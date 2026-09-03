#!/usr/bin/env python3
"""Regression coverage for portable CI and required Windows Agent checks."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import unittest
from pathlib import Path
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "bundle_validation", Path(__file__).with_name("validate_bundle.py")
)
assert SPEC and SPEC.loader
BUNDLE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUNDLE)
INTEGRATION = BUNDLE.ROOT / "integrations" / "cloudbase"


class PlatformRoutingTests(unittest.TestCase):
    def test_non_windows_does_not_spawn_or_require_powershell(self):
        for platform in ("linux", "darwin"):
            with self.subTest(platform=platform), patch.object(BUNDLE.sys, "platform", platform), \
                    patch.object(BUNDLE.shutil, "which") as lookup, \
                    patch.object(BUNDLE, "run") as run, \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                BUNDLE.validate_windows_local_agent(INTEGRATION)
                lookup.assert_not_called()
                run.assert_not_called()
                self.assertIn("SKIP: Windows", output.getvalue())

    def test_windows_executes_both_checks(self):
        with patch.object(BUNDLE.sys, "platform", "win32"), \
                patch.object(BUNDLE.shutil, "which", return_value="powershell"), \
                patch.object(BUNDLE, "run", return_value='{"passed":true}') as run, \
                contextlib.redirect_stdout(io.StringIO()):
            BUNDLE.validate_windows_local_agent(INTEGRATION)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(
            [Path(call.args[0][-1]).name for call in run.call_args_list],
            ["Test-LocalAgentSafety.ps1", "Test-LocalAgentConcurrency.ps1"],
        )

    def test_missing_windows_powershell_is_failure_not_skip(self):
        with patch.object(BUNDLE.sys, "platform", "win32"), \
                patch.object(BUNDLE.shutil, "which", return_value=None), \
                patch.object(BUNDLE, "run") as run:
            with self.assertRaisesRegex(BUNDLE.ValidationFailure, "PowerShell is required"):
                BUNDLE.validate_windows_local_agent(INTEGRATION)
            run.assert_not_called()

    def test_failed_windows_check_still_fails_bundle(self):
        with patch.object(BUNDLE.sys, "platform", "win32"), \
                patch.object(BUNDLE.shutil, "which", return_value="powershell"), \
                patch.object(BUNDLE, "run", return_value='{"passed":false}'):
            with self.assertRaisesRegex(BUNDLE.ValidationFailure, "did not pass"):
                BUNDLE.validate_windows_local_agent(INTEGRATION)

    def test_linux_still_runs_migration_and_isolation_contracts(self):
        outputs = ["CLOUDBASE_MIGRATION_CONTRACT: PASS", "INSTANCE_ISOLATION: PASS"]
        with patch.object(BUNDLE.sys, "platform", "linux"), \
                patch.object(BUNDLE, "run", side_effect=outputs) as run, \
                contextlib.redirect_stdout(io.StringIO()):
            BUNDLE.validate_v3_local_first_contract()
        self.assertEqual(run.call_count, 2)
        self.assertEqual(
            [Path(call.args[0][-1]).name for call in run.call_args_list],
            ["Test-MigrationContract.py", "Test-InstanceIsolation.py"],
        )


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(PlatformRoutingTests)
    )
    if not result.wasSuccessful():
        raise SystemExit(1)
    print("VALIDATION_PLATFORM_TEST: PASS")
