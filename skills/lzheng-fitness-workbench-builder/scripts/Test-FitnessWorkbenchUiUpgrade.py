#!/usr/bin/env python3
"""Migration safety tests: history, data preservation, drift, failures and concurrency."""
from __future__ import annotations
import gzip
import json
import os
import subprocess
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest.mock import patch

from workbench_ui import DATA, NAV, TEMPLATE, data_block, identity

HERE = Path(__file__).resolve().parent
UPGRADE = SourceFileLoader("ui_upgrade_test", str(HERE / "Upgrade-FitnessWorkbenchUi.py")).load_module()


class UpgradeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="fitness-ui-upgrade-")
        cls.base = Path(cls.temp.name)
        cls.project = cls.base / "中文 空格 project"
        result = subprocess.run([sys.executable, "-B", str(HERE / "Initialize-FitnessWorkbench.py"), "--target", str(cls.project), "--brand", "TEST"], capture_output=True, env={**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"})
        if result.returncode:
            raise AssertionError(result.stdout.decode("utf-8") + result.stderr.decode("utf-8"))
        cls.formal = cls.project / "健身工作台.html"
        cls.current = cls.formal.read_text(encoding="utf-8")
        cls.raw = data_block(cls.current)[0]
        # Public repository fixtures are deliberately not copied into installed Skills.
        cls.fixtures = HERE.parents[2] / "tests/fixtures/ui-history"

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        old = gzip.decompress((self.fixtures / "v3.1.1.html.gz").read_bytes()).decode("utf-8")
        self.old = DATA.sub(lambda m: m[1] + self.raw + m[3], old.replace("__FWB_BRAND__", "TEST"))
        self.formal.write_text(self.old, encoding="utf-8")
        self.before = self.formal.read_bytes()

    def test_official_history_and_same_path(self):
        for tag in ("v2.3.0", "v2.3.1", "v3.1.0", "v3.1.1"):
            with self.subTest(tag=tag):
                old = gzip.decompress((self.fixtures / (tag+".html.gz")).read_bytes()).decode("utf-8").replace("__FWB_BRAND__", "TEST")
                self.formal.write_text(DATA.sub(lambda m: m[1]+self.raw+m[3], old), encoding="utf-8")
                before = self.formal.read_bytes()
                receipt = UPGRADE.upgrade(self.project, self.base / "backups", True, smoke=lambda _: None)
                self.assertTrue(receipt["ui_upgraded"])
                self.assertFalse(receipt["data_refreshed"])
                self.assertEqual(Path(receipt["backup"]).read_bytes(), before)
                self.assertEqual(data_block(self.formal.read_text(encoding="utf-8"))[0], self.raw)
                self.assertEqual(receipt["workbench"], str(self.formal))

    def test_missing_navigation_is_repaired(self):
        self.formal.write_text(NAV.sub("", self.old), encoding="utf-8")
        UPGRADE.upgrade(self.project, self.base / "backups", True, smoke=lambda _: None)
        self.assertIn('id="workbench-shell"', self.formal.read_text(encoding="utf-8"))

    def test_check_only_and_repeat_are_readonly(self):
        names = set(self.project.rglob("*"))
        result = UPGRADE.upgrade(self.project, None, False)
        self.assertEqual(result["status"], "ui_upgrade_prepared")
        self.assertEqual(self.formal.read_bytes(), self.before)
        self.assertEqual(set(self.project.rglob("*")), names)
        UPGRADE.upgrade(self.project, self.base / "backups", True, smoke=lambda _: None)
        before = self.formal.read_bytes()
        result = UPGRADE.upgrade(self.project, None, True, smoke=lambda _: self.fail("No repeated write"))
        self.assertEqual(result["status"], "current")
        self.assertEqual(self.formal.read_bytes(), before)

    def test_customization_background_and_identity(self):
        background = SourceFileLoader("background_ui_test", str(HERE / "Replace-FitnessWorkbenchBackground.py")).load_module()
        old = background.build_html(self.old, "工作台与工具/健身工作台开发/界面素材/workbench-background.png", None, "20% center", "40% center", "80% center")
        old = old.replace("<title>Lzheng 健身系统</title>", "<title>用户自定义标题</title>")
        self.formal.write_text(old, encoding="utf-8")
        UPGRADE.upgrade(self.project, self.base / "backups", True, smoke=lambda _: None)
        after = self.formal.read_text(encoding="utf-8")
        self.assertIn("用户自定义标题", after)
        self.assertIn('data-background-mode="static"', after)
        self.assertIn("20% center", after)
        self.assertEqual(data_block(after)[0], self.raw)
        self.assertTrue(identity(after)["declared_hash_matches"])

    def test_unknown_custom_script_refused(self):
        for modified in (self.old.replace("</body>", "<script>window.custom=1</script></body>"), self.old.replace("--bg:#f6f6f4", "--bg:#fff")):
            self.formal.write_text(modified, encoding="utf-8")
            before = self.formal.read_bytes()
            with self.assertRaisesRegex(ValueError, "无法自动迁移"):
                UPGRADE.upgrade(self.project, self.base / "backups", True)
            self.assertEqual(self.formal.read_bytes(), before)

    def test_bad_data_refused(self):
        for raw in ("{", "[]", '{"schema":5}', '{"schema":6}'):
            self.formal.write_text(DATA.sub(lambda m: m[1]+raw+m[3], self.old), encoding="utf-8")
            before = self.formal.read_bytes()
            with self.assertRaises(ValueError):
                UPGRADE.upgrade(self.project, self.base / "backups", True)
            self.assertEqual(self.formal.read_bytes(), before)

    def test_browser_failure_before_and_after_replace(self):
        for fail_at in (1, 2):
            calls = []
            def smoke(path):
                calls.append(path)
                if len(calls) == fail_at:
                    raise ValueError("injected browser failure")
            with self.assertRaisesRegex(ValueError, "injected"):
                UPGRADE.upgrade(self.project, self.base / "backups", True, smoke=smoke)
            self.assertEqual(self.formal.read_bytes(), self.before)
            self.assertFalse(list(self.project.glob(".fitness-ui*")))

    def test_atomic_write_failure(self):
        with patch.object(UPGRADE.os, "replace", side_effect=OSError("injected write failure")):
            with self.assertRaises(OSError):
                UPGRADE.upgrade(self.project, self.base / "backups", True, smoke=lambda _: None)
        self.assertEqual(self.formal.read_bytes(), self.before)

    def test_backup_overlap_and_parallel_edit(self):
        for backup in (self.project, self.project / "backup", self.base):
            with self.assertRaisesRegex(ValueError, "重叠"):
                UPGRADE.upgrade(self.project, backup, True)
        def concurrent(_):
            self.formal.write_bytes(self.before + b"\n<!-- concurrent edit -->")
        with self.assertRaisesRegex(ValueError, "发生变化"):
            UPGRADE.upgrade(self.project, self.base / "backups", True, smoke=concurrent)
        self.assertTrue(self.formal.read_bytes().endswith(b"<!-- concurrent edit -->"))

    def test_revision_marker_cannot_disguise_custom_code(self):
        fake = self.current.replace("</body>", "<script>window.custom=1</script></body>")
        self.assertEqual(UPGRADE.inspect_html(fake)["status"], "unknown_or_customized")

    def test_custom_navigation_is_not_silently_discarded(self):
        custom = NAV.sub('<nav class="nav" id="navBar"><a href="custom.html">用户入口</a></nav>', self.old)
        self.assertEqual(UPGRADE.inspect_html(custom)["status"], "unknown_or_customized")

    def test_symlink_is_rejected(self):
        linked = self.base / "linked-project"
        junction = False
        try:
            linked.symlink_to(self.project, target_is_directory=True)
        except OSError:
            if os.name != "nt":
                self.skipTest("Platform does not permit creating symlinks")
            result = subprocess.run(["cmd", "/c", "mklink", "/J", str(linked), str(self.project)], capture_output=True)
            if result.returncode:
                self.skipTest("Platform does not permit creating symlinks or junctions")
            junction = True
        try:
            with self.assertRaisesRegex(ValueError, "重解析点"):
                UPGRADE.upgrade(linked, self.base / "backups", True)
        finally:
            if junction:
                # Remove only the junction itself, never recurse into the target.
                self.assertTrue(linked.parent.resolve() == self.base.resolve())
                linked.rmdir()
            else:
                linked.unlink()

    def test_system_cli_does_not_claim_full_upgrade(self):
        system = HERE.parents[1] / "lzheng-training-system/scripts/lzheng_training_system.py"
        config = self.base / "系统/lzheng-system.json"
        config.parent.mkdir(exist_ok=True)
        config.write_text(json.dumps({"schema": 1, "suite_version": "3.1.0", "project_root": self.project.name,
                                    "skills_root": "@runtime", "backup_root": "系统/backups", "managed_files": {}}), encoding="utf-8")
        before = config.read_bytes()
        env = {**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"}
        checked = subprocess.run([sys.executable, "-B", str(system), "upgrade-workbench-ui", "--root", str(self.base), "--check-only"], capture_output=True, text=True, encoding="utf-8", env=env)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertEqual(config.read_bytes(), before)
        self.assertEqual(self.formal.read_bytes(), self.before)
        upgraded = subprocess.run([sys.executable, "-B", str(system), "upgrade", "--root", str(self.base)], capture_output=True, text=True, encoding="utf-8", env=env)
        self.assertEqual(upgraded.returncode, 2, upgraded.stdout+upgraded.stderr)
        self.assertIn("CONFIG_ONLY", upgraded.stdout)
        self.assertIn("needs_ui_upgrade", upgraded.stdout)
        self.assertNotIn("UPGRADE: PASS", upgraded.stdout)
        self.assertEqual(self.formal.read_bytes(), self.before)
        diagnosed = subprocess.run([sys.executable, "-B", str(system), "doctor", "--root", str(self.base)], capture_output=True, text=True, encoding="utf-8", env=env)
        self.assertEqual(diagnosed.returncode, 2, diagnosed.stdout+diagnosed.stderr)
        self.assertIn("DOCTOR: NEEDS_UI_ATTENTION", diagnosed.stdout)


if __name__ == "__main__":
    unittest.main()
