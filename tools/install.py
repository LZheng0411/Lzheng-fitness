#!/usr/bin/env python3
"""Install one or more Lzheng Fitness Skills into a compatible Agent home."""

from __future__ import annotations

import argparse
import os
import shutil
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPO_ROOT / "skills"
SKILLS = (
    "lzheng-fitness-plan",
    "lzheng-training-return",
    "lzheng-strength-cycle-planner",
    "lzheng-strength-training-review",
    "lzheng-training-system",
    "lzheng-fitness-workbench-builder",
)


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
        raise SystemExit(f"Invalid source Skill: {source}")
    text = skill_file.read_text(encoding="utf-8")
    if f"name: {name}" not in text:
        raise SystemExit(f"SKILL.md name does not match folder: {name}")
    return source


def install_skill(name: str, skills_root: Path, force: bool) -> Path:
    source = verify_source(name)
    skills_root.mkdir(parents=True, exist_ok=True)
    destination = skills_root / name

    if destination.exists():
        if not force:
            raise SystemExit(
                f"Refusing to overwrite existing Skill: {destination}. "
                "Use --force only after reviewing the existing installation."
            )
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = skills_root / f"{name}.backup-{stamp}"
        destination.replace(backup)
        print(f"Backed up existing Skill to: {backup}")

    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", "Thumbs.db"),
    )
    if not (destination / "SKILL.md").is_file():
        raise SystemExit(f"Installation verification failed: {destination}")
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="Install portable Lzheng Fitness Skills.")
    parser.add_argument("--platform", choices=("codex", "claude", "agents"), default="codex")
    parser.add_argument("--skill", action="append", choices=SKILLS, help="Skill to install; repeat as needed")
    parser.add_argument("--all", action="store_true", help="Install all Lzheng Fitness Skills")
    parser.add_argument(
        "--target-root",
        type=Path,
        help="Custom Agent root; Skills are installed into <target-root>/skills",
    )
    parser.add_argument("--force", action="store_true", help="Back up and replace an existing installation")
    parser.add_argument("--list", action="store_true", help="List available Skills and exit")
    args = parser.parse_args()

    if args.list:
        print("\n".join(SKILLS))
        return

    selected = list(SKILLS) if args.all else list(dict.fromkeys(args.skill or []))
    if not selected:
        parser.error("Choose --all or at least one --skill.")

    agent_root = args.target_root.expanduser() if args.target_root else default_agent_root(args.platform)
    skills_root = agent_root / "skills"
    installed = [install_skill(name, skills_root, args.force) for name in selected]

    print("Installed Lzheng Fitness Skills:")
    for path in installed:
        print(f"- {path}")


if __name__ == "__main__":
    main()
