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


def print_ai_onboarding(agent_root: Path) -> None:
    """Print an explicit next reply for an Agent that just performed installation."""
    print("\nLZHENG_FITNESS_AI_ONBOARDING:")
    print("安装已完成。请直接告诉用户：不要先看 README；现在只需选一个新的空文件夹作为系统根目录。")
    print("建议用户下一句对 AI 说：")
    print('使用 $lzheng-training-system 帮我在 "<空文件夹路径>" 从零搭建我的 AI 健身系统。')
    print("随后 AI 应依次完成：")
    print("1. 初始化个人训练系统和离线工作台；")
    print("2. 询问建档所需的目标、近期训练、时间、器械、恢复与限制；")
    print("3. 生成第一版正式计划，再由每次训练复盘持续更新工作台。")
    print("如当前聊天未识别新 Skill，请新开一个聊天后发送上面的固定句。")
    print("安装位置：" + str(agent_root / "skills"))


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
    print_ai_onboarding(agent_root)


if __name__ == "__main__":
    main()
