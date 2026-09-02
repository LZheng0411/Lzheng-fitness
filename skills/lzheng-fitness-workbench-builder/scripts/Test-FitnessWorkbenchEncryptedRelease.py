#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Isolated security tests for the encrypted private static release."""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "Prepare-FitnessWorkbenchEncryptedRelease.py"
DEPLOY = HERE / "Deploy-FitnessWorkbenchCloudBaseEncrypted.py"
VERIFY = HERE / "Verify-FitnessWorkbenchCloudBaseEncrypted.py"


def load_module():
    spec = importlib.util.spec_from_file_location("lzheng_encrypted_release", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load encrypted release script")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EncryptedReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module()
        self.deploy_module = self._load(DEPLOY, "lzheng_encrypted_deploy_test")
        self.verify_module = self._load(VERIFY, "lzheng_encrypted_verify_test")
        self.temp = tempfile.TemporaryDirectory(prefix="lzheng-encrypted-release-")
        self.root = Path(self.temp.name)
        self.source = self.root / "private"
        self.source.mkdir()
        (self.source / "assets").mkdir()
        (self.source / "docs").mkdir()
        self.private_text = "私人训练 100kg E:\\obsidian notion://private"
        (self.source / "assets" / "background.png").write_bytes(b"\x89PNG\r\nprivate-image")
        (self.source / "docs" / "plan.html").write_text("<h1>" + self.private_text + "</h1>", encoding="utf-8")
        (self.source / "index.html").write_text('<script id="workbench-data" type="application/json">{"release":{"mode":"private-portable"}}</script><img src="assets/background.png"><a href="docs/plan.html">plan</a><p>' + self.private_text + "</p>", encoding="utf-8")
        allowed = ["index.html", "assets/background.png", "docs/plan.html", "release-manifest.json"]
        files = []
        for rel in allowed[:-1]:
            path = self.source / rel
            files.append({"path": rel, "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        manifest = {"schema": 2, "kind": "lzheng-fitness-workbench-release", "producer": "Prepare-FitnessWorkbenchRelease.py", "release_mode": "private-portable", "anonymized": False, "contains_personal_data": True, "required_access": "private-authenticated", "entrypoint": "index.html", "fresh_staging": True, "allowed_files": allowed, "files": files}
        (self.source / "release-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        self.password = "Q7!vN2@kL9#pR4$xT8&zM5*wC3^hF6+s"
        self.secret = self.root / "secret.json"
        protected = self.module.dpapi_protect(self.password.encode("utf-8"))
        self.secret.write_text(json.dumps({"schema": 1, "kind": "lzheng_fitness_workbench_private_secret", "protection": "windows-dpapi-current-user", "high_entropy_acknowledged": True, "ciphertext": base64.b64encode(protected).decode("ascii")}), encoding="utf-8")
        self.output = self.root / "encrypted"

    @staticmethod
    def _load(path: Path, name: str):
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise RuntimeError("cannot load test module")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def tearDown(self) -> None:
        self.temp.cleanup()

    def decrypt_output(self, password: str) -> bytes:
        payload = json.loads((self.output / "private-payload.json").read_text(encoding="utf-8"))
        salt = base64.b64decode(payload["salt"])
        nonce = base64.b64decode(payload["nonce"])
        ciphertext = base64.b64decode(payload["ciphertext"])
        key = self.module.derive_key(password, salt)
        return AESGCM(key).decrypt(nonce, ciphertext, payload["aad"].encode("ascii"))

    def test_dpapi_round_trip_is_current_user_bound(self):
        raw = b"Q7!vN2@kL9#pR4$xT8&zM5*wC3^hF6+s"
        self.assertEqual(self.module.dpapi_unprotect(self.module.dpapi_protect(raw)), raw)

    def test_build_exposes_only_ciphertext_and_manifest(self):
        result = self.module.build(self.source, self.output, self.secret)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual({p.name for p in self.output.iterdir()}, {"index.html", "private-payload.json", "release-manifest.json"})
        public = "\n".join(path.read_text(encoding="utf-8") for path in self.output.iterdir())
        self.assertNotIn("100kg", public)
        self.assertNotIn("obsidian", public.lower())
        self.assertNotIn(self.password, public)

    def test_correct_password_restores_html_and_inlines_assets(self):
        self.module.build(self.source, self.output, self.secret)
        plain = self.decrypt_output(self.password).decode("utf-8")
        self.assertIn(self.private_text, plain)
        self.assertIn("data:image/png;base64,", plain)
        self.assertIn("data:text/html;base64,", plain)
        self.assertNotIn('src="assets/background.png"', plain)

    def test_wrong_password_cannot_decrypt(self):
        self.module.build(self.source, self.output, self.secret)
        with self.assertRaises(InvalidTag):
            self.decrypt_output("Wrong-Private-2026!")

    def test_tampered_source_is_rejected(self):
        (self.source / "index.html").write_text("tampered", encoding="utf-8")
        with self.assertRaises(self.module.ReleaseError):
            self.module.build(self.source, self.output, self.secret)
        self.assertFalse(self.output.exists())

    def test_unmanaged_output_is_preserved(self):
        self.output.mkdir()
        sentinel = self.output / "owner.txt"
        sentinel.write_text("keep", encoding="utf-8")
        with self.assertRaises(self.module.ReleaseError):
            self.module.build(self.source, self.output, self.secret)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")

    def test_secret_strength_rejects_weak_values(self):
        self.assertFalse(self.module.strong_passphrase("12345678"))
        self.assertTrue(self.module.strong_passphrase(self.password))

    def test_cloudbase_deployer_accepts_only_intact_encrypted_tree(self):
        self.module.build(self.source, self.output, self.secret)
        evidence = self.deploy_module.validate_release(self.output)
        self.assertEqual(evidence["manifest"]["release_mode"], "private-encrypted")
        payload = self.output / "private-payload.json"
        payload.write_text(payload.read_text(encoding="utf-8") + " ", encoding="utf-8")
        with self.assertRaises(self.deploy_module.DeployError):
            self.deploy_module.validate_release(self.output)

    def test_online_verifier_requires_all_three_exact_files(self):
        self.module.build(self.source, self.output, self.secret)
        class Response:
            status = 200
            def __init__(self, value: bytes): self.value = value
            def __enter__(self): return self
            def __exit__(self, *args): return None
            def read(self): return self.value
        globals_ = self.verify_module.fetch.__globals__
        original = globals_["urlopen"]
        def exact(request, **kwargs):
            name = request.full_url.split("/")[-1].split("?")[0]
            return Response((self.output / name).read_bytes())
        globals_["urlopen"] = exact
        try:
            result = self.verify_module.verify(self.output, self.secret, "https://example.invalid")
            self.assertTrue(result["online_verified"])
            def stale(request, **kwargs):
                name = request.full_url.split("/")[-1].split("?")[0]
                return Response(b"stale" if name == "private-payload.json" else (self.output / name).read_bytes())
            globals_["urlopen"] = stale
            with self.assertRaises(self.verify_module.VerifyError):
                self.verify_module.verify(self.output, self.secret, "https://example.invalid")
        finally:
            globals_["urlopen"] = original

    def test_archived_release_must_decrypt_with_current_dpapi_secret(self):
        self.module.build(self.source, self.output, self.secret)
        evidence = self.deploy_module.validate_release(self.output)
        self.assertTrue(self.deploy_module.validate_local_decryption(self.output, self.secret, evidence)["passed"])
        wrong_secret = self.root / "wrong-secret.json"
        wrong_value = "Z9@rT4#nM7$pQ2&vL8*wC5^hF3+kD6!s"
        protected = self.module.dpapi_protect(wrong_value.encode("utf-8"))
        wrong_secret.write_text(json.dumps({"schema": 1, "kind": "lzheng_fitness_workbench_private_secret", "protection": "windows-dpapi-current-user", "high_entropy_acknowledged": True, "ciphertext": base64.b64encode(protected).decode("ascii")}), encoding="utf-8")
        with self.assertRaises(self.deploy_module.DeployError):
            self.deploy_module.validate_local_decryption(self.output, wrong_secret, evidence)

    def test_remote_file_set_is_bound_to_dedicated_prefix(self):
        expected = {"fitness-private/index.html", "fitness-private/private-payload.json", "fitness-private/release-manifest.json"}
        self.assertEqual(self.deploy_module.expected_remote_keys("/fitness-private"), expected)
        self.deploy_module.validate_remote_before(set(), expected)
        self.deploy_module.validate_remote_before(expected, expected)
        with self.assertRaises(self.deploy_module.DeployError):
            self.deploy_module.validate_remote_before({"fitness-private/index.html"}, expected)
        with self.assertRaises(self.deploy_module.DeployError):
            self.deploy_module.validate_remote_before(expected | {"fitness-private/old.html"}, expected)
        completed = mock.Mock(returncode=0, stdout=json.dumps({"data": [{"key": key} for key in sorted(expected)]}))
        with mock.patch.object(self.deploy_module.subprocess, "run", return_value=completed):
            self.assertEqual(self.deploy_module.list_remote_keys("tcb", "free-env", "/fitness-private"), expected)

    def test_remote_list_rejects_malformed_data_and_rows(self):
        for payload in ({"data": {}}, {"data": [{}]}, {"data": [{"key": 123}]}):
            completed = mock.Mock(returncode=0, stdout=json.dumps(payload))
            with mock.patch.object(self.deploy_module.subprocess, "run", return_value=completed):
                with self.assertRaises(self.deploy_module.DeployError):
                    self.deploy_module.list_remote_keys("tcb", "free-env", "/fitness-private")


if __name__ == "__main__":
    result = unittest.main(verbosity=2, exit=False)
    raise SystemExit(0 if result.result.wasSuccessful() else 1)
