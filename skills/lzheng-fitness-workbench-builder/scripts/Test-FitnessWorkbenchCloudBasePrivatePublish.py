#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Isolated state-machine tests for the unified private CloudBase publisher."""

from __future__ import annotations

import contextlib
import datetime as dt
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
PUBLISH = HERE / "Publish-FitnessWorkbenchCloudBasePrivate.py"


def load_module():
    spec = importlib.util.spec_from_file_location("lzheng_private_publish_test", PUBLISH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load private publisher")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PrivatePublishStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module()
        self.temp = tempfile.TemporaryDirectory(prefix="lzheng-private-publish-")
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        (self.project / "健身工作台.html").write_text("<!doctype html>", encoding="utf-8")
        stamp = dt.datetime.now().astimezone().isoformat(timespec="seconds")
        self.notion = self.root / "notion.json"
        self.notion.write_text(json.dumps({"sync_mode": "incremental", "source_queried_at": stamp, "snapshot_generated_at": stamp}), encoding="utf-8")
        self.config = self.root / "configs" / "config.json"
        self.config.parent.mkdir()
        self.config.write_text(json.dumps({"env_id": "free-env", "cloud_path": "/fitness-private"}), encoding="utf-8")
        self.secret = self.root / "secrets" / "local-secret.json"
        self.secret.parent.mkdir()
        self.secret.write_text("{}", encoding="utf-8")
        self.private = self.root / "private"
        self.encrypted = self.root / "encrypted"
        self.history = self.root / "history"
        self.backup = self.root / "backup"
        self.receipt = self.root / "receipts" / "publish.json"
        self.deploy_calls: list[list[str]] = []

    def tearDown(self) -> None:
        self.temp.cleanup()

    def argv(self, *, execute: bool = False, verify_online: bool = False) -> list[str]:
        args = ["--project", str(self.project), "--notion", str(self.notion), "--notion-mode", "incremental", "--private-release-dir", str(self.private), "--encrypted-release-dir", str(self.encrypted), "--history-dir", str(self.history), "--backup-dir", str(self.backup), "--receipt", str(self.receipt), "--config", str(self.config), "--secret-file", str(self.secret)]
        if execute:
            args.append("--execute")
        if verify_online:
            args.extend(["--verify-online", "--base-url", "https://example.invalid/fitness-private/"])
        return args

    def run_case(self, cloudbase: dict, *, execute: bool = False, verify_online: bool = False, online_error: bool = False, encryption_error: bool = False):
        def fake_run(command: list[str], label: str):
            if str(self.module.REFRESH) in command:
                path = Path(command[command.index("--receipt") + 1])
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({"result": {"status": "PASS"}, "claims": {"formal_refreshed": True, "release_prepared": True}}), encoding="utf-8")
                return {"status": "PASS"}
            if str(self.module.PREPARE) in command:
                if encryption_error:
                    raise self.module.StageError("encryption failed", {"status": "FAIL"})
                path = Path(command[command.index("--receipt") + 1])
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({"kind": "lzheng_fitness_workbench_encrypted_release_receipt", "claims": {"release_prepared": True}, "result": {"status": "PASS", "release_dir": str(self.encrypted), "mode": "private-encrypted", "manifest_sha256": "m", "payload_sha256": "p"}}), encoding="utf-8")
                return {"status": "PASS"}
            if str(self.module.DEPLOY) in command:
                self.deploy_calls.append(command)
                if cloudbase.get("raise_stage"):
                    raise self.module.StageError("remote tree mismatch", {"deployed": True, "online_verified": False, "remote_tree_exact": False})
                return cloudbase
            raise AssertionError(label)

        def fake_verify(_release, _secret, base_url=None):
            if base_url and online_error:
                raise self.module.verify_module.VerifyError("remote mismatch")
            return {"online_verified": bool(base_url), "decrypted_workbench_valid": True, "manifest_sha256": "m", "payload_sha256": "p"}

        with mock.patch.object(self.module, "run", side_effect=fake_run), mock.patch.object(self.module, "archive_release", return_value={"path": "archive", "manifest_sha256": "m", "payload_sha256": "p"}), mock.patch.object(self.module.verify_module, "verify", side_effect=fake_verify), contextlib.redirect_stdout(io.StringIO()):
            code = self.module.main(self.argv(execute=execute, verify_online=verify_online))
        return code, json.loads(self.receipt.read_text(encoding="utf-8"))

    def test_preflight_has_two_local_claims_and_no_execute(self):
        code, receipt = self.run_case({"deployed": False, "online_verified": False, "status": "preflight_ready"})
        self.assertEqual(code, 0)
        self.assertEqual(receipt["claims"], {"formal_refreshed": True, "release_prepared": True, "deployed": False, "online_verified": False})
        self.assertNotIn("--execute", self.deploy_calls[0])

    def test_upload_without_online_verification_preserves_boundary(self):
        code, receipt = self.run_case({"deployed": True, "online_verified": False, "remote_tree_exact": True}, execute=True)
        self.assertEqual(code, 0)
        self.assertEqual(receipt["claims"], {"formal_refreshed": True, "release_prepared": True, "deployed": True, "online_verified": False})

    def test_upload_and_online_verification_sets_all_claims(self):
        code, receipt = self.run_case({"deployed": True, "online_verified": False, "remote_tree_exact": True}, execute=True, verify_online=True)
        self.assertEqual(code, 0)
        self.assertTrue(all(receipt["claims"].values()))

    def test_online_mismatch_fails_but_keeps_deployed_true(self):
        code, receipt = self.run_case({"deployed": True, "online_verified": False, "remote_tree_exact": True}, execute=True, verify_online=True, online_error=True)
        self.assertEqual(code, 1)
        self.assertEqual(receipt["result"]["status"], "FAIL")
        self.assertTrue(receipt["claims"]["deployed"])
        self.assertFalse(receipt["claims"]["online_verified"])

    def test_encryption_failure_never_calls_deployer(self):
        code, receipt = self.run_case({}, encryption_error=True)
        self.assertEqual(code, 1)
        self.assertFalse(self.deploy_calls)
        self.assertFalse(receipt["claims"]["deployed"])

    def test_post_upload_remote_tree_mismatch_keeps_deployed_true(self):
        code, receipt = self.run_case({"raise_stage": True}, execute=True)
        self.assertEqual(code, 1)
        self.assertEqual(receipt["result"]["status"], "FAIL")
        self.assertTrue(receipt["claims"]["deployed"])
        self.assertFalse(receipt["claims"]["online_verified"])

    def test_secret_inside_release_scope_is_rejected_before_stages(self):
        self.private.mkdir()
        self.secret = self.private / "secret.json"
        self.secret.write_text("{}", encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            code = self.module.main(self.argv())
        receipt = json.loads(self.receipt.read_text(encoding="utf-8"))
        self.assertEqual(code, 1)
        self.assertIn("私人密钥必须位于私人中间目录之外", receipt["result"]["error"])

    def test_secret_inside_config_directory_is_rejected_before_refresh(self):
        self.secret = self.config.parent / "secret.json"
        self.secret.write_text("{}", encoding="utf-8")
        with mock.patch.object(self.module, "run") as stage_run, contextlib.redirect_stdout(io.StringIO()):
            code = self.module.main(self.argv())
        receipt = json.loads(self.receipt.read_text(encoding="utf-8"))
        self.assertEqual(code, 1)
        self.assertIn("私人密钥必须位于配置目录之外", receipt["result"]["error"])
        stage_run.assert_not_called()

    def test_secret_reparse_path_is_rejected_before_refresh(self):
        with mock.patch.object(self.module.deploy_module, "link_component", return_value=self.secret), mock.patch.object(self.module, "run") as stage_run, contextlib.redirect_stdout(io.StringIO()):
            code = self.module.main(self.argv())
        receipt = json.loads(self.receipt.read_text(encoding="utf-8"))
        self.assertEqual(code, 1)
        self.assertIn("reparse", receipt["result"]["error"])
        stage_run.assert_not_called()


if __name__ == "__main__":
    result = unittest.main(verbosity=2, exit=False)
    raise SystemExit(0 if result.result.wasSuccessful() else 1)
