#!/usr/bin/env python3
"""Regression tests for installer drift checks, backups, and custom target roots."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "tools" / "install.py"
SKILL = "lzheng-training-system"


def run(arguments: list[str], expected: int = 0) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [sys.executable, str(INSTALLER), *arguments],
        cwd=str(ROOT),
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    if completed.returncode != expected:
        raise AssertionError(
            f"Unexpected installer exit code {completed.returncode}, expected {expected}\n"
            f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )
    return completed


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def directory_snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def create_junction(link: Path, target: Path) -> None:
    if os.name != "nt":
        os.symlink(target, link, target_is_directory=True)
        return
    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"Could not create junction {link} -> {target}\n"
            f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )


def remove_junction(link: Path) -> None:
    if not os.path.lexists(link):
        return
    if os.name == "nt":
        os.rmdir(link)
    else:
        link.unlink()


def try_create_directory_symlink(link: Path, target: Path) -> bool:
    try:
        os.symlink(target, link, target_is_directory=True)
    except (NotImplementedError, OSError):
        return False
    return True


def remove_directory_symlink(link: Path) -> None:
    if os.path.lexists(link):
        link.unlink()


def assert_unsafe_output(completed: subprocess.CompletedProcess[str], context: str) -> None:
    lowered = completed.stdout.lower()
    require(
        any(word in lowered for word in ("symlink", "junction", "reparse")),
        f"{context} did not identify the unsafe link type",
    )


def test_unsafe_paths(raw_root: Path) -> None:
    outside = raw_root / "junction-outside"
    outside.mkdir()
    sentinel = outside / "sentinel.bin"
    sentinel.write_bytes(b"JUNCTION_SENTINEL\x00\xff\x10")
    before = directory_snapshot(outside)
    junction_target = raw_root / "junction-agent"
    junction_target.mkdir()
    skills_junction = junction_target / "skills"
    create_junction(skills_junction, outside)
    try:
        selection = ["--target-root", str(junction_target), "--skill", SKILL]
        rejected_install = run(selection, expected=1)
        assert_unsafe_output(rejected_install, "junction install")
        rejected_verify = run([*selection, "--verify"], expected=1)
        assert_unsafe_output(rejected_verify, "junction verify")
        require(
            "LZHENG_FITNESS_VERIFY: FAIL" in rejected_verify.stdout,
            "junction verify did not emit a verification failure marker",
        )
        require(directory_snapshot(outside) == before, "junction target outside bytes changed")
        require(sentinel.read_bytes() == before["sentinel.bin"], "junction sentinel bytes changed")
    finally:
        remove_junction(skills_junction)

    symlink_outside = raw_root / "symlink-outside"
    symlink_outside.mkdir()
    (symlink_outside / "sentinel.bin").write_bytes(b"SYMLINK_SENTINEL\x00\x01")
    symlink_before = directory_snapshot(symlink_outside)
    symlink_target = raw_root / "symlink-agent"
    symlink_target.mkdir()
    skills_symlink = symlink_target / "skills"
    if try_create_directory_symlink(skills_symlink, symlink_outside):
        try:
            selection = ["--target-root", str(symlink_target), "--skill", SKILL]
            assert_unsafe_output(run(selection, expected=1), "symlink install")
            assert_unsafe_output(run([*selection, "--verify"], expected=1), "symlink verify")
            require(
                directory_snapshot(symlink_outside) == symlink_before,
                "symlink target outside bytes changed",
            )
        finally:
            remove_directory_symlink(skills_symlink)

    source_skill = ROOT / "skills" / SKILL / "SKILL.md"
    source_before = source_skill.read_bytes()
    source_selection = ["--target-root", str(ROOT), "--skill", SKILL]
    source_rejected = run(source_selection, expected=1)
    require("source repository" in source_rejected.stdout.lower(), "source target was not rejected")
    source_verify = run([*source_selection, "--verify"], expected=1)
    require("source repository" in source_verify.stdout.lower(), "source verify was not rejected")
    require(source_skill.read_bytes() == source_before, "source repository Skill bytes changed")

    state_outside = raw_root / "state-outside"
    state_outside.mkdir()
    (state_outside / "sentinel.bin").write_bytes(b"STATE_SENTINEL\x00\xfe")
    state_before = directory_snapshot(state_outside)
    state_target = raw_root / "state-junction-agent"
    state_target.mkdir()
    state_junction = state_target / ".lzheng-fitness"
    create_junction(state_junction, state_outside)
    try:
        state_selection = ["--target-root", str(state_target), "--skill", SKILL]
        assert_unsafe_output(run(state_selection, expected=1), "state junction install")
        assert_unsafe_output(
            run([*state_selection, "--verify"], expected=1),
            "state junction verify",
        )
        require(directory_snapshot(state_outside) == state_before, "state junction outside bytes changed")
    finally:
        remove_junction(state_junction)

    backup_target = raw_root / "backup-junction-agent"
    backup_selection = ["--target-root", str(backup_target), "--skill", SKILL]
    run(backup_selection)
    active_skill = backup_target / "skills" / SKILL / "SKILL.md"
    active_skill.write_bytes(active_skill.read_bytes() + b"\nBACKUP_REPARSE_DRIFT\n")
    active_before = active_skill.read_bytes()
    state_file = backup_target / ".lzheng-fitness" / "install-state.json"
    installer_state_before = state_file.read_bytes()
    backup_outside = raw_root / "backup-outside"
    backup_outside.mkdir()
    (backup_outside / "sentinel.bin").write_bytes(b"BACKUP_SENTINEL\x00\xfd")
    backup_before = directory_snapshot(backup_outside)
    backup_junction = backup_target / "unsafe-backups"
    create_junction(backup_junction, backup_outside)
    try:
        rejected_backup = run(
            [*backup_selection, "--force", "--backup-root", "unsafe-backups"],
            expected=1,
        )
        assert_unsafe_output(rejected_backup, "backup junction")
        require(active_skill.read_bytes() == active_before, "backup rejection changed active Skill")
        require(state_file.read_bytes() == installer_state_before, "backup rejection changed installer state")
        require(directory_snapshot(backup_outside) == backup_before, "backup junction outside bytes changed")
    finally:
        remove_junction(backup_junction)

    file_target = raw_root / "file-destination-agent"
    file_skills = file_target / "skills"
    file_skills.mkdir(parents=True)
    file_destination = file_skills / SKILL
    file_destination.write_bytes(b"NOT_A_DIRECTORY\x00\xfc")
    file_before = file_destination.read_bytes()
    file_selection = ["--target-root", str(file_target), "--skill", SKILL]
    file_install = run(file_selection, expected=1)
    require("expected a directory" in file_install.stdout, "file destination install was not rejected")
    file_verify = run([*file_selection, "--verify"], expected=1)
    require("expected a directory" in file_verify.stdout, "file destination verify was not rejected")
    require(file_destination.read_bytes() == file_before, "file destination bytes changed")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="lzheng-fitness-installer-test-") as raw:
        raw_root = Path(raw)
        test_unsafe_paths(raw_root)

        target = raw_root / "自定义 Agent 目录"
        selection = ["--target-root", str(target), "--skill", SKILL]

        installed = run(selection)
        require("LZHENG_FITNESS_INSTALL: PASS" in installed.stdout, "clean install did not pass")
        skill_root = target / "skills" / SKILL
        state = target / ".lzheng-fitness" / "install-state.json"
        require(skill_root.is_dir(), "custom target root did not receive the Skill")
        require(state.is_file(), "post-install manifest state was not recorded")

        verified = run([*selection, "--verify"])
        require("LZHENG_FITNESS_VERIFY: PASS" in verified.stdout, "clean install did not verify")

        refused = run(selection, expected=1)
        require("Refusing to overwrite existing Skill" in refused.stdout, "non-force reinstall was not refused")

        skill_file = skill_root / "SKILL.md"
        original = skill_file.read_text(encoding="utf-8")
        skill_file.write_text(original + "\nlocal drift\n", encoding="utf-8")
        extra = skill_root / "local-private-adapter.py"
        extra.write_text("LOCAL_ADAPTER_SENTINEL = True\n", encoding="utf-8")
        private_adapter = target / ".lzheng-fitness" / "private-adapters" / "notion-sync.txt"
        private_adapter.parent.mkdir(parents=True, exist_ok=True)
        private_adapter.write_text("PRIVATE_ADAPTER_UNTOUCHED\n", encoding="utf-8")

        drift = run([*selection, "--verify"], expected=1)
        require("changed (1): SKILL.md" in drift.stdout, "changed file was not reported")
        require("extra (1): local-private-adapter.py" in drift.stdout, "extra file was not reported")

        invalid_backup = target / "skills" / "backups"
        rejected = run([*selection, "--force", "--backup-root", str(invalid_backup)], expected=1)
        require("Backup root must be outside" in rejected.stdout, "active-root backup was not rejected")
        require(extra.is_file(), "rejected backup location changed the existing Skill")

        forced = run([*selection, "--force"])
        require("LZHENG_FITNESS_INSTALL: PASS" in forced.stdout, "force install did not pass")
        require(private_adapter.read_text(encoding="utf-8") == "PRIVATE_ADAPTER_UNTOUCHED\n", "private adapter was modified")
        require(not extra.exists(), "destination-only file leaked back into the public Skill")

        default_backups = target / ".lzheng-fitness" / "backups"
        backup_skills = list(default_backups.glob(f"*/{SKILL}"))
        require(len(backup_skills) == 1, "force install did not create one external backup")
        require((backup_skills[0] / "local-private-adapter.py").is_file(), "extra local file was not preserved in backup")
        require(
            (backup_skills[0] / "SKILL.md").read_text(encoding="utf-8").endswith("local drift\n"),
            "changed core file was not preserved in backup",
        )
        require(not any(path.name.startswith(f"{SKILL}.backup-") for path in (target / "skills").iterdir()), "backup remained in active skills root")

        run([*selection, "--verify"])

        skill_file.write_text(original + "\nsecond drift\n", encoding="utf-8")
        custom_backup = target / "installer-backups"
        custom = run([*selection, "--force", "--backup-root", "installer-backups"])
        require("LZHENG_FITNESS_INSTALL: PASS" in custom.stdout, "custom backup force install failed")
        require(len(list(custom_backup.glob(f"*/{SKILL}"))) == 1, "custom backup root was not used")
        require(private_adapter.read_text(encoding="utf-8") == "PRIVATE_ADAPTER_UNTOUCHED\n", "custom backup install modified private adapter")
        run([*selection, "--verify"])

    print("LZHENG_FITNESS_INSTALLER_TEST: PASS")


if __name__ == "__main__":
    main()
