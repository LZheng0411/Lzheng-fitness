#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Isolated tests for the explicitly public personal workbench release."""

from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import unquote, urlparse
from unittest import mock

HERE = Path(__file__).resolve().parent
PREPARE = HERE / "Prepare-FitnessWorkbenchPublicPersonalRelease.py"
DEPLOY = HERE / "Deploy-FitnessWorkbenchCloudBasePublicPersonal.py"
VERIFY = HERE / "Verify-FitnessWorkbenchCloudBasePublicPersonal.py"
PUBLISH = HERE / "Publish-FitnessWorkbenchCloudBasePublicPersonal.py"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PublicPersonalReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.prepare = load(PREPARE, "public_personal_prepare_test")
        self.deploy = load(DEPLOY, "public_personal_deploy_test")
        self.verify = load(VERIFY, "public_personal_verify_test")
        self.temp = tempfile.TemporaryDirectory(prefix="public-personal-release-")
        self.root = Path(self.temp.name)
        self.source = self.root / "private"
        self.source.mkdir()
        (self.source / "docs").mkdir()
        private_text = "体重67kg Notion私人复盘"
        (self.source / "docs" / "review.html").write_text(private_text, encoding="utf-8")
        (self.source / "index.html").write_text('<script id="workbench-data" type="application/json">{"release":{"mode":"private-portable"},"private":"' + private_text + '"}</script><a href="docs/review.html">review</a>', encoding="utf-8")
        files = []
        for rel in ("index.html", "docs/review.html"):
            path = self.source / rel
            files.append({"path": rel, "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        manifest = {"schema": 2, "kind": "lzheng-fitness-workbench-release", "producer": "Prepare-FitnessWorkbenchRelease.py", "release_mode": "private-portable", "contains_personal_data": True, "required_access": "private-authenticated", "allowed_files": ["index.html", "docs/review.html", "release-manifest.json"], "files": files}
        (self.source / "release-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        self.output = self.root / "public"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_build_is_plaintext_public_and_has_no_password_launcher(self):
        result = self.prepare.build(self.source, self.output)
        self.assertEqual(result["mode"], "public-personal-authorized")
        manifest = json.loads((self.output / "release-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(set(manifest["allowed_files"]), {"index.html", "release-manifest.json", "assets/" + hashlib.sha256((self.source / "docs" / "review.html").read_bytes()).hexdigest()[:16] + ".html"})
        html = (self.output / "index.html").read_text(encoding="utf-8")
        review = next(path for path in self.output.rglob("*.html") if path.name != "index.html")
        self.assertIn("体重67kg", review.read_text(encoding="utf-8"))
        self.assertIn('"user_authorized_public":true', html)
        self.assertNotIn("private-payload.json", html)

    def test_build_serves_url_encoded_plan_link_as_static_file(self):
        plan_rel = "docs/训练计划.html"
        plan = self.source / plan_rel
        plan.write_text("<h1>完整训练计划</h1>", encoding="utf-8")
        (self.source / "docs" / "review.html").unlink()
        index = self.source / "index.html"
        index.write_text(
            '<script id="workbench-data" type="application/json">'
            '{"meta":{"plan_file":"docs/训练计划.html","plan_href":"docs/%E8%AE%AD%E7%BB%83%E8%AE%A1%E5%88%92.html"}}'
            '</script>' + self.prepare.PLAN_LINK_MARKER,
            encoding="utf-8",
        )
        manifest = {
            "schema": 2,
            "kind": "lzheng-fitness-workbench-release",
            "producer": "Prepare-FitnessWorkbenchRelease.py",
            "release_mode": "private-portable",
            "contains_personal_data": True,
            "required_access": "private-authenticated",
            "allowed_files": ["index.html", plan_rel, "release-manifest.json"],
            "files": [
                {"path": "index.html", "bytes": index.stat().st_size, "sha256": hashlib.sha256(index.read_bytes()).hexdigest()},
                {"path": plan_rel, "bytes": plan.stat().st_size, "sha256": hashlib.sha256(plan.read_bytes()).hexdigest()},
            ],
        }
        (self.source / "release-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        self.prepare.build(self.source, self.output)
        html = (self.output / "index.html").read_text(encoding="utf-8")
        match = __import__("re").search(r'<script id="workbench-data" type="application/json">(.*?)</script>', html)
        self.assertIsNotNone(match)
        data = json.loads(match.group(1))
        self.assertEqual(data["meta"]["plan_href"], "plans/current-plan.html")
        self.assertEqual((self.output / "plans" / "current-plan.html").read_text(encoding="utf-8"), "<h1>完整训练计划</h1>")
        self.assertNotIn("%E8%AE%AD%E7%BB%83", html)
        self.assertNotIn("data:text/html;base64,", html)
        self.assertIn("function openPublishedPlan", html)
        self.assertIn("frame.src=url", html)
        self.assertIn("plan-reader-dialog", html)
        self.assertIn("sandbox','allow-scripts", html)
        self.assertNotIn(self.prepare.PLAN_LINK_MARKER, html)

    def test_cli_requires_explicit_public_confirmation(self):
        self.assertEqual(self.prepare.main(["--private-release", str(self.source), "--out", str(self.output)]), 1)
        self.assertFalse(self.output.exists())

    def test_deployer_rejects_tampered_index(self):
        self.prepare.build(self.source, self.output)
        self.deploy.validate_release(self.output)
        (self.output / "index.html").write_text("tampered", encoding="utf-8")
        with self.assertRaises(self.deploy.DeployError):
            self.deploy.validate_release(self.output)

    def test_online_verifier_requires_both_exact_files(self):
        self.prepare.build(self.source, self.output)
        class Response:
            status = 200
            def __init__(self, value): self.value = value
            def __enter__(self): return self
            def __exit__(self, *args): return None
            def read(self): return self.value
        original = self.verify.urlopen
        def requested_path(request):
            return unquote(urlparse(request.full_url).path.split("/fitness-public/", 1)[1])
        def exact(request, **kwargs):
            return Response((self.output / requested_path(request)).read_bytes())
        self.verify.urlopen = exact
        try:
            self.assertTrue(self.verify.verify(self.output, "https://example.invalid/fitness-public/")["online_verified"])
            def stale(request, **kwargs):
                name = requested_path(request)
                return Response(b"stale" if name == "index.html" else (self.output / name).read_bytes())
            self.verify.urlopen = stale
            with self.assertRaises(self.verify.VerifyError):
                self.verify.verify(self.output, "https://example.invalid/fitness-public/", attempts=1)
        finally:
            self.verify.urlopen = original

    def test_online_verifier_retries_cloudbase_propagation_delay(self):
        self.prepare.build(self.source, self.output)
        class Response:
            status = 200
            def __init__(self, value): self.value = value
            def __enter__(self): return self
            def __exit__(self, *args): return None
            def read(self): return self.value
        calls = {"count": 0}
        def transient_then_exact(request, **kwargs):
            name = unquote(urlparse(request.full_url).path.split("/fitness-public/", 1)[1])
            calls["count"] += 1
            if calls["count"] == 1:
                raise self.verify.URLError("CloudBase propagation delay")
            return Response((self.output / name).read_bytes())
        with mock.patch.object(self.verify, "urlopen", side_effect=transient_then_exact):
            result = self.verify.verify(self.output, "https://example.invalid/fitness-public/", attempts=2, retry_delay=0)
        self.assertTrue(result["online_verified"])
        self.assertEqual(result["attempts_used"], 2)

    def test_deployer_missing_confirmation_never_calls_tcb(self):
        with mock.patch.object(self.deploy.common, "run_tcb") as run_tcb, mock.patch.object(self.deploy.subprocess, "run") as upload, contextlib.redirect_stderr(io.StringIO()):
            code = self.deploy.main(["--release-dir", str(self.output), "--env-id", "free-env", "--cloud-path", "/fitness-public", "--project", str(self.root / "project"), "--backup-dir", str(self.root / "backup"), "--receipt", str(self.root / "receipt.json"), "--config", str(self.root / "config.json")])
        self.assertEqual(code, 1)
        run_tcb.assert_not_called()
        upload.assert_not_called()


class PublicPersonalPublishStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.publisher = load(PUBLISH, "public_personal_publisher_state_test")
        self.temp = tempfile.TemporaryDirectory(prefix="public-personal-publisher-")
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        (self.project / "健身工作台.html").write_text("<!doctype html>", encoding="utf-8")
        stamp = dt.datetime.now().astimezone().isoformat(timespec="seconds")
        self.notion = self.root / "notion.json"
        self.notion.write_text(json.dumps({"sync_mode": "incremental", "source_queried_at": stamp, "snapshot_generated_at": stamp}), encoding="utf-8")
        self.config = self.root / "config.json"
        self.write_config("/fitness-public")
        self.private = self.root / "private"
        self.public = self.root / "public"
        self.history = self.root / "history"
        self.backup = self.root / "backup"
        self.receipt = self.root / "receipts" / "publish.json"
        self.commands: list[list[str]] = []

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_config(self, cloud_path: str) -> None:
        self.config.write_text(json.dumps({"env_id": "free-env", "cloud_path": cloud_path, "release_mode": "public-personal-authorized", "contains_personal_data": True, "user_authorized_public": True}), encoding="utf-8")

    def argv(self, *, confirm: bool = True, execute: bool = False, online: bool = False) -> list[str]:
        args = ["--project", str(self.project), "--notion", str(self.notion), "--notion-mode", "incremental", "--private-release-dir", str(self.private), "--public-release-dir", str(self.public), "--history-dir", str(self.history), "--backup-dir", str(self.backup), "--receipt", str(self.receipt), "--config", str(self.config)]
        if confirm:
            args.append("--confirm-public-personal-data")
        if execute:
            args.append("--execute")
        if online:
            args.extend(["--verify-online", "--base-url", "https://example.invalid/fitness-public/"])
        return args

    def run_case(self, *, deploy_failure: bool = False, online_failure: bool = False):
        def fake_run(command: list[str], _label: str):
            self.commands.append(command)
            if str(self.publisher.REFRESH) in command:
                path = Path(command[command.index("--receipt") + 1])
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({"result": {"status": "PASS"}, "claims": {"formal_refreshed": True, "release_prepared": True}}), encoding="utf-8")
                return {"status": "PASS"}
            if str(self.publisher.PREPARE) in command:
                path = Path(command[command.index("--receipt") + 1])
                path.write_text(json.dumps({"kind": "lzheng_fitness_workbench_public_personal_release_receipt", "claims": {"release_prepared": True}, "result": {"status": "PASS", "release_dir": str(self.public), "manifest_sha256": "m", "index_sha256": "i"}}), encoding="utf-8")
                return {"status": "PASS"}
            if str(self.publisher.DEPLOY) in command:
                if deploy_failure:
                    raise self.publisher.common.StageError("remote mismatch", {"deployed": True, "online_verified": False, "remote_tree_exact": False})
                return {"deployed": True, "online_verified": False, "remote_tree_exact": True}
            raise AssertionError(command)
        def fake_verify(*_args):
            if online_failure:
                raise self.publisher.verify_module.VerifyError("online mismatch")
            return {"online_verified": True}
        with mock.patch.object(self.publisher.common, "run", side_effect=fake_run), mock.patch.object(self.publisher, "archive_release", return_value={"path": "archive", "manifest_sha256": "m", "index_sha256": "i"}), mock.patch.object(self.publisher.verify_module, "verify", side_effect=fake_verify), contextlib.redirect_stdout(io.StringIO()):
            code = self.publisher.main(self.argv(execute=True, online=True))
        return code, json.loads(self.receipt.read_text(encoding="utf-8"))

    def test_publish_missing_confirmation_runs_no_stage(self):
        with mock.patch.object(self.publisher.common, "run") as stage_run, contextlib.redirect_stdout(io.StringIO()):
            code = self.publisher.main(self.argv(confirm=False))
        self.assertEqual(code, 1)
        stage_run.assert_not_called()

    def test_current_confirmation_is_forwarded_to_prepare_and_deploy(self):
        code, receipt = self.run_case()
        self.assertEqual(code, 0)
        self.assertTrue(all(receipt["claims"].values()))
        prepare = next(command for command in self.commands if str(self.publisher.PREPARE) in command)
        deploy = next(command for command in self.commands if str(self.publisher.DEPLOY) in command)
        self.assertIn("--confirm-public-personal-data", prepare)
        self.assertIn("--confirm-public-personal-data", deploy)

    def test_post_upload_remote_mismatch_keeps_deployed_true(self):
        code, receipt = self.run_case(deploy_failure=True)
        self.assertEqual(code, 1)
        self.assertTrue(receipt["claims"]["deployed"])
        self.assertFalse(receipt["claims"]["online_verified"])

    def test_online_mismatch_keeps_deployed_true(self):
        code, receipt = self.run_case(online_failure=True)
        self.assertEqual(code, 1)
        self.assertTrue(receipt["claims"]["deployed"])
        self.assertFalse(receipt["claims"]["online_verified"])

    def test_private_path_config_is_rejected_before_stages(self):
        self.write_config("/fitness-private")
        with mock.patch.object(self.publisher.common, "run") as stage_run, contextlib.redirect_stdout(io.StringIO()):
            code = self.publisher.main(self.argv())
        self.assertEqual(code, 1)
        stage_run.assert_not_called()


if __name__ == "__main__":
    result = unittest.main(verbosity=2, exit=False)
    raise SystemExit(0 if result.result.wasSuccessful() else 1)
