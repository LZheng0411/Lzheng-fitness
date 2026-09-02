#!/usr/bin/env python3
"""Verify a manifest-backed workbench release and, when requested, its online copy.

This module deliberately does not create CloudBase resources.  The normal call is a
local preflight; ``--verify-online`` is the explicit opt-in for an HTTP GET.  A
rollback is only accepted from another release directory whose manifest and file
hashes pass the same checks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MANIFEST_NAME = "release-manifest.json"
MANIFEST_SCHEMA = 2
MANIFEST_KIND = "lzheng-fitness-workbench-release"
MANIFEST_PRODUCER = "Prepare-FitnessWorkbenchRelease.py"
RELEASE_MODES = {"public-anonymized", "private-portable"}
CLAIMS = ("formal_refreshed", "release_prepared", "deployed", "online_verified")
PRIVATE_MARKERS = ("obsidian://", "notion://", "E:\\obsidian", "C:\\Users\\", "/Users/", "/home/")
TEXT_SUFFIXES = {".html", ".htm", ".json", ".js", ".css", ".md", ".txt", ".svg"}


class VerificationError(Exception):
    """A safe, user-facing verification failure (never includes credentials)."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_sha256(root: Path) -> str:
    files: list[dict[str, Any]] = []
    for path in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda item: item.as_posix()):
        files.append({"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": _sha256(path)})
    canonical = json.dumps(files, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _safe_rel(value: Any) -> str | None:
    if not isinstance(value, str) or not value or "\\" in value:
        return None
    p = PurePosixPath(value)
    if p.is_absolute() or ".." in p.parts or "." in p.parts:
        return None
    return p.as_posix()


def _read_manifest(root: Path) -> dict[str, Any]:
    path = root / MANIFEST_NAME
    if not path.is_file():
        raise VerificationError("发布目录缺少 release-manifest.json")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError("release-manifest.json 无法解析") from exc
    if not isinstance(value, dict):
        raise VerificationError("release-manifest.json 顶层必须是对象")
    return value


def _actual_files(root: Path) -> dict[str, Path]:
    return {p.relative_to(root).as_posix(): p for p in root.rglob("*") if p.is_file()}


def _privacy_problems(root: Path) -> list[str]:
    problems: list[str] = []
    for rel, path in _actual_files(root).items():
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            continue
        lowered = text.lower()
        if any(marker.lower() in lowered for marker in PRIVATE_MARKERS):
            problems.append("发布文件含私人路径或 Obsidian/Notion 链接: " + rel)
    return problems


def _validate_release(root: Path, expected_mode: str | None = None) -> tuple[dict[str, Any], str, str, str]:
    root = root.resolve()
    if not root.is_dir():
        raise VerificationError("release-dir 不存在或不是目录")
    manifest = _read_manifest(root)
    if manifest.get("schema") != MANIFEST_SCHEMA or manifest.get("kind") != MANIFEST_KIND or manifest.get("producer") != MANIFEST_PRODUCER:
        raise VerificationError("release manifest 不是受管的 schema 2 发布清单")
    mode = manifest.get("release_mode")
    if mode not in RELEASE_MODES:
        raise VerificationError("release manifest 的发布模式无效")
    if expected_mode and mode != expected_mode:
        raise VerificationError("发布模式与 expected mode 不一致")
    if manifest.get("entrypoint") != "index.html" or manifest.get("fresh_staging") is not True:
        raise VerificationError("发布清单未声明固定入口或 fresh staging")
    index = root / "index.html"
    if not index.is_file():
        raise VerificationError("发布目录缺少 index.html")
    allowed = manifest.get("allowed_files")
    entries = manifest.get("files")
    if not isinstance(allowed, list) or not isinstance(entries, list):
        raise VerificationError("发布清单缺少 allowed_files/files")
    allowed_rel = [_safe_rel(x) for x in allowed]
    if any(x is None for x in allowed_rel) or len(set(allowed_rel)) != len(allowed_rel):
        raise VerificationError("发布清单包含非法或重复文件路径")
    actual = _actual_files(root)
    if set(allowed_rel) != set(actual):
        raise VerificationError("发布目录文件与 manifest allowed_files 不一致")
    by_path: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or _safe_rel(entry.get("path")) is None or not re.fullmatch(r"[0-9a-f]{64}", str(entry.get("sha256", ""))):
            raise VerificationError("发布清单文件哈希条目无效")
        rel = _safe_rel(entry["path"])
        if rel in by_path:
            raise VerificationError("发布清单含重复哈希条目")
        by_path[rel] = entry
    expected_artifacts = set(allowed_rel) - {MANIFEST_NAME}
    if set(by_path) != expected_artifacts:
        raise VerificationError("发布清单哈希列表与 allowed_files 不一致")
    for rel, entry in by_path.items():
        path = actual.get(rel)
        if path is None or _sha256(path) != entry["sha256"] or path.stat().st_size != entry.get("bytes"):
            raise VerificationError("发布文件与 manifest 哈希不一致: " + rel)
    if mode == "public-anonymized":
        problems = _privacy_problems(root)
        if problems:
            raise VerificationError(problems[0])
    html = index.read_text(encoding="utf-8-sig")
    blocks = re.findall(r'<script id="workbench-data" type="application/json">([\s\S]*?)</script>', html)
    if len(blocks) != 1:
        raise VerificationError("index.html 的 workbench-data 数量异常")
    try:
        data = json.loads(blocks[0])
    except json.JSONDecodeError as exc:
        raise VerificationError("index.html 的 workbench-data 无法解析") from exc
    release = data.get("release") if isinstance(data, dict) else None
    if not isinstance(release, dict) or release.get("mode") != mode:
        raise VerificationError("页面模式与 release manifest 不一致")
    if mode == "public-anonymized" and (release.get("contains_personal_data") is True or release.get("anonymized") is not True):
        raise VerificationError("公开发布页面的匿名标记不正确")
    return manifest, html, _sha256(index), _sha256(root / MANIFEST_NAME)


def _identity(manifest: dict[str, Any], html: str) -> str | None:
    for key in ("release_version", "version", "release_id", "revision"):
        if manifest.get(key) is not None:
            return str(manifest[key])
    # A producer may put the version in the page data; do not invent one.
    match = re.search(r'"(?:release_version|version|release_id|revision)"\s*:\s*"([^"]+)"', html)
    return match.group(1) if match else None


def _receipt(path: Path | None, claims: dict[str, bool], result: dict[str, Any]) -> None:
    if not path:
        return
    payload = {"kind": "lzheng_fitness_workbench_cloudbase_receipt", "claims": {k: bool(claims.get(k, False)) for k in CLAIMS}, "result": result}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _input_claims(path: Path | None) -> dict[str, bool]:
    """Carry only upstream local evidence; remote claims need new proof per release."""
    claims = {k: False for k in CLAIMS}
    if not path or not path.is_file():
        return claims
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        source = payload.get("claims", {}) if isinstance(payload, dict) else {}
        if isinstance(source, dict):
            for key in ("formal_refreshed", "release_prepared"):
                claims[key] = source.get(key) is True
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        # A malformed old receipt is not evidence; the new receipt will be clear.
        pass
    return claims


def verify_release(release_dir: str | Path, expected_mode: str | None = None) -> dict[str, Any]:
    """Validate a local release; callable by a Python orchestrator."""
    manifest, html, index_sha, manifest_sha = _validate_release(Path(release_dir), expected_mode)
    return {"release_dir": str(Path(release_dir).resolve()), "mode": manifest["release_mode"], "index_sha256": index_sha, "manifest_sha256": manifest_sha, "version": _identity(manifest, html), "release_prepared": True}


def verify_online(release_dir: str | Path, base_url: str, expected_mode: str | None = None, timeout: float = 15.0) -> dict[str, Any]:
    """GET the online index and require exact manifest hash, mode, and privacy."""
    local = verify_release(release_dir, expected_mode)
    def fetch(name: str) -> tuple[bytes, int]:
        request = Request(base_url.rstrip("/") + "/" + name, headers={"User-Agent": "Lzheng-Fitness-Release-Verifier/1"}, method="GET")
        try:
            with urlopen(request, timeout=timeout) as response:
                body = response.read()
                status = getattr(response, "status", 200)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise VerificationError("线上 HTTP GET 失败") from exc
        if status < 200 or status >= 300:
            raise VerificationError("线上 HTTP 状态不是 2xx")
        return body, status

    body, status = fetch("index.html")
    try:
        online_html = body.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise VerificationError("线上 index.html 不是 UTF-8") from exc
    online_sha = hashlib.sha256(body).hexdigest()
    if online_sha != local["index_sha256"]:
        raise VerificationError("线上 index.html 哈希与 release manifest 不一致")
    online_manifest, manifest_status = fetch(MANIFEST_NAME)
    online_manifest_sha = hashlib.sha256(online_manifest).hexdigest()
    if online_manifest_sha != local["manifest_sha256"]:
        raise VerificationError("线上 release-manifest.json 哈希与本地发布清单不一致")
    if any(marker.lower() in online_html.lower() for marker in PRIVATE_MARKERS) and local["mode"] == "public-anonymized":
        raise VerificationError("线上页面含私人路径或 Obsidian/Notion 链接")
    if local["version"] and local["version"] not in online_html:
        raise VerificationError("线上页面缺少 manifest 版本标识")
    local.update({"base_url": base_url, "online_index_sha256": online_sha, "online_manifest_sha256": online_manifest_sha, "http_status": status, "manifest_http_status": manifest_status, "online_verified": True})
    return local


def _validate_rollback_deployment(config_path: Path | None, deployment_receipt_path: Path | None, previous: dict[str, Any], previous_dir: Path, env_id: str, cloud_path: str) -> None:
    if not config_path or not config_path.is_file() or not deployment_receipt_path or not deployment_receipt_path.is_file():
        raise VerificationError("回滚上传必须提供原部署的零成本配置与发布回执")
    try:
        config = json.loads(config_path.read_text(encoding="utf-8-sig"))
        receipt = json.loads(deployment_receipt_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerificationError("回滚的零成本配置或发布回执无法解析") from exc
    if not isinstance(config, dict) or config.get("accepted_free_tier") is not True or config.get("free_tier_env_id") != env_id or not isinstance(config.get("free_tier_checked_at"), str) or not config.get("free_tier_checked_at"):
        raise VerificationError("回滚零成本配置未绑定当前 env_id；请先在控制台核验费用")
    claims = receipt.get("claims", {}) if isinstance(receipt, dict) else {}
    cloudbase = receipt.get("evidence", {}).get("cloudbase") if isinstance(receipt, dict) and isinstance(receipt.get("evidence"), dict) else None
    if not isinstance(cloudbase, dict) or claims.get("deployed") is not True or cloudbase.get("deployed") is not True:
        raise VerificationError("回滚发布回执未证明原版本已经成功部署")
    if cloudbase.get("env_id") != env_id or cloudbase.get("cloud_path") != cloud_path:
        raise VerificationError("回滚 env_id 或 cloud_path 与原部署回执不一致")
    if cloudbase.get("manifest_sha256") != previous.get("manifest_sha256") or cloudbase.get("tree_sha256") != _tree_sha256(previous_dir):
        raise VerificationError("回滚副本哈希与原部署回执不一致")


def rollback_release(current_dir: str | Path, previous_dir: str | Path, expected_mode: str | None = None, *, deploy: bool = False, execute: bool = False, env_id: str | None = None, cloud_path: str | None = None, config_path: Path | None = None, deployment_receipt_path: Path | None = None, tcb_bin: str | None = None) -> dict[str, Any]:
    """Validate a previous release and optionally invoke the existing TCB deploy command."""
    if expected_mode not in {None, "public-anonymized"}:
        raise VerificationError("CloudBase 回滚只允许 public-anonymized 发布副本")
    previous = verify_release(previous_dir, "public-anonymized")
    if Path(current_dir).resolve() == Path(previous_dir).resolve():
        raise VerificationError("rollback source 不能与当前发布目录相同")
    result: dict[str, Any] = {"rollback_source": previous["release_dir"], "mode": previous["mode"], "release_prepared": True, "deployed": False}
    if deploy:
        if not execute:
            raise VerificationError("回滚上传必须显式指定 --execute")
        if not env_id or not cloud_path or not cloud_path.startswith("/"):
            raise VerificationError("回滚上传必须指定原 env_id 与 cloud_path")
        _validate_rollback_deployment(config_path, deployment_receipt_path, previous, Path(previous_dir).resolve(), env_id, cloud_path)
        resolved_tcb = shutil.which(tcb_bin or "tcb") or (tcb_bin or "tcb")
        command = [resolved_tcb, "hosting", "deploy", str(Path(previous_dir).resolve()), cloud_path, "-e", env_id]
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
        if completed.returncode != 0:
            raise VerificationError("tcb hosting deploy 回滚失败")
        result.update({"deployed": True, "env_id": env_id, "cloud_path": cloud_path, "online_verified": False})
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify or explicitly roll back a manifest-backed CloudBase workbench release")
    parser.add_argument("--release-dir", required=True)
    parser.add_argument("--base-url")
    parser.add_argument("--receipt")
    parser.add_argument("--expected-mode", choices=sorted(RELEASE_MODES))
    parser.add_argument("--verify-online", action="store_true", help="explicitly perform a real HTTP GET")
    parser.add_argument("--rollback", action="store_true", help="explicitly validate a previous release for rollback")
    parser.add_argument("--previous-release-dir")
    parser.add_argument("--deploy", action="store_true", help="after rollback validation, invoke existing tcb hosting deploy")
    parser.add_argument("--env-id", help="CloudBase environment id; never printed")
    parser.add_argument("--cloud-path", help="回滚时必须是原部署的静态托管路径")
    parser.add_argument("--config", help="回滚上传所用的原零成本非敏感配置")
    parser.add_argument("--deployment-receipt", help="原成功发布回执，用于绑定 env/path/哈希")
    parser.add_argument("--tcb-bin", help="仅供受控测试或明确的本地 CLI 路径；不会写入回执")
    parser.add_argument("--execute", action="store_true", help="回滚上传的明确授权")
    args = parser.parse_args(argv)
    receipt_path = Path(args.receipt) if args.receipt else None
    claims = _input_claims(receipt_path)
    try:
        if args.rollback:
            if not args.previous_release_dir:
                raise VerificationError("--rollback 必须指定 --previous-release-dir")
            result = rollback_release(args.release_dir, args.previous_release_dir, args.expected_mode, deploy=args.deploy, execute=args.execute, env_id=args.env_id, cloud_path=args.cloud_path, config_path=Path(args.config) if args.config else None, deployment_receipt_path=Path(args.deployment_receipt) if args.deployment_receipt else None, tcb_bin=args.tcb_bin)
            claims["release_prepared"] = True
            claims["deployed"] = bool(result.get("deployed"))
        elif args.verify_online:
            if not args.base_url:
                raise VerificationError("--verify-online 必须指定 --base-url")
            verify_release(args.release_dir, args.expected_mode)
            claims["release_prepared"] = True
            result = verify_online(args.release_dir, args.base_url, args.expected_mode)
            claims["online_verified"] = True
        else:
            result = verify_release(args.release_dir, args.expected_mode)
            claims["release_prepared"] = True
        _receipt(receipt_path, claims, {"status": "PASS", **result})
        print(json.dumps({"status": "PASS", "claims": claims, **result}, ensure_ascii=False))
        return 0
    except VerificationError as exc:
        _receipt(receipt_path, claims, {"status": "FAIL", "error": str(exc)})
        print(json.dumps({"status": "FAIL", "claims": claims, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
