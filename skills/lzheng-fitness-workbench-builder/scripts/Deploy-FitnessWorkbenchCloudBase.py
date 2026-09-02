#!/usr/bin/env python3
"""CloudBase static-hosting adapter for a verified public release.

This adapter deliberately does not create CloudBase environments or touch billing.
It is a preflight tool by default; ``--execute`` is the only upload switch.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any

SCRIPT_VERSION = "1.0.1"
MANIFEST_SCHEMA = 2
MANIFEST_KIND = "lzheng-fitness-workbench-release"
MANIFEST_PRODUCER = "Prepare-FitnessWorkbenchRelease.py"


class Failure(Exception):
    pass


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def tree_evidence(root: Path) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for path in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda item: item.as_posix()):
        files.append({"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": digest(path)})
    canonical = json.dumps(files, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return {"file_count": len(files), "tree_sha256": hashlib.sha256(canonical).hexdigest(), "files": files}


def link_like(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        attrs = getattr(os.lstat(path), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def link_component(path: Path) -> Path | None:
    current = Path(path.expanduser().absolute().anchor)
    for part in path.expanduser().absolute().parts[1:]:
        current /= part
        if os.path.lexists(current) and link_like(current):
            return current
    return None


def overlap(a: Path, b: Path) -> bool:
    try:
        a.resolve().relative_to(b.resolve())
        return True
    except ValueError:
        pass
    try:
        b.resolve().relative_to(a.resolve())
        return True
    except ValueError:
        return False


def safe_rel(value: Any) -> str | None:
    if not isinstance(value, str) or not value or "\\" in value:
        return None
    p = PurePosixPath(value)
    if p.is_absolute() or ".." in p.parts or "." in p.parts:
        return None
    return p.as_posix()


def validate_release(release: Path) -> tuple[dict[str, Any], str, dict[str, Any]]:
    if not release.is_dir() or link_component(release):
        raise Failure("发布目录必须是普通目录，且路径链不能包含符号链接、junction 或 reparse point")
    manifest_path = release / "release-manifest.json"
    if not manifest_path.is_file() or link_like(manifest_path):
        raise Failure("发布目录缺少 release-manifest.json")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise Failure("release-manifest.json 无法解析") from exc
    if not isinstance(manifest, dict):
        raise Failure("release-manifest.json 顶层必须是对象")
    if (manifest.get("schema"), manifest.get("kind"), manifest.get("producer")) != (
        MANIFEST_SCHEMA, MANIFEST_KIND, MANIFEST_PRODUCER
    ):
        raise Failure("只接受 manifest schema 2 且由 Prepare-FitnessWorkbenchRelease.py 生成的发布目录")
    if manifest.get("release_mode") != "public-anonymized":
        raise Failure("CloudBase 公开部署只接受 release_mode=public-anonymized")
    if manifest.get("anonymized") is not True or manifest.get("contains_personal_data") is not False:
        raise Failure("发布清单未证明为匿名公开副本")
    allowed = [safe_rel(x) for x in manifest.get("allowed_files", [])]
    if any(x is None for x in allowed) or len(allowed) != len(set(allowed)):
        raise Failure("manifest allowed_files 含非法或重复路径")
    if set(allowed) != {"index.html", "release-manifest.json"}:
        raise Failure("public-anonymized 发布目录必须只包含 index.html 与 release-manifest.json")
    actual = []
    for root, dirs, files in os.walk(release, followlinks=False):
        for name in dirs + files:
            p = Path(root) / name
            if link_like(p):
                raise Failure("发布目录包含链接或 reparse 条目")
            actual.append(p.relative_to(release).as_posix())
    if set(actual) != set(allowed):
        raise Failure("发布目录实际文件与 manifest allowed_files 不一致")
    entries = manifest.get("files")
    if not isinstance(entries, list) or len(entries) != 1 or entries[0].get("path") != "index.html":
        raise Failure("manifest 文件哈希列表不符合 public-anonymized 约束")
    entry = entries[0]
    index = release / "index.html"
    if entry.get("bytes") != index.stat().st_size or entry.get("sha256") != digest(index):
        raise Failure("index.html 与 manifest 哈希不一致")
    return manifest, digest(manifest_path), tree_evidence(release)


def validate_refresh_receipt(receipt: Path, release: Path, manifest: dict[str, Any], tree: dict[str, Any]) -> None:
    try:
        payload = json.loads(receipt.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise Failure("指定刷新回执无法解析") from exc
    claims = payload.get("claims", {}) if isinstance(payload, dict) else {}
    artifact = payload.get("artifacts", {}).get("deploy") if isinstance(payload, dict) and isinstance(payload.get("artifacts"), dict) else None
    scripts = payload.get("scripts", {}) if isinstance(payload, dict) else {}
    refresh_script = scripts.get("refresh") if isinstance(scripts, dict) else None
    if payload.get("result", {}).get("status") != "PASS" or claims.get("release_prepared") is not True:
        raise Failure("回执未证明 release_prepared=true 且 result.status=PASS")
    if not isinstance(artifact, dict):
        raise Failure("回执缺少发布副本哈希证据")
    try:
        artifact_path = Path(str(artifact.get("path"))).expanduser().resolve()
    except OSError as exc:
        raise Failure("回执发布路径无效") from exc
    if artifact_path != release.resolve() or artifact.get("release_mode") != manifest.get("release_mode"):
        raise Failure("回执发布路径或发布模式与当前发布副本不一致")
    for key in ("file_count", "tree_sha256", "files"):
        if artifact.get(key) != tree.get(key):
            raise Failure("回执发布树哈希与当前发布副本不一致")
    index_entry = next((entry for entry in manifest.get("files", []) if entry.get("path") == "index.html"), None)
    if not isinstance(index_entry, dict) or not isinstance(refresh_script, dict) or not refresh_script.get("sha256") or not refresh_script.get("version"):
        raise Failure("回执缺少 index.html 或刷新脚本版本证据")


def run_tcb(binary: str, args: list[str], timeout: int = 20) -> tuple[bool, str]:
    try:
        result = subprocess.run([binary, *args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                timeout=timeout, check=False)
    except FileNotFoundError:
        return False, "未找到 tcb CLI；请安装 CloudBase CLI 后重试"
    except (OSError, subprocess.TimeoutExpired):
        return False, "tcb CLI 无法在限定时间内完成检查"
    if result.returncode == 0:
        return True, "ok"
    if args[:2] == ["hosting", "detail"]:
        return False, "CloudBase 登录态、凭证或环境访问失败；请重新执行 tcb login 并确认 env_id"
    return False, "tcb CLI 执行失败；请检查安装状态"


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy a verified public-anonymized release to CloudBase static hosting")
    parser.add_argument("--release-dir", required=True)
    parser.add_argument("--env-id")
    parser.add_argument("--cloud-path")
    parser.add_argument("--project", required=True)
    parser.add_argument("--backup-dir", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--config")
    parser.add_argument(
        "--tcb-bin",
        help="可选：CloudBase CLI 可执行文件；仅供受控测试或已安装 CLI 的明确位置使用，不写入回执",
    )
    parser.add_argument("--execute", action="store_true", help="explicitly upload; default is preflight only")
    ns = parser.parse_args()
    result: dict[str, Any] = {"adapter": "cloudbase-static-hosting", "version": SCRIPT_VERSION,
                              "mode": "execute" if ns.execute else "preflight", "deployed": False,
                              "online_verified": False}
    try:
        config: dict[str, Any] = {}
        if ns.config:
            config = json.loads(Path(ns.config).read_text(encoding="utf-8-sig"))
            if not isinstance(config, dict):
                raise Failure("配置模板顶层必须是对象")
        if config.get("accepted_free_tier") is not True:
            raise Failure("必须明确设置 accepted_free_tier=true；本适配器拒绝任何可能产生费用的配置")
        env_id = ns.env_id or config.get("env_id")
        if not isinstance(env_id, str) or not env_id or any(c in env_id for c in "\r\n\t"):
            raise Failure("必须提供非敏感 CloudBase env_id")
        if config.get("free_tier_env_id") != env_id or not isinstance(config.get("free_tier_checked_at"), str) or not config.get("free_tier_checked_at"):
            raise Failure("必须在腾讯云控制台人工确认零成本后填写同一 env_id 的 free_tier_env_id 与 free_tier_checked_at；此声明不替代控制台核验")
        release = Path(ns.release_dir).expanduser().absolute().resolve()
        project = Path(ns.project).expanduser().absolute().resolve() if ns.project else None
        backup = Path(ns.backup_dir).expanduser().absolute().resolve() if ns.backup_dir else None
        receipt = Path(ns.receipt).expanduser().absolute().resolve() if ns.receipt else None
        for label, p in (("项目", project), ("备份", backup), ("回执", receipt)):
            if p and overlap(release, p):
                raise Failure(f"发布路径不得与{label}路径重叠")
            if p and link_component(p):
                raise Failure(f"{label}路径链包含链接或 reparse point")
        manifest, manifest_hash, tree = validate_release(release)
        cloud_path = ns.cloud_path if ns.cloud_path is not None else config.get("cloud_path", "/")
        if not isinstance(cloud_path, str) or not cloud_path.startswith("/") or "\r" in cloud_path or "\n" in cloud_path:
            raise Failure("cloud_path 必须是以 / 开头的非敏感静态托管路径")
        result.update({"status": "preflight_ready", "release_dir": str(release), "env_id": env_id,
                       "cloud_path": cloud_path, "manifest_schema": 2, "manifest_sha256": manifest_hash,
                       "tree_sha256": tree["tree_sha256"], "files": [entry["path"] for entry in tree["files"]],
                       "zero_cost_declaration": {"accepted_free_tier": True, "env_id": env_id, "checked_at": config["free_tier_checked_at"]}})
        if receipt:
            if not receipt.is_file():
                raise Failure("指定回执不存在")
            validate_refresh_receipt(receipt, release, manifest, tree)
            result["receipt_checked"] = True
        # The override exists only for isolated tests and explicit local CLI
        # locations.  It is never persisted or emitted in the JSON receipt.
        tcb_raw = ns.tcb_bin or os.environ.get("LZHENG_CLOUDBASE_TCB_BIN") or "tcb"
        # npm installs the Windows shim as tcb.cmd.  Resolving it explicitly
        # makes subprocess invocation reliable without asking callers to alter
        # PATHEXT or expose any credential.
        tcb_bin = shutil.which(tcb_raw) or tcb_raw
        checks = {}
        checks["tcb_cli"] = run_tcb(tcb_bin, ["--version"])
        # `hosting detail` is an official read-only command in CLI 3.x.  Its
        # success proves both the login state and access to the requested env.
        checks["environment_access"] = run_tcb(tcb_bin, ["hosting", "detail", "--env-id", env_id])
        result["checks"] = {k: {"pass": v[0], "message": v[1]} for k, v in checks.items()}
        if not all(v[0] for v in checks.values()):
            raise Failure("CloudBase CLI/version、登录态或环境检查未通过；请安装 tcb、执行 tcb login，并确认 env_id 属于当前账号")
        if ns.execute:
            command = [tcb_bin, "hosting", "deploy", str(release), cloud_path, "-e", env_id]
            proc = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            if proc.returncode != 0:
                raise Failure("CloudBase 静态托管上传失败；请检查登录态、环境权限和云路径")
            result["status"] = "deployed"
            result["deployed"] = True
            result["online_verified"] = False
            result["verification"] = "上传完成，但本适配器不宣称线上验证"
    except (Failure, OSError, ValueError, json.JSONDecodeError) as exc:
        result.update({"status": "rejected", "error": str(exc), "recovery": "修正配置/路径/manifest 或 CloudBase 登录环境后重新运行；不会创建环境或修改计费资源"})
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 1
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
