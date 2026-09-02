#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unified refresh -> encrypt -> CloudBase deploy -> online verify command."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

SCRIPT_VERSION = "1.0.0"
HERE = Path(__file__).resolve().parent
REFRESH = HERE / "Refresh-FitnessWorkbench.py"
PREPARE = HERE / "Prepare-FitnessWorkbenchEncryptedRelease.py"
DEPLOY = HERE / "Deploy-FitnessWorkbenchCloudBaseEncrypted.py"
VERIFY = HERE / "Verify-FitnessWorkbenchCloudBaseEncrypted.py"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载私人发布模块")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verify_module = load(VERIFY, "lzheng_private_verify")
deploy_module = load(DEPLOY, "lzheng_private_deploy")


class PublishError(RuntimeError):
    pass


class StageError(PublishError):
    def __init__(self, message: str, payload: dict[str, Any] | None = None):
        super().__init__(message)
        self.payload = payload or {}


def now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name("." + path.name + ".tmp")
    staging.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(staging, path)


def overlaps(left: Path, right: Path) -> bool:
    try:
        left.resolve().relative_to(right.resolve())
        return True
    except ValueError:
        pass
    try:
        right.resolve().relative_to(left.resolve())
        return True
    except ValueError:
        return False


def external(label: str, path: Path, project: Path) -> Path:
    value = path.expanduser().absolute().resolve()
    if value == Path(value.anchor) or overlaps(value, project):
        raise PublishError(label + "必须位于项目外，且不能是磁盘根目录")
    return value


def fresh_snapshot(path: Path, max_hours: float, mode: str) -> dict[str, Any]:
    if not math.isfinite(max_hours) or max_hours <= 0 or max_hours > 24:
        raise PublishError("Notion 新鲜度上限必须是 0 到 24 小时的有限数值")
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublishError("Notion 快照无法读取") from exc
    if not isinstance(payload, dict) or payload.get("sync_mode") != mode:
        raise PublishError("Notion 快照模式与 --notion-mode 不一致")
    for key in ("source_queried_at", "snapshot_generated_at"):
        value = payload.get(key)
        if not isinstance(value, str) or not value:
            raise PublishError("Notion 快照缺少 " + key)
    try:
        instant = dt.datetime.fromisoformat(payload["source_queried_at"].replace("Z", "+00:00"))
        if instant.tzinfo is None:
            raise ValueError("timezone")
    except ValueError as exc:
        raise PublishError("Notion 查询时间无效") from exc
    age = dt.datetime.now(dt.timezone.utc) - instant.astimezone(dt.timezone.utc)
    if age.total_seconds() < -300 or age.total_seconds() > max_hours * 3600:
        raise PublishError("Notion 快照已过期；必须重新查询后发布")
    return payload


def run(command: list[str], label: str) -> dict[str, Any]:
    child_env = os.environ.copy()
    child_env["PYTHONUTF8"] = "1"
    completed = subprocess.run(command, text=True, encoding="utf-8", errors="replace", capture_output=True, env=child_env)
    if completed.returncode:
        message = (completed.stderr or completed.stdout).strip().replace("\r", " ").replace("\n", " ")[:600]
        payload: dict[str, Any] = {}
        for candidate in (completed.stderr, completed.stdout):
            try:
                payload = json.loads(candidate.strip().splitlines()[-1])
                break
            except (json.JSONDecodeError, IndexError):
                pass
        raise StageError(label + "失败：" + (message or "命令返回非零"), payload)
    try:
        return json.loads(completed.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return {"status": "PASS"}


def archive_release(release: Path, history: Path, encryption_receipt: Path, refresh_receipt: Path) -> dict[str, Any]:
    evidence = deploy_module.validate_release(release)
    stamp = dt.datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    target = history / (stamp + "-" + evidence["manifest_sha256"][:12])
    if target.exists():
        raise PublishError("发布历史已存在同名版本")
    history.mkdir(parents=True, exist_ok=True)
    staging = history / ("." + target.name + ".candidate")
    if staging.exists():
        raise PublishError("发布历史候选目录已存在")
    try:
        shutil.copytree(release, staging)
        archived = deploy_module.validate_release(staging)
        os.replace(staging, target)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    archive_receipt = history / (target.name + ".encrypted-receipt.json")
    original = json.loads(encryption_receipt.read_text(encoding="utf-8-sig"))
    original["result"].update({"release_dir": str(target), "manifest_sha256": archived["manifest_sha256"], "payload_sha256": archived["payload_sha256"]})
    atomic_json(archive_receipt, original)
    refresh_copy = history / (target.name + ".refresh-receipt.json")
    shutil.copy2(refresh_receipt, refresh_copy)
    return {"path": str(target), "manifest_sha256": archived["manifest_sha256"], "payload_sha256": archived["payload_sha256"], "encrypted_receipt": str(archive_receipt), "refresh_receipt": str(refresh_copy)}


def receipt_base() -> dict[str, Any]:
    return {"schema": 1, "kind": "lzheng_fitness_workbench_cloudbase_private_publish_receipt", "pipeline_version": SCRIPT_VERSION, "started_at": now(), "finished_at": None, "result": {"status": "RUNNING", "error": None}, "claims": {"formal_refreshed": False, "release_prepared": False, "deployed": False, "online_verified": False}, "evidence": {"refresh": None, "encryption": None, "archive": None, "cloudbase": None, "online": None}}


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Publish the full personal workbench as password-encrypted CloudBase static files")
    parser.add_argument("--project", required=True)
    parser.add_argument("--notion", required=True)
    parser.add_argument("--notion-mode", choices=("incremental", "full"), required=True)
    parser.add_argument("--private-release-dir", required=True)
    parser.add_argument("--encrypted-release-dir", required=True)
    parser.add_argument("--history-dir", required=True)
    parser.add_argument("--backup-dir", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--secret-file")
    parser.add_argument("--base-url")
    parser.add_argument("--max-notion-age-hours", type=float, default=24.0)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--verify-online", action="store_true")
    args = parser.parse_args(argv)
    receipt = receipt_base()
    receipt_path = Path(args.receipt).expanduser().absolute()
    try:
        project = Path(args.project).expanduser().resolve()
        if not (project / "健身工作台.html").is_file():
            raise PublishError("项目根目录缺少正式健身工作台.html")
        notion = Path(args.notion).expanduser().resolve()
        fresh_snapshot(notion, args.max_notion_age_hours, args.notion_mode)
        private_release = external("私人中间发布目录", Path(args.private_release_dir), project)
        encrypted_release = external("加密发布目录", Path(args.encrypted_release_dir), project)
        history = external("发布历史目录", Path(args.history_dir), project)
        backup = external("备份目录", Path(args.backup_dir), project)
        receipt_path = external("发布回执", receipt_path, project)
        paths = [private_release, encrypted_release, history, backup, receipt_path]
        if any(overlaps(paths[i], paths[j]) for i in range(len(paths)) for j in range(i + 1, len(paths))):
            raise PublishError("私人中间、加密发布、历史、备份和回执必须隔离")
        if args.verify_online and (not args.execute or not args.base_url):
            raise PublishError("线上核验必须同时指定 --execute 与 --base-url")
        config = Path(args.config).expanduser().resolve()
        if not config.is_file():
            raise PublishError("CloudBase 非敏感配置不存在")
        env_config = json.loads(config.read_text(encoding="utf-8-sig"))
        cloud_path = env_config.get("cloud_path")
        if not isinstance(cloud_path, str):
            raise PublishError("CloudBase 配置缺少专用 cloud_path")
        secret_lexical = Path(args.secret_file).expanduser().absolute() if args.secret_file else prepare_secret_default().absolute()
        if deploy_module.link_component(secret_lexical):
            raise PublishError("私人密钥路径链包含链接/reparse point")
        secret_file = secret_lexical.resolve()
        if not secret_file.is_file():
            raise PublishError("私人密钥不存在")
        for label, scope in (("项目", project), ("私人中间目录", private_release), ("加密发布目录", encrypted_release), ("历史目录", history), ("备份目录", backup), ("回执目录", receipt_path.parent), ("配置目录", config.parent)):
            if overlaps(secret_file, scope):
                raise PublishError("私人密钥必须位于" + label + "之外")
        run_id = dt.datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")
        run_root = Path(tempfile.gettempdir()) / "lzheng-fitness-workbench" / "cloudbase-private" / run_id
        run_root.mkdir(parents=True, exist_ok=False)
        refresh_receipt = run_root / "refresh.json"
        refresh_command = [sys.executable, str(REFRESH), "--project", str(project), "--notion", str(notion), "--notion-mode", args.notion_mode, "--backup-dir", str(backup), "--receipt", str(refresh_receipt), "--deploy", str(private_release), "--release-mode", "private-portable", "--confirm-private-portable"]
        receipt["evidence"]["refresh"] = run(refresh_command, "正式刷新与私人副本准备")
        refresh = json.loads(refresh_receipt.read_text(encoding="utf-8-sig"))
        refresh_claims = refresh.get("claims", {})
        if refresh.get("result", {}).get("status") != "PASS" or refresh_claims.get("formal_refreshed") is not True or refresh_claims.get("release_prepared") is not True:
            raise PublishError("刷新回执没有证明正式刷新和私人副本均通过")
        receipt["claims"].update({"formal_refreshed": True})
        encryption_receipt = run_root / "encryption.json"
        encryption_command = [sys.executable, str(PREPARE), "--private-release", str(private_release), "--out", str(encrypted_release), "--secret-file", str(secret_file), "--receipt", str(encryption_receipt)]
        receipt["evidence"]["encryption"] = run(encryption_command, "私人工作台加密封装")
        encryption = json.loads(encryption_receipt.read_text(encoding="utf-8-sig"))
        if encryption.get("claims", {}).get("release_prepared") is not True or encryption.get("result", {}).get("status") != "PASS":
            raise PublishError("加密回执没有证明 release_prepared=true")
        verify_module.verify(encrypted_release, secret_file)
        receipt["claims"]["release_prepared"] = True
        receipt["evidence"]["archive"] = archive_release(encrypted_release, history, encryption_receipt, refresh_receipt)
        env_id = env_config.get("env_id")
        deploy_command = [sys.executable, str(DEPLOY), "--release-dir", str(encrypted_release), "--env-id", str(env_id), "--cloud-path", cloud_path, "--project", str(project), "--backup-dir", str(backup), "--receipt", str(encryption_receipt), "--config", str(config), "--secret-file", str(secret_file)]
        if args.execute:
            deploy_command.append("--execute")
        try:
            cloudbase = run(deploy_command, "CloudBase 私人加密发布预检/上传")
        except StageError as exc:
            receipt["evidence"]["cloudbase"] = exc.payload or None
            if exc.payload.get("deployed") is True:
                receipt["claims"]["deployed"] = True
            raise
        receipt["evidence"]["cloudbase"] = cloudbase
        if args.execute and cloudbase.get("deployed") is not True:
            raise PublishError("CloudBase 未证明部署成功")
        if args.execute and cloudbase.get("remote_tree_exact") is not True:
            raise PublishError("CloudBase 未证明专用路径只含三份受管文件")
        receipt["claims"]["deployed"] = cloudbase.get("deployed") is True
        if args.verify_online:
            online = verify_module.verify(encrypted_release, secret_file, args.base_url)
            receipt["evidence"]["online"] = online
            receipt["claims"]["online_verified"] = online.get("online_verified") is True
        receipt["result"] = {"status": "PASS", "error": None}
    except Exception as exc:
        receipt["result"] = {"status": "FAIL", "error": str(exc)}
    receipt["finished_at"] = now()
    try:
        atomic_json(receipt_path, receipt)
    except OSError:
        print(json.dumps(receipt, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(receipt, ensure_ascii=False))
    return 0 if receipt["result"]["status"] == "PASS" else 1


def prepare_secret_default() -> Path:
    module = load(PREPARE, "lzheng_private_prepare_default")
    return module.default_secret_file().resolve()


if __name__ == "__main__":
    raise SystemExit(main())
