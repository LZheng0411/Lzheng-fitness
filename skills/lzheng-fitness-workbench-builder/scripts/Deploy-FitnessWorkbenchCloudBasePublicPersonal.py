#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deploy an explicitly authorized public personal workbench to CloudBase."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any

HERE = Path(__file__).resolve().parent
COMMON = HERE / "Deploy-FitnessWorkbenchCloudBaseEncrypted.py"
SCRIPT_VERSION = "1.1.0"
KIND = "lzheng-fitness-workbench-public-personal-release"
PRODUCER = "Prepare-FitnessWorkbenchPublicPersonalRelease.py"
REQUIRED_FILES = {"index.html", "release-manifest.json"}


class DeployError(RuntimeError):
    pass


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 CloudBase 公共验证模块")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


common = load(COMMON, "lzheng_public_personal_cloudbase_common")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_relative(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        return None
    return path.as_posix()


def validate_release(root: Path) -> dict[str, Any]:
    if not root.is_dir() or common.link_component(root):
        raise DeployError("公开个人版目录不存在或路径链包含链接/reparse point")
    actual = {path.relative_to(root).as_posix(): path for path in root.rglob("*") if path.is_file()}
    try:
        manifest = json.loads(actual["release-manifest.json"].read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DeployError("公开个人版 manifest 无法解析") from exc
    if (manifest.get("schema"), manifest.get("kind"), manifest.get("producer")) != (1, KIND, PRODUCER):
        raise DeployError("只接受受管的公开个人版")
    if manifest.get("release_mode") != "public-personal-authorized" or manifest.get("contains_personal_data") is not True or manifest.get("user_authorized_public") is not True or manifest.get("required_access") != "public":
        raise DeployError("公开个人版缺少用户授权声明")
    allowed_list = manifest.get("allowed_files")
    if not isinstance(allowed_list, list) or len(set(allowed_list)) != len(allowed_list):
        raise DeployError("公开个人版 allowed_files 无效")
    allowed = set(allowed_list)
    if any(safe_relative(item) is None for item in allowed) or not REQUIRED_FILES.issubset(allowed):
        raise DeployError("公开个人版 allowed_files 路径不安全或缺少入口")
    if set(actual) != allowed:
        raise DeployError("公开个人版 allowed_files 不一致")
    entries = manifest.get("files")
    if not isinstance(entries, list):
        raise DeployError("公开个人版文件证据不完整")
    evidence_paths = set()
    for entry in entries:
        if not isinstance(entry, dict) or safe_relative(entry.get("path")) is None:
            raise DeployError("公开个人版文件证据路径无效")
        rel = entry["path"]
        if rel in evidence_paths or rel not in allowed or rel == "release-manifest.json":
            raise DeployError("公开个人版文件证据集合不一致")
        evidence_paths.add(rel)
        if entry.get("sha256") != sha256(actual[rel]) or entry.get("bytes") != actual[rel].stat().st_size:
            raise DeployError("公开个人版文件哈希不一致: " + rel)
    if evidence_paths != allowed - {"release-manifest.json"}:
        raise DeployError("公开个人版文件证据不完整")
    html = actual["index.html"].read_text(encoding="utf-8-sig")
    if '"mode":"public-personal-authorized"' not in html or '"user_authorized_public":true' not in html:
        raise DeployError("公开个人版 HTML 授权标记缺失")
    if "private-payload.json" in html or "请输入解密密码" in html:
        raise DeployError("公开个人版仍包含密码启动器")
    return {"manifest": manifest, "manifest_sha256": sha256(actual["release-manifest.json"]), "index_sha256": sha256(actual["index.html"]), "files": sorted(allowed)}


def validate_receipt(path: Path, release: Path, evidence: dict[str, Any]) -> None:
    try:
        receipt = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DeployError("公开个人版回执无法解析") from exc
    if receipt.get("kind") != "lzheng_fitness_workbench_public_personal_release_receipt" or receipt.get("claims", {}).get("release_prepared") is not True or receipt.get("result", {}).get("status") != "PASS":
        raise DeployError("公开个人版回执未证明 release_prepared=true")
    result = receipt["result"]
    if Path(str(result.get("release_dir"))).resolve() != release.resolve() or result.get("manifest_sha256") != evidence["manifest_sha256"] or result.get("index_sha256") != evidence["index_sha256"]:
        raise DeployError("公开个人版回执与当前目录不匹配")


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Deploy a public personal CloudBase workbench")
    parser.add_argument("--release-dir", required=True)
    parser.add_argument("--env-id", required=True)
    parser.add_argument("--cloud-path", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--backup-dir", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--tcb-bin")
    parser.add_argument("--confirm-public-personal-data", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    result: dict[str, Any] = {"adapter": "cloudbase-static-public-personal", "version": SCRIPT_VERSION, "deployed": False, "online_verified": False}
    try:
        if not args.confirm_public_personal_data:
            raise DeployError("必须显式确认线上内容包含可公开查看的个人数据")
        release = Path(args.release_dir).expanduser().absolute().resolve()
        project = Path(args.project).expanduser().absolute().resolve()
        backup = Path(args.backup_dir).expanduser().absolute().resolve()
        receipt = Path(args.receipt).expanduser().absolute().resolve()
        config = Path(args.config).expanduser().absolute().resolve()
        for label, path in (("项目", project), ("备份", backup), ("回执", receipt), ("配置", config)):
            if common.overlaps(release, path) or common.link_component(path):
                raise DeployError(f"发布目录不得与{label}重叠，且路径链不得含链接/reparse point")
        cloud_path = common.normalize_cloud_path(args.cloud_path)
        if cloud_path != "/fitness-public":
            raise DeployError("公开个人版只能部署到固定专用路径 /fitness-public")
        evidence = validate_release(release)
        config_data = common.validate_config(config, args.env_id, cloud_path)
        if config_data.get("release_mode") != "public-personal-authorized" or config_data.get("contains_personal_data") is not True or config_data.get("user_authorized_public") is not True:
            raise DeployError("CloudBase 配置不是显式公开个人版配置")
        validate_receipt(receipt, release, evidence)
        binary = shutil.which(args.tcb_bin or "tcb") or (args.tcb_bin or "tcb")
        checks = {"cli": common.run_tcb(binary, ["--version"]), "environment": common.run_tcb(binary, ["hosting", "detail", "--env-id", args.env_id])}
        if not all(checks.values()):
            raise DeployError("CloudBase CLI 登录态或目标环境访问检查失败")
        prefix = cloud_path.lstrip("/")
        expected = {prefix + "/" + name for name in evidence["files"]}
        remote_before = common.list_remote_keys(binary, args.env_id, cloud_path)
        legacy_two_file_release = {prefix + "/index.html", prefix + "/release-manifest.json"}
        if remote_before not in (set(), expected, legacy_two_file_release):
            raise DeployError("CloudBase 公开个人版专用路径含非受管文件，拒绝覆盖")
        result.update({"status": "preflight_ready", "mode": "public-personal-authorized", "release_dir": str(release), "env_id": args.env_id, "cloud_path": cloud_path, "manifest_sha256": evidence["manifest_sha256"], "index_sha256": evidence["index_sha256"], "files": evidence["files"], "migration_from_legacy_two_file_release": remote_before == legacy_two_file_release, "checks": checks, "remote_before": sorted(remote_before), "remote_expected": sorted(expected)})
        if args.execute:
            completed = subprocess.run([binary, "hosting", "deploy", str(release), cloud_path, "-e", args.env_id], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            if completed.returncode != 0:
                raise DeployError("CloudBase 公开个人版上传失败")
            result.update({"status": "deployed", "deployed": True})
            remote_after = common.list_remote_keys(binary, args.env_id, cloud_path)
            result.update({"remote_after": sorted(remote_after), "remote_tree_exact": remote_after == expected})
            if remote_after != expected:
                raise DeployError("上传已发生，但公开个人版远端文件集合不精确")
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0
    except (DeployError, common.DeployError, OSError, ValueError) as exc:
        result.update({"status": "rejected", "error": str(exc), "recovery": "修正公开个人版、回执、免费环境配置或 CLI 登录后重试；不会创建付费资源"})
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
