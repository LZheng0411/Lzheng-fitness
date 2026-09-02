#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unified public-personal refresh -> prepare -> CloudBase -> verify command."""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
COMMON = HERE / "Publish-FitnessWorkbenchCloudBasePrivate.py"
REFRESH = HERE / "Refresh-FitnessWorkbench.py"
PREPARE = HERE / "Prepare-FitnessWorkbenchPublicPersonalRelease.py"
DEPLOY = HERE / "Deploy-FitnessWorkbenchCloudBasePublicPersonal.py"
VERIFY = HERE / "Verify-FitnessWorkbenchCloudBasePublicPersonal.py"
SCRIPT_VERSION = "1.0.0"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载公开个人版模块")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


common = load(COMMON, "lzheng_public_personal_publish_common")
deploy_module = load(DEPLOY, "lzheng_public_personal_publish_deploy")
verify_module = load(VERIFY, "lzheng_public_personal_publish_verify")


class PublishError(RuntimeError):
    pass


def archive_release(release: Path, history: Path, prepare_receipt: Path, refresh_receipt: Path) -> dict[str, Any]:
    evidence = deploy_module.validate_release(release)
    stamp = dt.datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    target = history / (stamp + "-" + evidence["manifest_sha256"][:12])
    if target.exists():
        raise PublishError("公开个人版历史已存在同名版本")
    history.mkdir(parents=True, exist_ok=True)
    staging = history / ("." + target.name + ".candidate")
    shutil.copytree(release, staging)
    try:
        archived = deploy_module.validate_release(staging)
        os.replace(staging, target)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    prepare_copy = history / (target.name + ".prepare-receipt.json")
    refresh_copy = history / (target.name + ".refresh-receipt.json")
    payload = json.loads(prepare_receipt.read_text(encoding="utf-8-sig"))
    payload["result"]["release_dir"] = str(target)
    common.atomic_json(prepare_copy, payload)
    shutil.copy2(refresh_receipt, refresh_copy)
    return {"path": str(target), "manifest_sha256": archived["manifest_sha256"], "index_sha256": archived["index_sha256"], "prepare_receipt": str(prepare_copy), "refresh_receipt": str(refresh_copy)}


def receipt_base() -> dict[str, Any]:
    return {"schema": 1, "kind": "lzheng_fitness_workbench_cloudbase_public_personal_publish_receipt", "pipeline_version": SCRIPT_VERSION, "started_at": common.now(), "finished_at": None, "result": {"status": "RUNNING", "error": None}, "claims": {"formal_refreshed": False, "release_prepared": False, "deployed": False, "online_verified": False}, "evidence": {"refresh": None, "prepare": None, "archive": None, "cloudbase": None, "online": None}}


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Publish an explicitly public personal fitness workbench")
    parser.add_argument("--project", required=True)
    parser.add_argument("--notion", required=True)
    parser.add_argument("--notion-mode", choices=("incremental", "full"), required=True)
    parser.add_argument("--private-release-dir", required=True)
    parser.add_argument("--public-release-dir", required=True)
    parser.add_argument("--history-dir", required=True)
    parser.add_argument("--backup-dir", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--base-url")
    parser.add_argument("--max-notion-age-hours", type=float, default=24.0)
    parser.add_argument("--confirm-public-personal-data", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--verify-online", action="store_true")
    args = parser.parse_args(argv)
    receipt = receipt_base()
    receipt_path = Path(args.receipt).expanduser().absolute()
    try:
        if not args.confirm_public_personal_data:
            raise PublishError("必须显式确认完整个人工作台将公开访问")
        project = Path(args.project).expanduser().resolve()
        if not (project / "健身工作台.html").is_file():
            raise PublishError("项目根目录缺少正式健身工作台.html")
        notion = Path(args.notion).expanduser().resolve()
        common.fresh_snapshot(notion, args.max_notion_age_hours, args.notion_mode)
        private_release = common.external("私人中间发布目录", Path(args.private_release_dir), project)
        public_release = common.external("公开个人发布目录", Path(args.public_release_dir), project)
        history = common.external("发布历史目录", Path(args.history_dir), project)
        backup = common.external("备份目录", Path(args.backup_dir), project)
        receipt_path = common.external("发布回执", receipt_path, project)
        paths = [private_release, public_release, history, backup, receipt_path]
        if any(common.overlaps(paths[i], paths[j]) for i in range(len(paths)) for j in range(i + 1, len(paths))):
            raise PublishError("中间、公开、历史、备份和回执必须隔离")
        if args.verify_online and (not args.execute or not args.base_url):
            raise PublishError("线上核验必须同时指定 --execute 与 --base-url")
        config = Path(args.config).expanduser().resolve()
        env_config = json.loads(config.read_text(encoding="utf-8-sig"))
        env_id, cloud_path = env_config.get("env_id"), env_config.get("cloud_path")
        if not isinstance(env_id, str) or not isinstance(cloud_path, str):
            raise PublishError("CloudBase 配置缺少环境或专用路径")
        if cloud_path != "/fitness-public" or env_config.get("release_mode") != "public-personal-authorized" or env_config.get("contains_personal_data") is not True or env_config.get("user_authorized_public") is not True:
            raise PublishError("公开个人版配置必须显式绑定 /fitness-public 与 public-personal-authorized")
        run_id = dt.datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")
        run_root = Path(tempfile.gettempdir()) / "lzheng-fitness-workbench" / "cloudbase-public-personal" / run_id
        run_root.mkdir(parents=True, exist_ok=False)
        refresh_receipt = run_root / "refresh.json"
        refresh_command = [sys.executable, str(REFRESH), "--project", str(project), "--notion", str(notion), "--notion-mode", args.notion_mode, "--backup-dir", str(backup), "--receipt", str(refresh_receipt), "--deploy", str(private_release), "--release-mode", "private-portable", "--confirm-private-portable"]
        receipt["evidence"]["refresh"] = common.run(refresh_command, "正式刷新与私人中间副本")
        refresh = json.loads(refresh_receipt.read_text(encoding="utf-8-sig"))
        if refresh.get("result", {}).get("status") != "PASS" or refresh.get("claims", {}).get("formal_refreshed") is not True or refresh.get("claims", {}).get("release_prepared") is not True:
            raise PublishError("刷新回执未证明本地两级成功")
        receipt["claims"]["formal_refreshed"] = True
        prepare_receipt = run_root / "prepare.json"
        prepare_command = [sys.executable, str(PREPARE), "--private-release", str(private_release), "--out", str(public_release), "--receipt", str(prepare_receipt), "--confirm-public-personal-data"]
        receipt["evidence"]["prepare"] = common.run(prepare_command, "公开个人版单文件准备")
        prepared = json.loads(prepare_receipt.read_text(encoding="utf-8-sig"))
        if prepared.get("claims", {}).get("release_prepared") is not True:
            raise PublishError("公开个人版回执未证明 release_prepared=true")
        receipt["claims"]["release_prepared"] = True
        receipt["evidence"]["archive"] = archive_release(public_release, history, prepare_receipt, refresh_receipt)
        deploy_command = [sys.executable, str(DEPLOY), "--release-dir", str(public_release), "--env-id", env_id, "--cloud-path", cloud_path, "--project", str(project), "--backup-dir", str(backup), "--receipt", str(prepare_receipt), "--config", str(config), "--confirm-public-personal-data"]
        if args.execute:
            deploy_command.append("--execute")
        try:
            cloudbase = common.run(deploy_command, "CloudBase 公开个人版预检/上传")
        except common.StageError as exc:
            receipt["evidence"]["cloudbase"] = exc.payload or None
            if exc.payload.get("deployed") is True:
                receipt["claims"]["deployed"] = True
            raise
        receipt["evidence"]["cloudbase"] = cloudbase
        if args.execute and (cloudbase.get("deployed") is not True or cloudbase.get("remote_tree_exact") is not True):
            raise PublishError("CloudBase 未证明公开个人版部署与远端文件集成功")
        receipt["claims"]["deployed"] = cloudbase.get("deployed") is True
        if args.verify_online:
            online = verify_module.verify(public_release, args.base_url)
            receipt["evidence"]["online"] = online
            receipt["claims"]["online_verified"] = online.get("online_verified") is True
        receipt["result"] = {"status": "PASS", "error": None}
    except Exception as exc:
        receipt["result"] = {"status": "FAIL", "error": str(exc)}
    receipt["finished_at"] = common.now()
    try:
        common.atomic_json(receipt_path, receipt)
    except OSError:
        print(json.dumps(receipt, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(receipt, ensure_ascii=False))
    return 0 if receipt["result"]["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
