#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify local and online bytes for a public personal CloudBase release."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
DEPLOY = HERE / "Deploy-FitnessWorkbenchCloudBasePublicPersonal.py"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载公开个人版验证模块")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


deploy_module = load(DEPLOY, "lzheng_public_personal_verify_deploy")


class VerifyError(RuntimeError):
    pass


def fetch(url: str, timeout: float = 20.0) -> tuple[bytes, int]:
    request = Request(url, headers={"User-Agent": "Lzheng-Fitness-Public-Personal-Verifier/1", "Cache-Control": "no-cache"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read(), getattr(response, "status", 200)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise VerifyError("线上公开个人版 HTTP GET 失败") from exc


def verify(
    release: Path,
    base_url: str | None = None,
    attempts: int = 20,
    retry_delay: float = 5.0,
) -> dict:
    release = release.resolve()
    try:
        local = deploy_module.validate_release(release)
    except Exception as exc:
        raise VerifyError(str(exc)) from exc
    result = {"release_dir": str(release), "mode": "public-personal-authorized", "manifest_sha256": local["manifest_sha256"], "index_sha256": local["index_sha256"], "online_verified": False}
    if base_url:
        if attempts < 1 or retry_delay < 0:
            raise VerifyError("线上核验重试参数无效")
        last_error: VerifyError | None = None
        for attempt in range(1, attempts + 1):
            try:
                statuses = {}
                for name in local["files"]:
                    body, status = fetch(base_url.rstrip("/") + "/" + name + "?verify=" + local["manifest_sha256"][:16])
                    if status < 200 or status >= 300 or body != (release / name).read_bytes():
                        raise VerifyError("线上公开个人版文件与本地不一致: " + name)
                    statuses[name] = status
                result.update({"base_url": base_url, "http_status": statuses, "online_verified": True, "attempts_used": attempt})
                break
            except VerifyError as exc:
                last_error = exc
                if attempt < attempts:
                    time.sleep(retry_delay)
        else:
            raise last_error or VerifyError("线上公开个人版核验失败")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a public personal CloudBase workbench")
    parser.add_argument("--release-dir", required=True)
    parser.add_argument("--base-url")
    parser.add_argument("--verify-online", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.verify_online and not args.base_url:
            raise VerifyError("--verify-online 必须指定 --base-url")
        result = verify(Path(args.release_dir), args.base_url if args.verify_online else None)
        print(json.dumps({"status": "PASS", **result}, ensure_ascii=False))
        return 0
    except (VerifyError, OSError, ValueError) as exc:
        print(json.dumps({"status": "FAIL", "online_verified": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
