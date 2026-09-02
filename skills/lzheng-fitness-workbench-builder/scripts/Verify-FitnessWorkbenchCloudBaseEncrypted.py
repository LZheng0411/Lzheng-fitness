#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify local and online bytes for a private-encrypted CloudBase release."""

from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
DEPLOY_SCRIPT = HERE / "Deploy-FitnessWorkbenchCloudBaseEncrypted.py"
PREPARE_SCRIPT = HERE / "Prepare-FitnessWorkbenchEncryptedRelease.py"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载本地加密发布模块")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


deploy_module = load(DEPLOY_SCRIPT, "lzheng_encrypted_deploy")
prepare_module = load(PREPARE_SCRIPT, "lzheng_encrypted_prepare")


class VerifyError(RuntimeError):
    pass


def decrypt_local(release: Path, secret_file: Path) -> dict[str, Any]:
    try:
        payload = json.loads((release / "private-payload.json").read_text(encoding="utf-8-sig"))
        passphrase = prepare_module.load_secret(secret_file)
        salt = base64.b64decode(payload["salt"], validate=True)
        nonce = base64.b64decode(payload["nonce"], validate=True)
        ciphertext = base64.b64decode(payload["ciphertext"], validate=True)
        key = prepare_module.derive_key(passphrase, salt)
        plain = prepare_module.AESGCM(key).decrypt(nonce, ciphertext, payload["aad"].encode("ascii"))
        html = plain.decode("utf-8")
    except Exception as exc:
        raise VerifyError("本机 DPAPI 私人密码无法解密发布内容") from exc
    if len(re.findall(r'<script id="workbench-data" type="application/json">', html)) != 1:
        raise VerifyError("解密后的私人工作台 workbench-data 数量异常")
    return {"plaintext_bytes": len(plain), "decrypted_workbench_valid": True}


def fetch(url: str, timeout: float) -> tuple[bytes, int]:
    request = Request(url, headers={"User-Agent": "Lzheng-Fitness-Encrypted-Verifier/1", "Cache-Control": "no-cache"}, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read()
            status = getattr(response, "status", 200)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise VerifyError("线上加密发布 HTTP GET 失败") from exc
    if status < 200 or status >= 300:
        raise VerifyError("线上加密发布 HTTP 状态不是 2xx")
    return body, status


def verify(release: Path, secret_file: Path, base_url: str | None = None, timeout: float = 20.0) -> dict[str, Any]:
    release = release.resolve()
    try:
        local = deploy_module.validate_release(release)
    except Exception as exc:
        raise VerifyError(str(exc)) from exc
    result: dict[str, Any] = {"release_dir": str(release), "mode": "private-encrypted", "manifest_sha256": local["manifest_sha256"], "payload_sha256": local["payload_sha256"], "index_sha256": local["index_sha256"], **decrypt_local(release, secret_file), "online_verified": False}
    if base_url:
        statuses: dict[str, int] = {}
        for name in ("index.html", "private-payload.json", "release-manifest.json"):
            body, status = fetch(base_url.rstrip("/") + "/" + name + "?verify=" + local["manifest_sha256"][:16], timeout)
            expected = (release / name).read_bytes()
            if body != expected:
                raise VerifyError("线上文件字节与本地加密发布不一致: " + name)
            statuses[name] = status
        result.update({"base_url": base_url, "http_status": statuses, "online_verified": True})
    return result


def write_receipt(path: Path | None, claims: dict[str, bool], result: dict[str, Any]) -> None:
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name("." + path.name + ".tmp")
    staging.write_text(json.dumps({"schema": 1, "kind": "lzheng_fitness_workbench_encrypted_verify_receipt", "claims": claims, "result": result}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(staging, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a private-encrypted CloudBase workbench release")
    parser.add_argument("--release-dir", required=True)
    parser.add_argument("--secret-file", default=str(prepare_module.default_secret_file()))
    parser.add_argument("--base-url")
    parser.add_argument("--verify-online", action="store_true")
    parser.add_argument("--receipt")
    args = parser.parse_args(argv)
    claims = {"formal_refreshed": False, "release_prepared": False, "deployed": False, "online_verified": False}
    receipt = Path(args.receipt).expanduser().absolute() if args.receipt else None
    try:
        if args.verify_online and not args.base_url:
            raise VerifyError("--verify-online 必须指定 --base-url")
        result = verify(Path(args.release_dir), Path(args.secret_file), args.base_url if args.verify_online else None)
        claims["release_prepared"] = True
        claims["online_verified"] = result["online_verified"] is True
        result = {"status": "PASS", **result}
        write_receipt(receipt, claims, result)
        print(json.dumps({"claims": claims, **result}, ensure_ascii=False))
        return 0
    except (VerifyError, OSError, ValueError) as exc:
        result = {"status": "FAIL", "error": str(exc)}
        write_receipt(receipt, claims, result)
        print(json.dumps({"claims": claims, **result}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
