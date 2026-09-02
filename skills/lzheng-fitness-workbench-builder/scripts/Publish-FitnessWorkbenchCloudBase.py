#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One explicit CloudBase publishing entry for the personal workbench.

The command requires a freshly queried Notion snapshot.  It refreshes only the
formal ``workbench-data`` block through the existing checked pipeline, prepares
an anonymous release, archives that exact release, then optionally uploads and
reads the public URL.  It never creates CloudBase environments, billing
resources, or credentials.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import math
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

SCRIPT_VERSION = "1.0.1"
HERE = Path(__file__).resolve().parent
REFRESH = HERE / "Refresh-FitnessWorkbench.py"
DEPLOYER = HERE / "Deploy-FitnessWorkbenchCloudBase.py"
VERIFY = HERE / "Verify-FitnessWorkbenchCloudBase.py"

_verify_spec = importlib.util.spec_from_file_location("lzheng_cloudbase_verify", VERIFY)
if _verify_spec is None or _verify_spec.loader is None:
    raise RuntimeError("无法加载 Verify-FitnessWorkbenchCloudBase.py")
_verify_module = importlib.util.module_from_spec(_verify_spec)
_verify_spec.loader.exec_module(_verify_module)
VerificationError = _verify_module.VerificationError
verify_online = _verify_module.verify_online
verify_release = _verify_module.verify_release


class PublishError(RuntimeError):
    pass


def iso_now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def link_like(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def first_link_component(path: Path) -> Path | None:
    absolute = path.expanduser().absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if os.path.lexists(current) and link_like(current):
            return current
    return None


def within(left: Path, right: Path) -> bool:
    try:
        left.resolve().relative_to(right.resolve())
        return True
    except ValueError:
        return False


def overlaps(left: Path, right: Path) -> bool:
    return within(left, right) or within(right, left)


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name("." + path.name + ".tmp")
    staging.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(staging, path)


def fresh_notion_snapshot(path: Path, max_age_hours: float) -> dict[str, Any]:
    if not math.isfinite(max_age_hours) or max_age_hours <= 0 or max_age_hours > 24:
        raise PublishError("Notion 新鲜度上限必须是 0 到 24 小时的有限数值")
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublishError("Notion 快照无法读取；未执行刷新或部署") from exc
    if not isinstance(payload, dict):
        raise PublishError("Notion 快照根节点无效；未执行刷新或部署")
    queried = payload.get("source_queried_at")
    if not isinstance(queried, str) or not queried:
        raise PublishError("Notion 快照缺少 source_queried_at；不能冒充最新数据")
    try:
        instant = dt.datetime.fromisoformat(queried.replace("Z", "+00:00"))
        if instant.tzinfo is None:
            raise ValueError("timezone")
    except ValueError as exc:
        raise PublishError("Notion 快照查询时间无法解析；不能冒充最新数据") from exc
    age = dt.datetime.now(dt.timezone.utc) - instant.astimezone(dt.timezone.utc)
    if age.total_seconds() < -300 or age.total_seconds() > max_age_hours * 3600:
        raise PublishError("Notion 快照已过期或时间异常；请让 Agent 重新查询 Notion 后再发布")
    if payload.get("sync_mode") not in {"incremental", "full"}:
        raise PublishError("Notion 快照缺少合法 sync_mode；不能执行发布")
    generated = payload.get("snapshot_generated_at")
    if not isinstance(generated, str) or not generated:
        raise PublishError("Notion 快照缺少 snapshot_generated_at；不能冒充最新数据")
    return payload


def safe_external(label: str, path: Path, project: Path) -> Path:
    lexical = path.expanduser().absolute()
    linked = first_link_component(lexical)
    if linked:
        raise PublishError(f"{label}路径不能经过符号链接、junction 或 reparse point：{linked}")
    resolved = lexical.resolve()
    if resolved == Path(resolved.anchor) or overlaps(resolved, project):
        raise PublishError(f"{label}必须位于项目外且不能是磁盘根目录")
    return resolved


def run(command: list[str], label: str) -> dict[str, Any]:
    completed = subprocess.run(command, text=True, encoding="utf-8", errors="replace", capture_output=True)
    if completed.returncode:
        message = (completed.stderr or completed.stdout).strip().replace("\r", " ").replace("\n", " ")[:500]
        raise PublishError(f"{label}失败：{message or '命令返回非零'}")
    return {"command": [Path(command[0]).name, *command[1:]], "returncode": completed.returncode}


def archive_release(release: Path, history: Path, refresh_receipt: Path) -> dict[str, Any]:
    local = verify_release(release, "public-anonymized")
    stamp = dt.datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    target = history / (stamp + "-" + local["index_sha256"][:12])
    if target.exists() or first_link_component(history):
        raise PublishError("发布历史目录异常或已存在同名版本，拒绝覆盖")
    staging = history / ("." + target.name + ".candidate")
    if staging.exists():
        raise PublishError("发布历史候选目录已存在，拒绝覆盖")
    history.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copytree(release, staging)
        verify_release(staging, "public-anonymized")
        os.replace(staging, target)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    receipt_target = history / (target.name + ".refresh-receipt.json")
    shutil.copy2(refresh_receipt, receipt_target)
    return {"path": str(target), "index_sha256": local["index_sha256"], "manifest_sha256": local["manifest_sha256"], "manifest_version": local.get("version"), "refresh_receipt_path": str(receipt_target), "refresh_receipt_sha256": sha256_file(receipt_target)}


def base_receipt() -> dict[str, Any]:
    return {
        "schema": 1,
        "kind": "lzheng_fitness_workbench_cloudbase_publish_receipt",
        "pipeline_version": SCRIPT_VERSION,
        "started_at": iso_now(), "finished_at": None,
        "result": {"status": "RUNNING", "error": None},
        "claims": {"formal_refreshed": False, "release_prepared": False, "deployed": False, "online_verified": False},
        "evidence": {"refresh_receipt": None, "archive": None, "cloudbase": None, "online": None},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh, publish, and verify a public-anonymized workbench on CloudBase")
    parser.add_argument("--project", required=True)
    parser.add_argument("--notion", required=True, help="本次 Agent 实际查询 Notion 后冻结的 JSON 快照")
    parser.add_argument("--notion-mode", choices=("incremental", "full"), required=True)
    parser.add_argument("--release-dir", required=True)
    parser.add_argument("--history-dir", required=True)
    parser.add_argument("--backup-dir", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--base-url", help="CloudBase 默认网址；只有 --verify-online 才需要")
    parser.add_argument("--max-notion-age-hours", type=float, default=24.0)
    parser.add_argument("--execute", action="store_true", help="明确允许上传已验收的匿名发布副本")
    parser.add_argument("--verify-online", action="store_true", help="明确允许部署后 HTTP 回读核验")
    args = parser.parse_args(argv)

    receipt_path = Path(args.receipt).expanduser().absolute()
    receipt = base_receipt()
    try:
        project = Path(args.project).expanduser().resolve()
        if not project.is_dir() or not (project / "健身工作台.html").is_file():
            raise PublishError("项目根目录缺少正式健身工作台.html")
        notion = Path(args.notion).expanduser().resolve()
        snapshot = fresh_notion_snapshot(notion, args.max_notion_age_hours)
        if snapshot["sync_mode"] != args.notion_mode:
            raise PublishError("--notion-mode 与快照 sync_mode 不一致；未执行刷新或部署")
        release = safe_external("发布", Path(args.release_dir), project)
        history = safe_external("发布历史", Path(args.history_dir), project)
        backup = safe_external("备份", Path(args.backup_dir), project)
        config = Path(args.config).expanduser().resolve()
        if not config.is_file():
            raise PublishError("CloudBase 非敏感配置文件不存在")
        if args.verify_online and (not args.execute or not args.base_url):
            raise PublishError("线上核验必须同时显式 --execute 和 --base-url")
        if not args.execute and args.verify_online:
            raise PublishError("未上传时不得声称线上验证")
        receipt_path = safe_external("发布回执", receipt_path, project)
        if any(overlaps(a, b) for a, b in ((release, history), (release, backup), (history, backup), (receipt_path, release), (receipt_path, history), (receipt_path, backup))):
            raise PublishError("发布、历史、备份和回执目录必须完全隔离")
        run_id = dt.datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")
        stage_root = Path(tempfile.gettempdir()) / "lzheng-fitness-workbench" / "cloudbase" / run_id
        stage_root.mkdir(parents=True, exist_ok=False)
        refresh_receipt = stage_root / "refresh.json"
        refresh_cmd = [sys.executable, str(REFRESH), "--project", str(project), "--notion", str(notion), "--notion-mode", args.notion_mode, "--backup-dir", str(backup), "--receipt", str(refresh_receipt), "--deploy", str(release), "--release-mode", "public-anonymized"]
        receipt["evidence"]["refresh"] = run(refresh_cmd, "正式刷新与发布副本准备")
        refresh = json.loads(refresh_receipt.read_text(encoding="utf-8-sig"))
        claims = refresh.get("claims", {})
        if refresh.get("result", {}).get("status") != "PASS" or claims.get("formal_refreshed") is not True or claims.get("release_prepared") is not True:
            raise PublishError("刷新回执未证明正式校验和发布副本校验均通过")
        receipt["claims"]["formal_refreshed"] = True
        receipt["claims"]["release_prepared"] = True
        receipt["evidence"]["refresh_receipt"] = {"sha256": sha256_file(refresh_receipt), "path": str(refresh_receipt)}
        receipt["evidence"]["archive"] = archive_release(release, history, refresh_receipt)
        adapter_cmd = [sys.executable, str(DEPLOYER), "--release-dir", str(release), "--project", str(project), "--backup-dir", str(backup), "--receipt", str(refresh_receipt), "--config", str(config)]
        if args.execute:
            adapter_cmd.append("--execute")
        adapter_result = subprocess.run(adapter_cmd, text=True, encoding="utf-8", errors="replace", capture_output=True)
        adapter = json.loads(adapter_result.stdout or "{}")
        receipt["evidence"]["cloudbase"] = adapter
        if adapter_result.returncode:
            raise PublishError("CloudBase 部署预检失败：" + str(adapter.get("error") or "未返回可用状态"))
        if adapter.get("deployed") is True:
            receipt["claims"]["deployed"] = True
        elif args.execute:
            raise PublishError("CloudBase 上传未成功；未执行线上验证")
        if args.verify_online:
            online = verify_online(release, args.base_url, "public-anonymized")
            receipt["evidence"]["online"] = online
            receipt["claims"]["online_verified"] = True
        receipt["result"]["status"] = "PASS"
    except (PublishError, VerificationError, OSError, json.JSONDecodeError) as exc:
        receipt["result"] = {"status": "FAIL", "error": str(exc)}
    receipt["finished_at"] = iso_now()
    try:
        atomic_json(receipt_path, receipt)
    except OSError:
        print(json.dumps(receipt, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(receipt, ensure_ascii=False))
    return 0 if receipt["result"]["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
