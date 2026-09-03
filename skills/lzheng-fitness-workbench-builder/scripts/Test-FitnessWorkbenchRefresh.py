#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Focused regression tests for the refresh receipt and handoff state gate."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
REFRESH_SOURCE = HERE / "Refresh-FitnessWorkbench.py"
PROCESS_SOURCE = HERE.parent.parent / "lzheng-training-system" / "scripts" / "Process-LzhengHandoffs.py"


BUILD_STUB = r'''#!/usr/bin/env python3
import argparse
import shutil
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--project", required=True)
p.add_argument("--notion")
p.add_argument("--notion-mode", choices=("incremental", "full"))
p.add_argument("--replace-main-lift-history", action="store_true")
p.add_argument("--check-only", action="store_true")
p.add_argument("--apply", action="store_true")
p.add_argument("--backup-dir")
a = p.parse_args()
formal = Path(a.project) / "健身工作台.html"
if a.notion_mode:
    import json
    payload = json.loads(Path(a.notion).read_text(encoding="utf-8"))
    if payload.get("sync_mode") != a.notion_mode:
        raise SystemExit("mode was not preserved")
if a.replace_main_lift_history and a.notion_mode != "full":
    raise SystemExit("history replacement was not forwarded with full mode")
if a.apply:
    backup = Path(a.backup_dir)
    backup.mkdir(parents=True, exist_ok=True)
    shutil.copy2(formal, backup / "pre-apply-workbench.html")
    text = formal.read_text(encoding="utf-8")
    formal.write_text(text + "\n<!-- refreshed -->\n", encoding="utf-8")
    print("workbench-data applied: " + str(formal))
print("FITNESS_WORKBENCH_DATA: PASS")
'''


CHECK_STUB = r'''#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--project", required=True)
p.add_argument("--notion")
p.add_argument("--notion-mode", choices=("incremental", "full"))
p.add_argument("--replace-main-lift-history", action="store_true")
p.add_argument("--deploy")
p.add_argument("--allow-private-portable", action="store_true")
p.add_argument("--expect-release-mode")
a = p.parse_args()
project = Path(a.project)
if (project / "fail-formal-check").exists():
    print("FITNESS_WORKBENCH_CHECK: FAIL")
    raise SystemExit(1)
if a.notion_mode:
    payload = json.loads(Path(a.notion).read_text(encoding="utf-8"))
    if payload.get("sync_mode") != a.notion_mode:
        raise SystemExit("checker mode was not preserved")
if a.replace_main_lift_history and a.notion_mode != "full":
    raise SystemExit("checker history replacement was not forwarded with full mode")
if a.deploy:
    deploy = Path(a.deploy)
    manifest = json.loads((deploy / "release-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("release_mode") != a.expect_release_mode:
        raise SystemExit("wrong release mode")
    if a.expect_release_mode == "private-portable" and not a.allow_private_portable:
        raise SystemExit("private release was not confirmed to checker")
    print("deploy: PASS (" + a.expect_release_mode + ")")
else:
    print("deploy: PASS")
print("FITNESS_WORKBENCH_CHECK: PASS")
'''


RELEASE_STUB = r'''#!/usr/bin/env python3
import argparse
import hashlib
import json
import shutil
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--project", required=True)
p.add_argument("--deploy", required=True)
p.add_argument("--mode", required=True)
a = p.parse_args()
project = Path(a.project)
deploy = Path(a.deploy)
if deploy.exists():
    shutil.rmtree(deploy)
deploy.mkdir(parents=True)
shutil.copy2(project / "健身工作台.html", deploy / "index.html")
index = deploy / "index.html"
private = a.mode == "private-portable"
(deploy / "release-manifest.json").write_text(json.dumps({
    "schema": 2,
    "kind": "lzheng-fitness-workbench-release",
    "producer": "Prepare-FitnessWorkbenchRelease.py",
    "release_mode": a.mode,
    "fresh_staging": True,
    "entrypoint": "index.html",
    "anonymized": not private,
    "contains_personal_data": private,
    "required_access": "private-authenticated" if private else "public",
    "allowed_files": ["index.html", "release-manifest.json"],
    "files": [{"path": "index.html", "bytes": index.stat().st_size, "sha256": hashlib.sha256(index.read_bytes()).hexdigest()}],
}), encoding="utf-8")
print("FITNESS_WORKBENCH_RELEASE: PASS")
'''


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def make_suite(root: Path) -> tuple[Path, Path]:
    builder_scripts = root / "skills" / "lzheng-fitness-workbench-builder" / "scripts"
    system_scripts = root / "skills" / "lzheng-training-system" / "scripts"
    builder_scripts.mkdir(parents=True)
    system_scripts.mkdir(parents=True)
    shutil.copy2(REFRESH_SOURCE, builder_scripts / REFRESH_SOURCE.name)
    shutil.copy2(PROCESS_SOURCE, system_scripts / PROCESS_SOURCE.name)
    write(builder_scripts / "Build-FitnessWorkbenchData.py", BUILD_STUB)
    write(builder_scripts / "Check-FitnessWorkbench.py", CHECK_STUB)
    write(builder_scripts / "Prepare-FitnessWorkbenchRelease.py", RELEASE_STUB)
    return builder_scripts, system_scripts


def make_project(root: Path, name: str) -> Path:
    project = root / name
    write(
        project / "健身工作台.html",
        '<!doctype html><script id="workbench-data" type="application/json">{"schema":6}</script>',
    )
    return project


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, encoding="utf-8", errors="replace", capture_output=True)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def make_directory_link(link: Path, target: Path) -> bool:
    try:
        link.symlink_to(target, target_is_directory=True)
        return True
    except OSError:
        if os.name != "nt":
            return False
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    return result.returncode == 0 and link.exists()


def test_formal_only(builder_scripts: Path, root: Path) -> None:
    project = make_project(root, "中文 空格-正式刷新")
    backup = root / "证据" / "formal"
    receipt_path = root / "回执" / "formal.json"
    notion = root / "快照" / "notion.json"
    write(notion, json.dumps({"sessions": []}, ensure_ascii=False))
    result = run(
        [
            sys.executable,
            str(builder_scripts / "Refresh-FitnessWorkbench.py"),
            "--project",
            str(project),
            "--notion",
            str(notion),
            "--notion-mode",
            "incremental",
            "--backup-dir",
            str(backup),
            "--receipt",
            str(receipt_path),
        ]
    )
    require(result.returncode == 0, result.stdout + result.stderr)
    receipt = load(receipt_path)
    require(receipt["result"]["status"] == "PASS", "formal receipt must pass")
    require(receipt["claims"] == {"formal_refreshed": True, "release_prepared": False, "deployed": False, "online_verified": False}, "formal-only claims are wrong")
    require(receipt["artifacts"]["snapshot"]["sha256"] == hashlib.sha256(notion.read_bytes()).hexdigest(), "source snapshot hash missing")
    require(receipt["artifacts"]["formal"]["sha256_after"], "formal hash missing")
    require(receipt["evidence"]["formal_checker_pass"] is True, "checker evidence missing")
    require([phase["name"] for phase in receipt["phases"]] == ["builder_check", "builder_apply", "formal_checker"], "formal phase order changed")
    for name in ("refresh", "builder", "checker", "releaser"):
        require(receipt["scripts"][name]["sha256"], "script hash missing: " + name)
        require(receipt["scripts"][name]["version"], "script version missing: " + name)


def test_private_confirmation(builder_scripts: Path, root: Path) -> None:
    project = make_project(root, "private-confirmation")
    receipt_path = root / "回执" / "private-rejected.json"
    deploy = root / "deploy-private"
    result = run(
        [
            sys.executable,
            str(builder_scripts / "Refresh-FitnessWorkbench.py"),
            "--project",
            str(project),
            "--receipt",
            str(receipt_path),
            "--deploy",
            str(deploy),
            "--release-mode",
            "private-portable",
        ]
    )
    require(result.returncode != 0, "private-portable must require explicit confirmation")
    receipt = load(receipt_path)
    require(receipt["claims"] == {"formal_refreshed": False, "release_prepared": False, "deployed": False, "online_verified": False}, "rejected private release claimed progress")
    require(not deploy.exists(), "rejected private release created output")


def test_main_lift_history_confirmation_and_forwarding(builder_scripts: Path, root: Path) -> None:
    project = make_project(root, "replace-main-lift-history")
    notion = root / "快照" / "full-history.json"
    write(notion, json.dumps({"sync_mode": "full", "sessions": []}, ensure_ascii=False))
    rejected_receipt = root / "回执" / "replace-unconfirmed.json"
    rejected = run(
        [
            sys.executable,
            str(builder_scripts / "Refresh-FitnessWorkbench.py"),
            "--project",
            str(project),
            "--notion",
            str(notion),
            "--notion-mode",
            "full",
            "--replace-main-lift-history",
            "--receipt",
            str(rejected_receipt),
        ]
    )
    require(rejected.returncode != 0, "history replacement must require explicit confirmation")
    require(load(rejected_receipt)["claims"]["formal_refreshed"] is False, "unconfirmed history replacement claimed refresh")

    receipt_path = root / "回执" / "replace-confirmed.json"
    deploy = root / "replace-history-deploy"
    accepted = run(
        [
            sys.executable,
            str(builder_scripts / "Refresh-FitnessWorkbench.py"),
            "--project",
            str(project),
            "--notion",
            str(notion),
            "--notion-mode",
            "full",
            "--replace-main-lift-history",
            "--confirm-replace-main-lift-history",
            "--receipt",
            str(receipt_path),
            "--deploy",
            str(deploy),
            "--release-mode",
            "public-anonymized",
        ]
    )
    require(accepted.returncode == 0, accepted.stdout + accepted.stderr)
    receipt = load(receipt_path)
    require(receipt["operation"] == {"replace_main_lift_history": True, "replace_main_lift_history_confirmed": True, "private_portable_confirmed": False}, "history replacement confirmation missing from receipt")
    forwarded = {"builder_check", "builder_apply", "formal_checker", "deploy_checker"}
    for phase in receipt["phases"]:
        if phase["name"] in forwarded:
            require("--replace-main-lift-history" in phase["argv"], "history replacement flag missing from " + phase["name"])
            require("--notion-mode" in phase["argv"] and "full" in phase["argv"], "full mode missing from " + phase["name"])


def test_public_release(builder_scripts: Path, root: Path) -> None:
    project = make_project(root, "public-release")
    receipt_path = root / "回执" / "public.json"
    deploy = root / "deploy-public"
    result = run(
        [
            sys.executable,
            str(builder_scripts / "Refresh-FitnessWorkbench.py"),
            "--project",
            str(project),
            "--receipt",
            str(receipt_path),
            "--deploy",
            str(deploy),
            "--release-mode",
            "public-anonymized",
        ]
    )
    require(result.returncode == 0, result.stdout + result.stderr)
    receipt = load(receipt_path)
    require(receipt["claims"] == {"formal_refreshed": True, "release_prepared": True, "deployed": False, "online_verified": False}, "release claims blurred local preparation with deployment")
    require(receipt["evidence"]["deploy_checker_pass"] is True, "deploy checker evidence missing")
    require(receipt["artifacts"]["deploy"]["tree_sha256"], "deploy tree hash missing")
    require([phase["name"] for phase in receipt["phases"]] == ["builder_check", "builder_apply", "formal_checker", "release_prepare", "deploy_checker"], "release phase order changed")


def test_owned_release_replacement(builder_scripts: Path, root: Path) -> None:
    project = make_project(root, "owned-release")
    deploy = root / "owned-deploy"
    first_receipt = root / "回执" / "owned-first.json"
    common = [
        sys.executable,
        str(builder_scripts / "Refresh-FitnessWorkbench.py"),
        "--project",
        str(project),
        "--deploy",
        str(deploy),
        "--release-mode",
        "public-anonymized",
    ]
    first = run(common + ["--receipt", str(first_receipt)])
    require(first.returncode == 0, first.stdout + first.stderr)
    formal = project / "健身工作台.html"
    formal.write_text(formal.read_text(encoding="utf-8") + "\n<!-- changed template/facts -->\n", encoding="utf-8")
    notion = root / "快照" / "owned-new-notion.json"
    write(notion, json.dumps({"sessions": [{"id": "new"}]}, ensure_ascii=False))
    second_receipt = root / "回执" / "owned-second.json"
    second = run(
        common
        + [
            "--receipt",
            str(second_receipt),
            "--notion",
            str(notion),
            "--notion-mode",
            "incremental",
        ]
    )
    require(second.returncode == 0, second.stdout + second.stderr)
    receipt = load(second_receipt)
    existing = receipt["evidence"]["existing_deploy"]
    require(existing == {"existed": True, "owned_manifest": True, "tree_hashes_pass": True}, "owned deploy replacement lacks proof")
    require(receipt["phases"][0]["name"] == "builder_check", "ownership preflight must not run stale-sensitive full checker")

    tampered_index = deploy / "index.html"
    tampered_index.write_text(tampered_index.read_text(encoding="utf-8") + "\nTAMPERED\n", encoding="utf-8")
    tampered_bytes = tampered_index.read_bytes()
    formal_before_rejection = formal.read_bytes()
    rejected_receipt = root / "回执" / "owned-tampered-rejected.json"
    rejected = run(common + ["--receipt", str(rejected_receipt)])
    require(rejected.returncode != 0, "tampered managed deploy must be rejected")
    require(tampered_index.read_bytes() == tampered_bytes, "tampered deploy was replaced despite failed ownership proof")
    require(formal.read_bytes() == formal_before_rejection, "tampered deploy rejection happened after formal mutation")


def rejected_release(
    builder_scripts: Path,
    project: Path,
    deploy: Path,
    backup: Path,
    receipt: Path,
) -> subprocess.CompletedProcess[str]:
    return run(
        [
            sys.executable,
            str(builder_scripts / "Refresh-FitnessWorkbench.py"),
            "--project",
            str(project),
            "--backup-dir",
            str(backup),
            "--receipt",
            str(receipt),
            "--deploy",
            str(deploy),
            "--release-mode",
            "public-anonymized",
        ]
    )


def test_deploy_target_safety(builder_scripts: Path, root: Path) -> None:
    case = root / "deploy-target-safety"
    project = make_project(case / "container", "project")
    sentinel = project / "project-sentinel.txt"
    write(sentinel, "must survive")
    original_formal = (project / "健身工作台.html").read_bytes()
    outside_backup = case / "evidence"
    outside_receipts = case / "receipts"

    dangerous = {
        "parent": project.parent,
        "project": project,
        "child": project / "deploy",
    }
    for label, target in dangerous.items():
        result = rejected_release(
            builder_scripts,
            project,
            target,
            outside_backup / label,
            outside_receipts / (label + ".json"),
        )
        require(result.returncode != 0, label + " deploy target must be rejected")
        require(sentinel.read_text(encoding="utf-8") == "must survive", label + " target damaged project sentinel")
        require((project / "健身工作台.html").read_bytes() == original_formal, label + " target changed formal HTML")

    root_target = Path(project.anchor)
    result = rejected_release(
        builder_scripts,
        project,
        root_target,
        outside_backup / "root",
        outside_receipts / "root.json",
    )
    require(result.returncode != 0, "drive root deploy target must be rejected")
    require(sentinel.read_text(encoding="utf-8") == "must survive", "root target damaged project sentinel")

    unrelated = case / "unrelated-existing"
    unrelated_sentinel = unrelated / "unrelated-sentinel.txt"
    write(unrelated_sentinel, "must survive")
    result = rejected_release(
        builder_scripts,
        project,
        unrelated,
        outside_backup / "unrelated",
        outside_receipts / "unrelated.json",
    )
    require(result.returncode != 0, "unowned existing directory must be rejected")
    require(unrelated_sentinel.read_text(encoding="utf-8") == "must survive", "unowned directory was replaced")

    overlap_backup = case / "overlap-backup"
    result = rejected_release(
        builder_scripts,
        project,
        overlap_backup / "deploy",
        overlap_backup,
        outside_receipts / "backup-overlap.json",
    )
    require(result.returncode != 0, "deploy nested in backup must be rejected")

    symlink_target = case / "symlink-target"
    symlink_target.mkdir(parents=True)
    symlink_sentinel = symlink_target / "symlink-sentinel.txt"
    write(symlink_sentinel, "must survive")
    symlink_deploy = case / "symlink-deploy"
    if make_directory_link(symlink_deploy, symlink_target):
        sentinel_before = symlink_sentinel.read_bytes()
        result = rejected_release(
            builder_scripts,
            project,
            symlink_deploy,
            outside_backup / "symlink",
            outside_receipts / "symlink.json",
        )
        require(result.returncode != 0, "symlink deploy target must be rejected")
        require(symlink_sentinel.read_bytes() == sentinel_before, "symlink/junction target was changed")
        if symlink_deploy.is_symlink():
            symlink_deploy.unlink()
        else:
            symlink_deploy.rmdir()
        require(not os.path.lexists(symlink_deploy), "test directory link was not removed")
        require(symlink_sentinel.read_bytes() == sentinel_before, "link cleanup changed its target")
    else:
        raise AssertionError("host could create neither directory symlink nor Windows junction for regression")

    parent_target = case / "parent-junction-target"
    parent_target.mkdir(parents=True)
    parent_sentinel = parent_target / "parent-sentinel.bin"
    parent_sentinel.write_bytes(b"junction-parent-must-survive\x00\xff")
    parent_link = case / "parent-junction"
    require(make_directory_link(parent_link, parent_target), "could not create parent link regression fixture")
    parent_before = parent_sentinel.read_bytes()
    result = rejected_release(
        builder_scripts,
        project,
        parent_link / "nested-deploy",
        outside_backup / "parent-junction",
        outside_receipts / "parent-junction.json",
    )
    require(result.returncode != 0, "deploy path through junction parent must be rejected")
    require(parent_sentinel.read_bytes() == parent_before, "junction parent target was changed")
    require(not (parent_target / "nested-deploy").exists(), "junction parent was traversed before rejection")
    if parent_link.is_symlink():
        parent_link.unlink()
    else:
        parent_link.rmdir()
    require(not os.path.lexists(parent_link), "test parent link was not removed")
    require(parent_sentinel.read_bytes() == parent_before, "parent link cleanup changed its target")


def test_checker_failure_rolls_back(builder_scripts: Path, root: Path) -> None:
    project = make_project(root, "rollback")
    before = (project / "健身工作台.html").read_bytes()
    write(project / "fail-formal-check", "1")
    receipt_path = root / "回执" / "rollback.json"
    result = run(
        [
            sys.executable,
            str(builder_scripts / "Refresh-FitnessWorkbench.py"),
            "--project",
            str(project),
            "--backup-dir",
            str(root / "证据" / "rollback"),
            "--receipt",
            str(receipt_path),
        ]
    )
    require(result.returncode != 0, "failed checker must fail refresh")
    receipt = load(receipt_path)
    require(receipt["claims"]["formal_refreshed"] is False, "failed checker claimed formal refresh")
    require(receipt["evidence"]["formal_rollback"]["passed"] is True, "formal rollback evidence missing")
    require((project / "健身工作台.html").read_bytes() == before, "failed checker did not restore formal HTML")


def test_project_path_gate(builder_scripts: Path, root: Path) -> None:
    project = make_project(root, "path-gate")
    requested = project / "forbidden-receipt.json"
    result = run(
        [
            sys.executable,
            str(builder_scripts / "Refresh-FitnessWorkbench.py"),
            "--project",
            str(project),
            "--backup-dir",
            str(project / "forbidden-backup"),
            "--receipt",
            str(requested),
        ]
    )
    require(result.returncode != 0, "project-internal evidence paths must be rejected")
    require(not requested.exists(), "rejected receipt polluted project")
    require(not (project / "forbidden-backup").exists(), "rejected backup polluted project")


def test_handoff_gate(system_scripts: Path, root: Path) -> None:
    project = make_project(root, "handoff-project")
    records = project / "工作台与工具" / "交接记录"
    artifact = project / "训练复盘与状态" / "训练复盘" / "review.md"
    write(artifact, "confirmed review")
    base = {
        "schema": 1,
        "source_skill": "lzheng-strength-training-review",
        "target_skill": "lzheng-fitness-workbench-builder",
        "user_system_id": "local",
        "event_type": "training_review_completed",
        "created_at": "2026-08-23T12:00:00+08:00",
        "artifacts": [{"type": "review", "path": "训练复盘与状态/训练复盘/review.md"}],
        "requires": {"refresh_workbench": True, "merge_into_current_plan": False},
        "warnings": [],
    }
    legacy = json.loads(json.dumps(base))
    legacy["delivery"] = {"status": "refreshed", "detail": "legacy success"}
    write(records / "20260822-legacy.json", json.dumps(legacy, ensure_ascii=False))
    write(records / "20260823-pending.json", json.dumps(base, ensure_ascii=False))
    backup = root / "handoff-evidence"
    result = run(
        [
            sys.executable,
            str(system_scripts / "Process-LzhengHandoffs.py"),
            "--project",
            str(project),
            "--backup-dir",
            str(backup),
        ]
    )
    require(result.returncode == 0, result.stdout + result.stderr)
    require(load(records / "20260822-legacy.json")["delivery"]["status"] == "refreshed", "legacy refreshed was consumed again")
    delivered = load(records / "20260823-pending.json")["delivery"]
    require(delivered["status"] == "formal_refreshed", "handoff did not use evidence-backed status")
    require(delivered["evidence"]["formal_checker"] == "PASS", "handoff lacks checker PASS evidence")
    receipt_file = backup / "handoff-receipts" / delivered["evidence"]["receipt_file"]
    require(receipt_file.is_file(), "handoff receipt not found outside project")
    require(delivered["evidence"]["receipt_sha256"] == hashlib.sha256(receipt_file.read_bytes()).hexdigest(), "handoff receipt hash mismatch")


def test_actual_script_integration(root: Path) -> None:
    project = root / "actual-integration" / "个人训练系统"
    initialize = HERE / "Initialize-FitnessWorkbench.py"
    result = run([sys.executable, str(initialize), "--target", str(project)])
    require(result.returncode == 0, "actual initialize failed:\n" + result.stdout + result.stderr)
    receipt_path = root / "actual-integration" / "refresh-receipt.json"
    deploy = root / "actual-integration" / "deploy"
    result = run(
        [
            sys.executable,
            str(REFRESH_SOURCE),
            "--project",
            str(project),
            "--backup-dir",
            str(root / "actual-integration" / "evidence"),
            "--receipt",
            str(receipt_path),
            "--deploy",
            str(deploy),
            "--release-mode",
            "public-anonymized",
        ]
    )
    require(result.returncode == 0, "actual refresh integration failed:\n" + result.stdout + result.stderr)
    receipt = load(receipt_path)
    require(receipt["claims"] == {"formal_refreshed": True, "release_prepared": True, "deployed": False, "online_verified": False}, "actual pipeline claims are wrong")
    require((deploy / "release-manifest.json").is_file(), "actual release manifest missing")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="lzheng-refresh-test-") as temporary:
        root = Path(temporary)
        builder_scripts, system_scripts = make_suite(root)
        test_formal_only(builder_scripts, root)
        test_private_confirmation(builder_scripts, root)
        test_main_lift_history_confirmation_and_forwarding(builder_scripts, root)
        test_public_release(builder_scripts, root)
        test_owned_release_replacement(builder_scripts, root)
        test_deploy_target_safety(builder_scripts, root)
        test_checker_failure_rolls_back(builder_scripts, root)
        test_project_path_gate(builder_scripts, root)
        test_handoff_gate(system_scripts, root)
        test_actual_script_integration(root)
    print("FITNESS_WORKBENCH_REFRESH_TEST: PASS")


if __name__ == "__main__":
    main()
