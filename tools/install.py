#!/usr/bin/env python3
"""Install and verify Lzheng Fitness Skills without hiding local drift."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import tempfile
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPO_ROOT / "skills"
SKILLS = (
    "lzheng-fitness-plan",
    "lzheng-training-return",
    "lzheng-strength-cycle-planner",
    "lzheng-strength-training-review",
    "lzheng-training-expert-library",
    "lzheng-nutrition-system",
    "lzheng-training-system",
    "lzheng-fitness-workbench-builder",
)
EXPERT_DEPENDENTS = {
    "lzheng-fitness-plan",
    "lzheng-training-return",
    "lzheng-strength-cycle-planner",
    "lzheng-strength-training-review",
    "lzheng-nutrition-system",
}
IGNORED_NAMES = {"__pycache__", ".DS_Store", "Thumbs.db"}
INSTALL_STATE_SCHEMA = 1


class InstallFailure(RuntimeError):
    pass


def default_agent_root(platform: str) -> Path:
    if platform == "codex":
        configured = os.environ.get("CODEX_HOME")
        return Path(configured).expanduser() if configured else Path.home() / ".codex"
    if platform == "claude":
        return Path.home() / ".claude"
    if platform == "agents":
        return Path.home() / ".agents"
    raise ValueError(f"Unsupported platform: {platform}")


def verify_source(name: str) -> Path:
    source = SOURCE_ROOT / name
    skill_file = source / "SKILL.md"
    if not source.is_dir() or not skill_file.is_file():
        raise InstallFailure(f"Invalid source Skill: {source}")
    text = skill_file.read_text(encoding="utf-8")
    if f"name: {name}" not in text:
        raise InstallFailure(f"SKILL.md name does not match folder: {name}")
    return source


def ignored(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    return any(part in IGNORED_NAMES for part in relative.parts) or path.suffix.lower() == ".pyc"


def lexical_absolute(path: Path) -> Path:
    """Return an absolute path without resolving links or junctions."""
    return Path(os.path.abspath(os.fspath(path.expanduser())))


def is_reparse_point(path: Path) -> bool:
    """Detect symlinks, Windows junctions, and other Windows reparse points."""
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    if callable(is_junction) and is_junction():
        return True
    if os.name == "nt":
        try:
            attributes = getattr(os.lstat(path), "st_file_attributes", 0)
        except OSError:
            return False
        return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    return False


def existing_components(path: Path) -> list[Path]:
    """List existing path components from the filesystem anchor to the target."""
    target = lexical_absolute(path)
    chain: list[Path] = []
    current = target
    while True:
        chain.append(current)
        if current.parent == current:
            break
        current = current.parent
    return [component for component in reversed(chain) if os.path.lexists(component)]


def reject_reparse_components(path: Path, label: str) -> None:
    for component in existing_components(path):
        if is_reparse_point(component):
            raise InstallFailure(
                f"Unsafe {label}: symlink, junction, or reparse component is not allowed: {component}"
            )


def require_directory_if_existing(path: Path, label: str) -> None:
    target = lexical_absolute(path)
    for component in existing_components(target):
        if is_reparse_point(component):
            raise InstallFailure(
                f"Unsafe {label}: symlink, junction, or reparse component is not allowed: "
                f"{component}"
            )
        if not component.is_dir():
            raise InstallFailure(
                f"Unsafe {label}: expected a directory, found a non-directory component: "
                f"{component}"
            )


def file_manifest(root: Path) -> dict[str, dict[str, object]]:
    """Return the portable file list and SHA-256 digest for one Skill tree."""
    root = lexical_absolute(root)
    require_directory_if_existing(root, "manifest root")
    if not root.is_dir():
        raise InstallFailure(f"Manifest root does not exist: {root}")
    result: dict[str, dict[str, object]] = {}
    for current_raw, directories, files in os.walk(root, topdown=True, followlinks=False):
        current = Path(current_raw)
        safe_directories: list[str] = []
        for name in sorted(directories):
            candidate = current / name
            if ignored(candidate, root):
                continue
            if is_reparse_point(candidate):
                raise InstallFailure(
                    f"Symlink, junction, or reparse directory is not allowed in a Skill: {candidate}"
                )
            safe_directories.append(name)
        directories[:] = safe_directories
        for name in sorted(files):
            path = current / name
            if ignored(path, root):
                continue
            if is_reparse_point(path):
                raise InstallFailure(
                    f"Symlink or reparse file is not allowed in a Skill: {path}"
                )
            relative = path.relative_to(root).as_posix()
            result[relative] = {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "size": path.stat().st_size,
            }
    return result


def manifest_digest(manifest: dict[str, dict[str, object]]) -> str:
    payload = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compare_manifests(
    expected: dict[str, dict[str, object]], actual: dict[str, dict[str, object]]
) -> dict[str, list[str]]:
    expected_names = set(expected)
    actual_names = set(actual)
    return {
        "missing": sorted(expected_names - actual_names),
        "changed": sorted(name for name in expected_names & actual_names if expected[name] != actual[name]),
        "extra": sorted(actual_names - expected_names),
    }


def is_clean(report: dict[str, list[str]]) -> bool:
    return not any(report.values())


def summarize_paths(paths: list[str], limit: int = 12) -> str:
    visible = paths[:limit]
    suffix = f" ... and {len(paths) - limit} more" if len(paths) > limit else ""
    return ", ".join(visible) + suffix


def print_drift(name: str, report: dict[str, list[str]]) -> None:
    print(f"- {name}: DRIFT")
    for label in ("missing", "changed", "extra"):
        if report[label]:
            print(f"  {label} ({len(report[label])}): {summarize_paths(report[label])}")


def path_is_within(path: Path, parent: Path) -> bool:
    try:
        common = os.path.commonpath(
            [os.path.normcase(str(path)), os.path.normcase(str(parent))]
        )
    except ValueError:
        return False
    return common == os.path.normcase(str(parent))


def paths_overlap(first: Path, second: Path) -> bool:
    return path_is_within(first, second) or path_is_within(second, first)


def safe_resolve(path: Path, label: str) -> Path:
    candidate = lexical_absolute(path)
    reject_reparse_components(candidate, label)
    return candidate.resolve(strict=False)


def reject_source_overlap(path: Path, label: str) -> None:
    source_repository = REPO_ROOT.resolve(strict=True)
    if paths_overlap(path, source_repository):
        raise InstallFailure(
            f"Unsafe {label}: path must not alias, contain, or be inside the source repository: "
            f"{path} (source: {source_repository})"
        )


def require_within(path: Path, parent: Path, label: str) -> None:
    if not path_is_within(path, parent):
        raise InstallFailure(f"Unsafe {label}: resolved path escapes {parent}: {path}")


def validate_agent_layout(configured_root: Path, selected: list[str]) -> tuple[Path, Path]:
    """Validate every managed path before reading state or mutating the target."""
    agent_root = lexical_absolute(configured_root)
    require_directory_if_existing(agent_root, "target root")
    resolved_agent_root = safe_resolve(agent_root, "target root")
    reject_source_overlap(resolved_agent_root, "target root")

    skills_root = agent_root / "skills"
    require_directory_if_existing(skills_root, "skills root")
    resolved_skills_root = safe_resolve(skills_root, "skills root")
    require_within(resolved_skills_root, resolved_agent_root, "skills root")
    reject_source_overlap(resolved_skills_root, "skills root")

    state_parent = agent_root / ".lzheng-fitness"
    require_directory_if_existing(state_parent, "installer state directory")
    resolved_state_parent = safe_resolve(state_parent, "installer state directory")
    require_within(resolved_state_parent, resolved_agent_root, "installer state directory")
    reject_source_overlap(resolved_state_parent, "installer state directory")

    state_path = install_state_path(agent_root)
    reject_reparse_components(state_path, "installer state file")
    if os.path.lexists(state_path) and not state_path.is_file():
        raise InstallFailure(
            f"Unsafe installer state file: expected a regular file, found: {state_path}"
        )
    resolved_state_path = safe_resolve(state_path, "installer state file")
    require_within(resolved_state_path, resolved_state_parent, "installer state file")
    reject_source_overlap(resolved_state_path, "installer state file")

    for name in selected:
        destination = skills_root / name
        require_directory_if_existing(destination, f"Skill destination {name}")
        resolved_destination = safe_resolve(destination, f"Skill destination {name}")
        require_within(resolved_destination, resolved_skills_root, f"Skill destination {name}")
        reject_source_overlap(resolved_destination, f"Skill destination {name}")

    return agent_root, skills_root


def validate_skill_destination(destination: Path, skills_root: Path, name: str) -> None:
    require_directory_if_existing(destination, f"Skill destination {name}")
    resolved_destination = safe_resolve(destination, f"Skill destination {name}")
    resolved_skills_root = safe_resolve(skills_root, "skills root")
    require_within(resolved_destination, resolved_skills_root, f"Skill destination {name}")
    reject_source_overlap(resolved_destination, f"Skill destination {name}")


def resolve_backup_root(agent_root: Path, skills_root: Path, configured: Path | None) -> Path:
    resolved_agent_root = safe_resolve(agent_root, "target root")
    resolved_skills_root = safe_resolve(skills_root, "skills root")
    explicitly_absolute = False
    if configured is None:
        backup_root = agent_root / ".lzheng-fitness" / "backups"
    else:
        expanded = configured.expanduser()
        explicitly_absolute = expanded.is_absolute()
        backup_root = expanded if expanded.is_absolute() else agent_root / expanded
    backup_root = lexical_absolute(backup_root)
    require_directory_if_existing(backup_root, "backup root")
    resolved_backup_root = safe_resolve(backup_root, "backup root")
    if not explicitly_absolute:
        require_within(resolved_backup_root, resolved_agent_root, "backup root")
    if paths_overlap(resolved_backup_root, resolved_skills_root):
        raise InstallFailure(
            "Backup root must be outside and must not contain the active skills directory: "
            + str(backup_root)
        )
    reject_source_overlap(resolved_backup_root, "backup root")
    return backup_root


def validate_backup_run(backup_run: Path, backup_root: Path, skills_root: Path) -> None:
    reject_reparse_components(backup_run, "backup run directory")
    if os.path.lexists(backup_run):
        raise InstallFailure(f"Backup run directory already exists: {backup_run}")
    resolved_backup_root = safe_resolve(backup_root, "backup root")
    resolved_backup_run = safe_resolve(backup_run, "backup run directory")
    resolved_skills_root = safe_resolve(skills_root, "skills root")
    require_within(resolved_backup_run, resolved_backup_root, "backup run directory")
    if paths_overlap(resolved_backup_run, resolved_skills_root):
        raise InstallFailure(
            "Backup run directory must be outside the active skills directory: " + str(backup_run)
        )
    reject_source_overlap(resolved_backup_run, "backup run directory")


def install_state_path(agent_root: Path) -> Path:
    return agent_root / ".lzheng-fitness" / "install-state.json"


def read_install_state(agent_root: Path) -> dict[str, object]:
    path = install_state_path(agent_root)
    reject_reparse_components(path, "installer state file")
    if not path.is_file():
        return {"schema": INSTALL_STATE_SCHEMA, "skills": {}}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InstallFailure(f"Cannot read installer state {path}: {exc}") from exc
    if value.get("schema") != INSTALL_STATE_SCHEMA or not isinstance(value.get("skills"), dict):
        raise InstallFailure(f"Unsupported installer state: {path}")
    return value


def write_install_state(agent_root: Path, state: dict[str, object]) -> Path:
    path = install_state_path(agent_root)
    resolved_agent_root = safe_resolve(agent_root, "target root")
    state_parent = path.parent
    require_directory_if_existing(state_parent, "installer state directory")
    resolved_state_parent = safe_resolve(state_parent, "installer state directory")
    require_within(resolved_state_parent, resolved_agent_root, "installer state directory")
    reject_source_overlap(resolved_state_parent, "installer state directory")
    path.parent.mkdir(parents=True, exist_ok=True)
    require_directory_if_existing(state_parent, "installer state directory")
    reject_reparse_components(path, "installer state file")
    if os.path.lexists(path) and not path.is_file():
        raise InstallFailure(
            f"Unsafe installer state file: expected a regular file, found: {path}"
        )
    payload = json.dumps(state, ensure_ascii=False, indent=2) + "\n"
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=state_parent,
            prefix="install-state.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(payload)
            temporary = Path(handle.name)
        reject_reparse_components(state_parent, "installer state directory")
        os.replace(temporary, path)
    finally:
        if temporary is not None and os.path.lexists(temporary):
            temporary.unlink()
    return path


def selected_skills(args: argparse.Namespace, parser: argparse.ArgumentParser) -> list[str]:
    requested = list(SKILLS) if args.all else list(dict.fromkeys(args.skill or []))
    if args.verify and not requested:
        requested = list(SKILLS)
    if not requested:
        parser.error("Choose --all or at least one --skill.")
    desired = set(requested)
    if desired & EXPERT_DEPENDENTS:
        desired.add("lzheng-training-expert-library")
    return [name for name in SKILLS if name in desired]


def verify_install(selected: list[str], skills_root: Path, state: dict[str, object]) -> bool:
    print("LZHENG_FITNESS_VERIFY:")
    success = True
    recorded_skills = state.get("skills", {}) if isinstance(state.get("skills"), dict) else {}
    for name in selected:
        source = verify_source(name)
        destination = skills_root / name
        if not destination.is_dir():
            success = False
            print(f"- {name}: MISSING ({destination})")
            continue
        expected = file_manifest(source)
        actual = file_manifest(destination)
        source_report = compare_manifests(expected, actual)
        if not is_clean(source_report):
            success = False
            print_drift(name, source_report)
            continue
        recorded = recorded_skills.get(name) if isinstance(recorded_skills, dict) else None
        recorded_digest = recorded.get("manifest_sha256") if isinstance(recorded, dict) else None
        digest = manifest_digest(actual)
        state_note = "recorded" if recorded_digest == digest else "source-exact; state unavailable or older"
        print(f"- {name}: PASS files={len(actual)} sha256={digest} ({state_note})")
    print("LZHENG_FITNESS_VERIFY: " + ("PASS" if success else "FAIL"))
    return success


def copy_and_verify(source: Path, staging: Path) -> tuple[dict[str, dict[str, object]], str]:
    expected = file_manifest(source)
    shutil.copytree(
        source,
        staging,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", "Thumbs.db"),
    )
    staged = file_manifest(staging)
    report = compare_manifests(expected, staged)
    if not is_clean(report):
        raise InstallFailure(
            f"Staged files differ from source {source.name}: " + json.dumps(report, ensure_ascii=False)
        )
    return expected, manifest_digest(expected)


def install_skill(
    name: str,
    skills_root: Path,
    force: bool,
    backup_run: Path | None,
) -> tuple[Path, dict[str, dict[str, object]], str, Path | None]:
    source = verify_source(name)
    destination = skills_root / name
    require_directory_if_existing(skills_root, "skills root")
    validate_skill_destination(destination, skills_root, name)
    if os.path.lexists(destination) and not force:
        raise InstallFailure(
            f"Refusing to overwrite existing Skill: {destination}. "
            "Run --verify first and use --force only after reviewing the drift."
        )

    with tempfile.TemporaryDirectory(prefix=f"lzheng-fitness-install-{name}-") as raw:
        staging = Path(raw) / name
        expected, digest = copy_and_verify(source, staging)
        backup: Path | None = None
        require_directory_if_existing(skills_root, "skills root")
        validate_skill_destination(destination, skills_root, name)
        if os.path.lexists(destination):
            if backup_run is None:
                raise InstallFailure("Internal error: force install has no external backup directory")
            existing = file_manifest(destination)
            report = compare_manifests(expected, existing)
            if is_clean(report):
                print(f"Existing Skill is source-exact before replacement: {name}")
            else:
                print("Existing Skill drift preserved in external backup:")
                print_drift(name, report)
            backup = backup_run / name
            require_directory_if_existing(backup_run, "backup run directory")
            resolved_backup_run = safe_resolve(backup_run, "backup run directory")
            reject_reparse_components(backup, f"backup destination {name}")
            resolved_backup = safe_resolve(backup, f"backup destination {name}")
            require_within(resolved_backup, resolved_backup_run, f"backup destination {name}")
            reject_source_overlap(resolved_backup, f"backup destination {name}")
            if os.path.lexists(backup):
                raise InstallFailure(f"Backup destination already exists: {backup}")
            validate_skill_destination(destination, skills_root, name)
            shutil.move(str(destination), str(backup))

        try:
            require_directory_if_existing(skills_root, "skills root")
            skills_root.mkdir(parents=True, exist_ok=True)
            require_directory_if_existing(skills_root, "skills root")
            validate_skill_destination(destination, skills_root, name)
            shutil.move(str(staging), str(destination))
            installed = file_manifest(destination)
            report = compare_manifests(expected, installed)
            if not is_clean(report):
                raise InstallFailure(
                    f"Post-install manifest mismatch for {name}: "
                    + json.dumps(report, ensure_ascii=False)
                )
        except Exception:
            if os.path.lexists(destination):
                validate_skill_destination(destination, skills_root, name)
                shutil.rmtree(destination)
            if backup and os.path.lexists(backup):
                require_directory_if_existing(backup, f"backup destination {name}")
                validate_skill_destination(destination, skills_root, name)
                shutil.move(str(backup), str(destination))
            raise

    return destination, expected, digest, backup


def print_ai_onboarding(agent_root: Path) -> None:
    """Print an explicit next reply for an Agent that just performed installation."""
    print("\nLZHENG_FITNESS_AI_ONBOARDING:")
    print("安装已完成。不要让用户先看 README 或寻找命令。")
    print("请直接告诉用户：我现在开始帮你建立个人健身系统。你的主要目标是增肌、减脂、力量，还是综合改善？")
    print("用户也只需在新聊天说：开始建立我的健身系统。")
    print("随后 AI 应依次完成：")
    print("1. 初始化个人训练系统和饿狼风格离线工作台；")
    print("2. 询问建档所需的目标、近期训练、时间、器械、恢复与限制；")
    print("3. 记录已有动作基准，或逐个指导未知动作完成安全的重量校准；")
    print("4. 生成第一版正式计划，再由每次训练复盘持续更新下一次明确处方和工作台。")
    print("如当前聊天未识别新 Skill，请新开一个聊天后只说：开始建立我的健身系统。")
    print("安装位置：" + str(agent_root / "skills"))
    print("私人适配器目录（安装器不会修改）：" + str(agent_root / ".lzheng-fitness" / "private-adapters"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Install or verify portable Lzheng Fitness Skills.")
    parser.add_argument("--platform", choices=("codex", "claude", "agents"), default="codex")
    parser.add_argument("--skill", action="append", choices=SKILLS, help="Skill to install or verify; repeat as needed")
    parser.add_argument("--all", action="store_true", help="Install or verify all Lzheng Fitness Skills")
    parser.add_argument(
        "--target-root",
        type=Path,
        help="Custom Agent root; Skills are managed in <target-root>/skills",
    )
    parser.add_argument("--force", action="store_true", help="Back up outside skills and replace an existing installation")
    parser.add_argument(
        "--backup-root",
        type=Path,
        help="Force-install backup root; relative paths resolve from target root",
    )
    parser.add_argument("--verify", action="store_true", help="Read-only drift check; do not install or replace files")
    parser.add_argument("--list", action="store_true", help="List available Skills and exit")
    args = parser.parse_args()

    if args.list:
        print("\n".join(SKILLS))
        return
    if args.verify and args.force:
        parser.error("--verify cannot be combined with --force")
    if args.verify and args.backup_root:
        parser.error("--backup-root is only used during installation")

    selected = selected_skills(args, parser)
    configured_root = args.target_root.expanduser() if args.target_root else default_agent_root(args.platform)

    try:
        agent_root, skills_root = validate_agent_layout(configured_root, selected)
        state = read_install_state(agent_root)
        if args.verify:
            raise SystemExit(0 if verify_install(selected, skills_root, state) else 1)

        backup_run: Path | None = None
        backup_root: Path | None = None
        if args.force:
            backup_root = resolve_backup_root(agent_root, skills_root, args.backup_root)
        if backup_root is not None and any(
            os.path.lexists(skills_root / name) for name in selected
        ):
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            backup_run = backup_root / stamp
            validate_backup_run(backup_run, backup_root, skills_root)
            backup_run.mkdir(parents=True, exist_ok=False)
            require_directory_if_existing(backup_run, "backup run directory")
            resolved_backup_run = safe_resolve(backup_run, "backup run directory")
            require_within(
                resolved_backup_run,
                safe_resolve(backup_root, "backup root"),
                "backup run directory",
            )
            reject_source_overlap(resolved_backup_run, "backup run directory")

        installed: list[tuple[Path, dict[str, dict[str, object]], str, Path | None]] = []
        for name in selected:
            installed.append(install_skill(name, skills_root, args.force, backup_run))

        now = datetime.now().astimezone().isoformat(timespec="seconds")
        state_skills = state.setdefault("skills", {})
        if not isinstance(state_skills, dict):
            raise InstallFailure("Installer state skills field is invalid")
        for path, manifest, digest, backup in installed:
            state_skills[path.name] = {
                "installed_at": now,
                "manifest_sha256": digest,
                "files": manifest,
                "backup": str(backup) if backup else None,
            }
        state["schema"] = INSTALL_STATE_SCHEMA
        state["updated_at"] = now
        state["source_version"] = json.loads(
            (REPO_ROOT / "lzheng-fitness.manifest.json").read_text(encoding="utf-8")
        ).get("version")
        state_path = write_install_state(agent_root, state)

        print("Installed Lzheng Fitness Skills:")
        for path, manifest, digest, backup in installed:
            print(f"- {path} files={len(manifest)} sha256={digest}")
            if backup:
                print(f"  backup: {backup}")
        print("Installer state: " + str(state_path))
        if backup_run:
            print("External backup root: " + str(backup_run))
        if not verify_install(selected, skills_root, state):
            raise InstallFailure("Post-install verification failed")
        print("LZHENG_FITNESS_INSTALL: PASS")
        print_ai_onboarding(agent_root)
    except InstallFailure as exc:
        if args.verify:
            print("LZHENG_FITNESS_VERIFY:")
            print("- installer safety: FAIL (" + str(exc) + ")")
            print("LZHENG_FITNESS_VERIFY: FAIL")
        else:
            print("LZHENG_FITNESS_INSTALL: FAIL")
            print("- " + str(exc))
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
