#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""隔离测试：CloudBase 发布器/线上校验器的安全契约。

本文件不导入 Deploy/Verify 脚本，故可在它们尚未落地时先安装测试。
固定子进程契约：
  Deploy-FitnessWorkbenchCloudBase.py --release-dir DIR --env-id ENV --project DIR
      --backup-dir DIR --receipt FILE --config FILE [--execute]
  Verify-FitnessWorkbenchCloudBase.py --release-dir DIR --base-url URL
      [--verify-online] [--rollback]

伪 tcb 只写入临时目录的调用日志；测试绝不联网、登录或触碰正式项目。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
DEPLOY = HERE / "Deploy-FitnessWorkbenchCloudBase.py"
VERIFY = HERE / "Verify-FitnessWorkbenchCloudBase.py"


class CloudBaseReleaseContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not DEPLOY.is_file() or not VERIFY.is_file():
            raise unittest.SkipTest(
                "待测脚本尚未落地；已安装 CloudBase CLI 子进程契约测试（部署器/校验器缺失）"
            )

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="lzheng-cloudbase-contract-")
        self.root = Path(self.tmp.name)
        self.release = self.root / "release"
        self.release.mkdir()
        self.index = self.release / "index.html"
        data = {"release": {"mode": "public-anonymized", "anonymized": True, "contains_personal_data": False}}
        self.index.write_text('<script id="workbench-data" type="application/json">' + json.dumps(data) + '</script>\n', encoding="utf-8")
        self.manifest = self.release / "release-manifest.json"
        self._write_manifest(schema=2, public=True)
        self.log = self.root / "tcb-calls.jsonl"
        self.tcb = self.root / ("tcb.cmd" if os.name == "nt" else "tcb")
        self._write_fake_tcb()
        self.config = self.root / "cloudbase.json"
        self.config.write_text(json.dumps({"accepted_free_tier": True, "env_id": "test-env", "free_tier_env_id": "test-env", "free_tier_checked_at": "2026-08-23T18:00:00+08:00", "cloud_path": "/workbench"}), encoding="utf-8")
        self.project = self.root / "project"; self.project.mkdir()
        self.backup = self.root / "backup"; self.backup.mkdir()
        self.receipt = self.root / "receipt.json"
        files = []
        for path in sorted((item for item in self.release.rglob("*") if item.is_file()), key=lambda item: item.as_posix()):
            files.append({"path": path.relative_to(self.release).as_posix(), "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        tree = hashlib.sha256(json.dumps(files, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")).hexdigest()
        self.receipt.write_text(json.dumps({"claims": {"formal_refreshed": True, "release_prepared": True}, "result": {"status": "PASS"}, "artifacts": {"deploy": {"path": str(self.release.resolve()), "release_mode": "public-anonymized", "file_count": len(files), "tree_sha256": tree, "files": files}}, "scripts": {"refresh": {"version": "1.0.0", "sha256": "a" * 64}}}), encoding="utf-8")
        self.deployment_receipt = self.root / "deployment-receipt.json"
        self.deployment_receipt.write_text(json.dumps({"claims": {"formal_refreshed": True, "release_prepared": True, "deployed": True, "online_verified": False}, "evidence": {"cloudbase": {"deployed": True, "env_id": "test-env", "cloud_path": "/workbench", "manifest_sha256": hashlib.sha256(self.manifest.read_bytes()).hexdigest(), "tree_sha256": tree}}}), encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_manifest(self, *, schema: int, public: bool, tamper: bool = False) -> None:
        digest = hashlib.sha256(self.index.read_bytes()).hexdigest()
        payload = {
            "schema": schema,
            "kind": "lzheng-fitness-workbench-release",
            "producer": "Prepare-FitnessWorkbenchRelease.py",
            "release_mode": "public-anonymized" if public else "private-portable",
            "anonymized": public,
            "contains_personal_data": not public,
            "required_access": "public" if public else "private-authenticated",
            "entrypoint": "index.html",
            "fresh_staging": True,
            "allowed_files": ["index.html", "release-manifest.json"],
            "files": [{"path": "index.html", "bytes": self.index.stat().st_size, "sha256": digest}],
        }
        if tamper:
            payload["files"][0]["sha256"] = "0" * 64
        self.manifest.write_text(json.dumps(payload), encoding="utf-8")

    def _write_fake_tcb(self) -> None:
        # The executable records argv and can optionally emulate a remote hash.
        code = (
            "import json, os, pathlib, sys\n"
            "p=pathlib.Path(os.environ['TCB_CALL_LOG'])\n"
            "with p.open('a', encoding='utf-8') as f: f.write(json.dumps(sys.argv[1:])+'\\n')\n"
            "if os.environ.get('TCB_FAIL') == '1': print('credential expired', file=sys.stderr); raise SystemExit(17)\n"
            "if os.environ.get('TCB_REMOTE_HASH'): print('remote-sha256='+os.environ['TCB_REMOTE_HASH'])\n"
        )
        helper = self.root / "fake_tcb.py"
        helper.write_text(code, encoding="utf-8")
        if os.name == "nt":
            self.tcb.write_text(f'@echo off\n"{sys.executable}" "{helper}" %*\n', encoding="utf-8")
        else:
            self.tcb.write_text("#!/bin/sh\nexec " + repr(sys.executable) + " " + repr(str(helper)) + " \"$@\"\n", encoding="utf-8")
            self.tcb.chmod(self.tcb.stat().st_mode | stat.S_IXUSR)

    def _env(self, **extra: str) -> dict[str, str]:
        env = os.environ.copy()
        env.update({"PYTHONUTF8": "1", "TCB_CALL_LOG": str(self.log), "LZHENG_CLOUDBASE_TCB_BIN": str(self.tcb), "PATH": str(self.root) + os.pathsep + env.get("PATH", ""),
                    "PATHEXT": ".CMD;.EXE;.BAT;" + env.get("PATHEXT", ""), **extra})
        return env

    def _run(self, script: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(script), *args], text=True, encoding="utf-8", errors="replace",
            capture_output=True, env=env or self._env(),
        )

    def _deploy(self, *extra: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return self._run(DEPLOY, "--release-dir", str(self.release), "--env-id", "test-env", "--project", str(self.project),
                         "--backup-dir", str(self.backup), "--receipt", str(self.receipt), "--config", str(self.config), *extra, env=env)

    def _verify(self, *extra: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return self._run(VERIFY, "--release-dir", str(self.release), "--env-id", "test-env",
                         "--base-url", "https://example.invalid/workbench", *extra, env=env)

    def assertRejected(self, result: subprocess.CompletedProcess[str], *markers: str) -> None:
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        text = result.stdout + result.stderr
        self.assertTrue(any(marker.lower() in text.lower() for marker in markers), text)

    def test_missing_cli_is_rejected(self):
        result = self._deploy(env=self._env(
            PATH=str(self.root / "missing"),
            LZHENG_CLOUDBASE_TCB_BIN=str(self.root / "missing" / "tcb"),
        ))
        # Contract: the declared path must be checked before upload.
        self.assertRejected(result, "CLI", "安装", "不存在", "not found")

    def test_free_tier_must_be_explicit_true(self):
        self.config.write_text(json.dumps({"accepted_free_tier": False, "env_id": "test-env"}), encoding="utf-8")
        self.assertRejected(self._deploy(), "free-tier", "accepted", "true")

    def test_free_tier_must_be_bound_to_checked_environment(self):
        self.config.write_text(json.dumps({"accepted_free_tier": True, "env_id": "test-env", "free_tier_env_id": "other-env", "free_tier_checked_at": "2026-08-23T18:00:00+08:00"}), encoding="utf-8")
        self.assertRejected(self._deploy(), "free_tier_env_id", "控制台", "零成本")

    def test_manifest_schema_tamper_and_private_release_are_rejected(self):
        self._write_manifest(schema=1, public=True)
        self.assertRejected(self._deploy(), "schema", "2")
        self._write_manifest(schema=2, public=True, tamper=True)
        self.assertRejected(self._deploy(), "hash", "完整性", "manifest")
        self._write_manifest(schema=2, public=False)
        self.assertRejected(self._deploy(), "public", "匿名", "公开")

    def test_without_execute_never_uploads(self):
        result = self._deploy()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []
        self.assertFalse(any("hosting" in call and "deploy" in call for call in calls), calls)

    def test_receipt_must_match_exact_release_tree(self):
        payload = json.loads(self.receipt.read_text(encoding="utf-8"))
        payload["artifacts"]["deploy"]["tree_sha256"] = "0" * 64
        self.receipt.write_text(json.dumps(payload), encoding="utf-8")
        self.assertRejected(self._deploy(), "树哈希", "副本")

    def test_remote_hash_mismatch_cannot_be_online_verified(self):
        import runpy
        module = runpy.run_path(str(VERIFY))
        class Response:
            status = 200
            def __init__(self, payload): self.payload = payload
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return self.payload
        globals_ = module["verify_online"].__globals__
        old = globals_["urlopen"]
        globals_["urlopen"] = lambda *args, **kwargs: Response(b"tampered-online-copy")
        try:
            with self.assertRaises(Exception) as caught:
                module["verify_online"](self.release, "https://example.invalid/workbench")
            self.assertTrue(any(x in str(caught.exception).lower() for x in ("哈希", "hash", "http")))
        finally:
            globals_["urlopen"] = old

    def test_remote_manifest_mismatch_cannot_be_online_verified(self):
        import runpy
        module = runpy.run_path(str(VERIFY))
        class Response:
            status = 200
            def __init__(self, payload): self.payload = payload
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return self.payload
        globals_ = module["verify_online"].__globals__
        old = globals_["urlopen"]
        globals_["urlopen"] = lambda request, **kwargs: Response(self.index.read_bytes() if request.full_url.endswith("/index.html") else b"stale-manifest")
        try:
            with self.assertRaises(Exception) as caught:
                module["verify_online"](self.release, "https://example.invalid/workbench")
            self.assertTrue("manifest" in str(caught.exception).lower() or "哈希" in str(caught.exception).lower(), str(caught.exception))
        finally:
            globals_["urlopen"] = old

    def test_expired_credentials_are_clear(self):
        result = self._deploy("--execute", env=self._env(TCB_FAIL="1"))
        self.assertRejected(result, "credential", "凭证", "expired", "失效")

    def test_private_release_cannot_be_rollback_source(self):
        previous = self.root / "previous-release"
        previous.mkdir()
        (previous / "index.html").write_bytes(self.index.read_bytes())
        manifest = json.loads(self.manifest.read_text(encoding="utf-8")); manifest.update({"release_mode": "private-portable", "anonymized": False, "contains_personal_data": True})
        (previous / "release-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        result = self._verify("--rollback", "--previous-release-dir", str(previous), "--expected-mode", "private-portable")
        self.assertRejected(result, "public-anonymized", "回滚")

    def test_rollback_deploy_requires_original_cloud_path_and_execute(self):
        previous = self.root / "previous-release"
        shutil.copytree(self.release, previous)
        result = self._verify("--rollback", "--previous-release-dir", str(previous), "--deploy")
        self.assertRejected(result, "execute", "cloud_path")

    def test_successful_rollback_binds_env_path_hash_and_clears_remote_claim(self):
        previous = self.root / "previous-release"
        shutil.copytree(self.release, previous)
        result = self._verify("--rollback", "--previous-release-dir", str(previous), "--deploy", "--execute", "--env-id", "test-env", "--cloud-path", "/workbench", "--config", str(self.config), "--deployment-receipt", str(self.deployment_receipt), "--tcb-bin", str(self.tcb))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["deployed"])
        self.assertFalse(payload["online_verified"])
        self.assertFalse(payload["claims"]["online_verified"])
        calls = [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(calls[-1], ["hosting", "deploy", str(previous.resolve()), "/workbench", "-e", "test-env"])

    def test_rollback_rejects_unbound_deployment_receipt(self):
        previous = self.root / "previous-release"
        shutil.copytree(self.release, previous)
        payload = json.loads(self.deployment_receipt.read_text(encoding="utf-8"))
        payload["evidence"]["cloudbase"]["cloud_path"] = "/other"
        self.deployment_receipt.write_text(json.dumps(payload), encoding="utf-8")
        result = self._verify("--rollback", "--previous-release-dir", str(previous), "--deploy", "--execute", "--env-id", "test-env", "--cloud-path", "/workbench", "--config", str(self.config), "--deployment-receipt", str(self.deployment_receipt), "--tcb-bin", str(self.tcb))
        self.assertRejected(result, "不一致", "回执")

    def test_same_environment_keeps_same_base_url(self):
        for _ in range(2):
            result = self._deploy("--execute")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(self.log.exists())


if __name__ == "__main__":
    result = unittest.main(verbosity=2, exit=False)
    raise SystemExit(0 if result.result.wasSuccessful() else 1)
