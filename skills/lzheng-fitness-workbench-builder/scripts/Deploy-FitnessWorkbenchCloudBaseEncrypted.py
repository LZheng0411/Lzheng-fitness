#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deploy only a verified password-encrypted workbench to CloudBase hosting."""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any

SCRIPT_VERSION = "1.0.0"
KIND = "lzheng-fitness-workbench-encrypted-release"
PRODUCER = "Prepare-FitnessWorkbenchEncryptedRelease.py"
FILES = {"index.html", "private-payload.json", "release-manifest.json"}
PRIVATE_MARKERS = ("obsidian://", "notion://", "E:\\obsidian", "C:\\Users\\", "/Users/", "/home/")
PREPARE = Path(__file__).resolve().parent / "Prepare-FitnessWorkbenchEncryptedRelease.py"


class DeployError(RuntimeError):
    pass


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载加密发布核验模块")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prepare_module = load(PREPARE, "lzheng_private_prepare_for_deploy")


def sha256(path: Path) -> str:
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


def link_component(path: Path) -> Path | None:
    absolute = path.expanduser().absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if os.path.lexists(current) and link_like(current):
            return current
    return None


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


def tree_evidence(root: Path) -> dict[str, Any]:
    entries = [{"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path)} for path in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda item: item.as_posix())]
    canonical = json.dumps(entries, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return {"file_count": len(entries), "tree_sha256": hashlib.sha256(canonical).hexdigest(), "files": entries}


def validate_release(root: Path) -> dict[str, Any]:
    if not root.is_dir() or link_component(root):
        raise DeployError("加密发布目录不存在或路径链包含链接/reparse point")
    actual: dict[str, Path] = {}
    for path in root.rglob("*"):
        if link_like(path):
            raise DeployError("加密发布目录包含链接/reparse 条目")
        if path.is_file():
            actual[path.relative_to(root).as_posix()] = path
    if set(actual) != FILES:
        raise DeployError("加密发布目录必须且只能包含 index、密文和 manifest")
    try:
        manifest = json.loads(actual["release-manifest.json"].read_text(encoding="utf-8-sig"))
        payload = json.loads(actual["private-payload.json"].read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DeployError("加密发布 manifest 或密文无法解析") from exc
    if (manifest.get("schema"), manifest.get("kind"), manifest.get("producer")) != (1, KIND, PRODUCER):
        raise DeployError("只接受受管的 private-encrypted 发布目录")
    if manifest.get("release_mode") != "private-encrypted" or manifest.get("personal_data_encrypted") is not True or manifest.get("required_access") != "strong-passphrase":
        raise DeployError("加密发布的隐私声明不完整")
    if set(manifest.get("allowed_files", [])) != FILES:
        raise DeployError("加密发布 allowed_files 不一致")
    entries = manifest.get("files")
    if not isinstance(entries, list):
        raise DeployError("加密发布缺少文件哈希")
    by_path = {entry.get("path"): entry for entry in entries if isinstance(entry, dict)}
    if set(by_path) != {"index.html", "private-payload.json"}:
        raise DeployError("加密发布文件哈希列表不完整")
    for rel, entry in by_path.items():
        path = actual[rel]
        if entry.get("sha256") != sha256(path) or entry.get("bytes") != path.stat().st_size:
            raise DeployError("加密发布文件哈希不一致: " + rel)
    if payload.get("schema") != 1 or payload.get("kind") != "lzheng_fitness_workbench_encrypted_payload" or payload.get("crypto") != "AES-256-GCM" or payload.get("kdf") != "PBKDF2-HMAC-SHA256" or payload.get("iterations", 0) < 600_000:
        raise DeployError("加密 payload 的密码学参数不受支持")
    try:
        if len(base64.b64decode(payload["salt"], validate=True)) != 16 or len(base64.b64decode(payload["nonce"], validate=True)) != 12 or len(base64.b64decode(payload["ciphertext"], validate=True)) < 32:
            raise ValueError("size")
    except (KeyError, ValueError) as exc:
        raise DeployError("加密 payload 的密文字段无效") from exc
    public_text = "\n".join(path.read_text(encoding="utf-8-sig") for path in actual.values())
    if any(marker.lower() in public_text.lower() for marker in PRIVATE_MARKERS):
        raise DeployError("加密发布明文文件仍包含私人路径或深链")
    return {"manifest": manifest, "tree": tree_evidence(root), "manifest_sha256": sha256(actual["release-manifest.json"]), "payload_sha256": sha256(actual["private-payload.json"]), "index_sha256": sha256(actual["index.html"])}


def validate_config(path: Path, env_id: str, cloud_path: str) -> dict[str, Any]:
    try:
        config = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DeployError("CloudBase 非敏感配置无法解析") from exc
    if not isinstance(config, dict) or config.get("accepted_free_tier") is not True or config.get("env_id") != env_id or config.get("free_tier_env_id") != env_id or not isinstance(config.get("free_tier_checked_at"), str) or not config.get("free_tier_checked_at"):
        raise DeployError("CloudBase 配置未绑定已人工核验的同一免费环境")
    if config.get("package_price_cny_month") != 0 or config.get("pay_as_you_go_supported") is not False:
        raise DeployError("CloudBase 配置没有证明月费为 0 且禁止按量计费")
    if config.get("cloud_path") != cloud_path:
        raise DeployError("CloudBase 配置与专用云路径不一致")
    return config


def validate_receipt(path: Path, release: Path, evidence: dict[str, Any]) -> None:
    try:
        receipt = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DeployError("加密发布回执无法解析") from exc
    claims = receipt.get("claims", {}) if isinstance(receipt, dict) else {}
    result = receipt.get("result", {}) if isinstance(receipt, dict) else {}
    if receipt.get("kind") != "lzheng_fitness_workbench_encrypted_release_receipt" or claims.get("release_prepared") is not True or result.get("status") != "PASS":
        raise DeployError("加密发布回执未证明 release_prepared=true")
    if Path(str(result.get("release_dir"))).resolve() != release.resolve() or result.get("mode") != "private-encrypted":
        raise DeployError("加密发布回执的目录或模式不匹配")
    if result.get("manifest_sha256") != evidence["manifest_sha256"] or result.get("payload_sha256") != evidence["payload_sha256"]:
        raise DeployError("加密发布回执哈希与当前目录不匹配")


def run_tcb(binary: str, args: list[str], timeout: int = 20) -> bool:
    try:
        result = subprocess.run([binary, *args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def normalize_cloud_path(value: str) -> str:
    normalized = value.rstrip("/")
    if not re.fullmatch(r"/[a-z0-9][a-z0-9-]{2,62}", normalized):
        raise DeployError("私人加密工作台必须使用非根目录的专用小写云路径")
    return normalized


def expected_remote_keys(cloud_path: str) -> set[str]:
    prefix = cloud_path.lstrip("/")
    return {prefix + "/" + name for name in FILES}


def list_remote_keys(binary: str, env_id: str, cloud_path: str, timeout: int = 30) -> set[str]:
    child_env = os.environ.copy()
    child_env["PYTHONUTF8"] = "1"
    try:
        completed = subprocess.run([binary, "hosting", "list", cloud_path, "-e", env_id, "--json"], text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=timeout, check=False, env=child_env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DeployError("无法读取 CloudBase 专用路径文件列表") from exc
    if completed.returncode != 0:
        raise DeployError("CloudBase 专用路径文件列表读取失败")
    try:
        payload = json.loads(completed.stdout)
        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise TypeError("data")
        if any(not isinstance(row, dict) or not isinstance(row.get("key"), str) for row in rows):
            raise TypeError("key")
        keys = {row["key"] for row in rows}
    except (json.JSONDecodeError, AttributeError, TypeError) as exc:
        raise DeployError("CloudBase 专用路径文件列表格式无效") from exc
    return keys


def validate_remote_before(actual: set[str], expected: set[str]) -> None:
    if actual != set() and actual != expected:
        raise DeployError("CloudBase 专用路径必须为空或精确包含三份受管文件")


def validate_local_decryption(release: Path, secret_file: Path, evidence: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = json.loads((release / "private-payload.json").read_text(encoding="utf-8-sig"))
        passphrase = prepare_module.load_secret(secret_file)
        salt = base64.b64decode(payload["salt"], validate=True)
        nonce = base64.b64decode(payload["nonce"], validate=True)
        ciphertext = base64.b64decode(payload["ciphertext"], validate=True)
        key = prepare_module.derive_key(passphrase, salt)
        html = prepare_module.AESGCM(key).decrypt(nonce, ciphertext, payload["aad"].encode("ascii")).decode("utf-8")
    except Exception as exc:
        raise DeployError("当前 DPAPI 密钥无法解密并绑定这一版加密产物") from exc
    if len(re.findall(r'<script id="workbench-data" type="application/json">', html)) != 1:
        raise DeployError("当前 DPAPI 密钥解密后的工作台结构异常")
    return {"passed": True, "manifest_sha256": evidence["manifest_sha256"], "payload_sha256": evidence["payload_sha256"]}


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Deploy a verified private-encrypted workbench release")
    parser.add_argument("--release-dir", required=True)
    parser.add_argument("--env-id", required=True)
    parser.add_argument("--cloud-path", default="/")
    parser.add_argument("--project", required=True)
    parser.add_argument("--backup-dir", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--secret-file", required=True)
    parser.add_argument("--tcb-bin")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    result: dict[str, Any] = {"adapter": "cloudbase-static-private-encrypted", "version": SCRIPT_VERSION, "deployed": False, "online_verified": False}
    try:
        release = Path(args.release_dir).expanduser().absolute().resolve()
        project = Path(args.project).expanduser().absolute().resolve()
        backup = Path(args.backup_dir).expanduser().absolute().resolve()
        receipt = Path(args.receipt).expanduser().absolute().resolve()
        config_path = Path(args.config).expanduser().absolute().resolve()
        secret_lexical = Path(args.secret_file).expanduser().absolute()
        if link_component(secret_lexical):
            raise DeployError("私人密钥路径链包含链接/reparse point")
        secret_file = secret_lexical.resolve()
        for label, path in (("项目", project), ("备份", backup), ("回执", receipt), ("配置", config_path)):
            if overlaps(release, path) or link_component(path):
                raise DeployError(f"发布目录不得与{label}重叠，且路径链不得含链接/reparse point")
        if not secret_file.is_file():
            raise DeployError("私人密钥不存在")
        for label, path in (("项目", project), ("发布目录", release), ("备份", backup), ("回执目录", receipt.parent), ("配置目录", config_path.parent)):
            if overlaps(secret_file, path):
                raise DeployError("私人密钥必须位于" + label + "之外")
        cloud_path = normalize_cloud_path(args.cloud_path)
        evidence = validate_release(release)
        validate_config(config_path, args.env_id, cloud_path)
        validate_receipt(receipt, release, evidence)
        local_decryption = validate_local_decryption(release, secret_file, evidence)
        binary = shutil.which(args.tcb_bin or "tcb") or (args.tcb_bin or "tcb")
        checks = {"cli": run_tcb(binary, ["--version"]), "environment": run_tcb(binary, ["hosting", "detail", "--env-id", args.env_id])}
        if not all(checks.values()):
            raise DeployError("CloudBase CLI 登录态或目标环境访问检查失败")
        expected = expected_remote_keys(cloud_path)
        remote_before = list_remote_keys(binary, args.env_id, cloud_path)
        validate_remote_before(remote_before, expected)
        result.update({"status": "preflight_ready", "mode": "private-encrypted", "release_dir": str(release), "env_id": args.env_id, "cloud_path": cloud_path, "manifest_sha256": evidence["manifest_sha256"], "payload_sha256": evidence["payload_sha256"], "index_sha256": evidence["index_sha256"], "tree_sha256": evidence["tree"]["tree_sha256"], "checks": checks, "local_decryption": local_decryption, "remote_before": sorted(remote_before), "remote_expected": sorted(expected)})
        if args.execute:
            completed = subprocess.run([binary, "hosting", "deploy", str(release), cloud_path, "-e", args.env_id], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            if completed.returncode != 0:
                raise DeployError("CloudBase 私人加密发布上传失败")
            result.update({"status": "deployed", "deployed": True, "online_verified": False})
            remote_after = list_remote_keys(binary, args.env_id, cloud_path)
            result["remote_after"] = sorted(remote_after)
            result["remote_tree_exact"] = remote_after == expected
            if remote_after != expected:
                raise DeployError("上传已发生，但 CloudBase 专用路径文件集合不精确")
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0
    except (DeployError, OSError, ValueError) as exc:
        result.update({"status": "rejected", "error": str(exc), "recovery": "修正加密发布、回执、免费环境配置或 CLI 登录后重试；不会创建付费资源"})
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
