#!/usr/bin/env python3
"""Portable bootstrap, doctor, upgrade and validation commands for Lzheng Fitness System."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SUITE_VERSION = "3.1.1"
PORTABLE_CONFIG_VERSION = 1
PROJECT_RELATIVE = Path("个人训练系统")
BACKUP_RELATIVE = Path("系统/backups")
RUNTIME_SKILLS = "@runtime"
WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")
CORE_SKILLS = (
    "lzheng-fitness-plan",
    "lzheng-strength-cycle-planner",
    "lzheng-strength-training-review",
    "lzheng-training-return",
    "lzheng-training-expert-library",
    "lzheng-nutrition-system",
    "lzheng-fitness-workbench-builder",
)
OUTPUT_LOCATIONS = {
    "profiles": "个人训练系统/训练复盘与状态/状态档案",
    "plans": "个人训练系统/训练与周期/当前周期",
    "cycles": "个人训练系统/训练与周期/力量周期",
    "reviews": "个人训练系统/训练复盘与状态/训练复盘",
    "returns": "个人训练系统/训练复盘与状态/状态档案",
    "nutrition": "个人训练系统/工作台与工具/饮食工作台",
}
HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent.parent


def stop(message: str) -> None:
    raise SystemExit("LZHENG_TRAINING_SYSTEM: FAIL\n- " + message)


def read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        stop(f"配置无法读取：{path}（{exc}）")
    if not isinstance(data, dict):
        stop(f"配置根节点必须是对象：{path}")
    return data


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def config_path(root: Path) -> Path:
    return root / "系统" / "lzheng-system.json"


def portable_relative(path: Path, root: Path, field: str) -> str:
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError:
        stop(f"{field} 必须位于当前系统根目录内：{path}")
    return relative.as_posix()


def is_machine_absolute(value: object) -> bool:
    text = str(value or "")
    return Path(text).is_absolute() or bool(WINDOWS_ABSOLUTE.match(text)) or text.startswith(("\\\\", "//"))


def safe_relative(root: Path, raw: object, fallback: Path, field: str) -> Path:
    """Resolve a portable config path and reject absolute paths or traversal."""
    value = str(raw or fallback.as_posix())
    candidate = Path(value)
    if is_machine_absolute(value):
        candidate = fallback
    target = (root / candidate).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        stop(f"配置 {field} 越出当前系统根目录")
    return target


def migrate_config(root: Path, path: Path, data: dict) -> dict:
    """Convert legacy machine paths to current-root-relative values in place."""
    desired_project = PROJECT_RELATIVE.as_posix()
    desired_backup = BACKUP_RELATIVE.as_posix()
    changed = False

    project_value = str(data.get("project_root") or "")
    project_candidate = Path(project_value) if project_value else None
    if not project_candidate or is_machine_absolute(project_value):
        data["project_root"] = desired_project
        changed = True
    else:
        resolved = safe_relative(root, project_value, PROJECT_RELATIVE, "project_root")
        portable = portable_relative(resolved, root, "project_root")
        if portable != project_value.replace("\\", "/"):
            data["project_root"] = portable
            changed = True

    if data.get("skills_root") != RUNTIME_SKILLS:
        data["skills_root"] = RUNTIME_SKILLS
        changed = True

    backup_value = str(data.get("backup_root") or "")
    backup_candidate = Path(backup_value) if backup_value else None
    if not backup_candidate or is_machine_absolute(backup_value):
        data["backup_root"] = desired_backup
        changed = True
    else:
        resolved = safe_relative(root, backup_value, BACKUP_RELATIVE, "backup_root")
        portable = portable_relative(resolved, root, "backup_root")
        if portable != backup_value.replace("\\", "/"):
            data["backup_root"] = portable
            changed = True

    if data.get("portable_config_version") != PORTABLE_CONFIG_VERSION:
        data["portable_config_version"] = PORTABLE_CONFIG_VERSION
        changed = True

    if changed:
        migration_root = root / BACKUP_RELATIVE / "config-migrations"
        migration_root.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")
        shutil.copy2(path, migration_root / ("lzheng-system-before-portability-" + stamp + ".json"))
        data["paths_migrated_at"] = dt.datetime.now().astimezone().isoformat(timespec="seconds")
        write_json(path, data)
    return data


def load_config(root: Path) -> dict:
    path = config_path(root)
    if not path.is_file():
        stop("找不到系统配置；请先在空目录运行 bootstrap，或用 --root 指向已有系统")
    data = read_json(path)
    if data.get("schema") != 1:
        stop(f"不支持的配置 schema：{data.get('schema')}")
    return migrate_config(root, path, data)


def load_config_readonly(root: Path) -> dict:
    """Load enough portable config for inspection without migration or backups."""
    path = config_path(root)
    if not path.is_file():
        stop("找不到系统配置；请先在空目录运行 bootstrap，或用 --root 指向已有系统")
    data = read_json(path)
    if data.get("schema") != 1:
        stop(f"不支持的配置 schema：{data.get('schema')}")
    data = dict(data)
    project_value = str(data.get("project_root") or "")
    if not project_value or is_machine_absolute(project_value):
        data["project_root"] = PROJECT_RELATIVE.as_posix()
    return data


def project_path(root: Path, config: dict) -> Path:
    return safe_relative(root, config.get("project_root"), PROJECT_RELATIVE, "project_root")


def backup_path(root: Path, config: dict) -> Path:
    return safe_relative(root, config.get("backup_root"), BACKUP_RELATIVE, "backup_root")


def ensure_empty(target: Path) -> None:
    if target.exists() and any(target.iterdir()):
        stop("bootstrap 只允许空目录，拒绝覆盖已有内容：" + str(target))


def workbench_script(name: str) -> Path:
    candidate = SKILL_ROOT / "lzheng-fitness-workbench-builder" / "scripts" / name
    if not candidate.is_file():
        stop("缺少工作台构建器脚本：" + str(candidate))
    return candidate


def run(command: list[str]) -> None:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    result = subprocess.run(command, text=True, encoding="utf-8", errors="replace", capture_output=True, env=env)
    if result.stdout:
        print(result.stdout.rstrip())
    if result.returncode:
        if result.stderr:
            print(result.stderr.rstrip(), file=sys.stderr)
        stop("命令失败：" + " ".join(command))


def bootstrap(args: argparse.Namespace) -> None:
    root = Path(args.target).resolve()
    ensure_empty(root)
    root.mkdir(parents=True, exist_ok=True)
    backup_root = root / BACKUP_RELATIVE
    project_root = root / PROJECT_RELATIVE
    run([sys.executable, str(workbench_script("Initialize-FitnessWorkbench.py")), "--target", str(project_root), "--brand", args.brand, "--athlete", args.athlete, "--title", args.title])
    knowledge_root = root / "健身知识库"
    for relative, content in {
        "INDEX.md": "# Lzheng 健身系统\n\n- [[个人训练系统/健身工作台|打开个人训练工作台]]\n- [[健身知识库/README|进入健身知识库]]\n\n首次使用：先完成建档，再生成正式计划。\n",
        "健身知识库/README.md": "# 健身知识库\n\n这里只保存可复用训练知识、来源登记与专家模块；私人资料放入 `私人知识包`，默认不参与公开导出。\n",
        "健身知识库/知识索引.md": "# 知识索引\n\n- [[专家系统/README|专家系统]]\n- [[来源登记/README|来源登记]]\n",
        "健身知识库/专家系统/README.md": "# 专家系统\n\n按需接入训练金字塔、增肌、营养、力量、动作模式与运动医学模块；医学危险信号优先转介。\n",
        "健身知识库/来源登记/README.md": "# 来源登记\n\n登记来源、适用边界、审核日期与公开/仅本地范围；不复制受版权保护原文。\n",
        "模板/LZHENG_HANDOFF.example.json": json.dumps({"schema": 1, "source_skill": "", "target_skill": "", "user_system_id": "local", "event_type": "", "created_at": "", "artifacts": [], "requires": {"refresh_workbench": False, "merge_into_current_plan": False}, "warnings": []}, ensure_ascii=False, indent=2) + "\n",
    }.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    managed = {}
    for relative in ("INDEX.md", "健身知识库/README.md", "健身知识库/知识索引.md", "健身知识库/专家系统/README.md", "健身知识库/来源登记/README.md", "模板/LZHENG_HANDOFF.example.json"):
        managed[relative] = sha256(root / relative)
    config = {
        "schema": 1,
        "suite_version": SUITE_VERSION,
        "project_root": PROJECT_RELATIVE.as_posix(),
        "skills_root": RUNTIME_SKILLS,
        "backup_root": BACKUP_RELATIVE.as_posix(),
        "portable_config_version": PORTABLE_CONFIG_VERSION,
        "output_locations": OUTPUT_LOCATIONS,
        "created_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "managed_files": managed,
    }
    write_json(config_path(root), config)
    print("LZHENG_TRAINING_SYSTEM: PASS")
    print("mode: 待建档；请用真实计划替换匿名示例后再开始训练")


def skill_paths(config: dict) -> Path:
    # The running Skill bundle is the source of truth after a computer move.
    path = SKILL_ROOT
    if not path.is_dir():
        stop("Skill 根目录不可用：" + str(path))
    return path


def doctor(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    config = load_config(root)
    problems: list[str] = []
    project_root = project_path(root, config)
    if not project_root.is_dir():
        problems.append("配置 project_root 不可用")
    for relative in ("健身工作台.html", "训练与周期/当前周期", "训练复盘与状态/训练复盘/INDEX.md", "训练复盘与状态/状态档案/INDEX.md"):
        if not (project_root / relative).exists():
            problems.append("缺少主源：" + relative)
    configured_outputs = config.get("output_locations") or OUTPUT_LOCATIONS
    for name, relative in OUTPUT_LOCATIONS.items():
        if configured_outputs.get(name) != relative or not (root / relative).is_dir():
            problems.append("正式产物目录不可用：" + name)
    try:
        skills = skill_paths(config)
        for name in CORE_SKILLS:
            if not (skills / name / "SKILL.md").is_file():
                problems.append("缺少专业 Skill：" + name)
    except SystemExit as exc:
        problems.append(str(exc).split("- ")[-1])
    if problems:
        stop("；".join(problems))
    print("LZHENG_TRAINING_SYSTEM_DOCTOR: PASS")
    print("suite: " + str(config.get("suite_version")))
    print("root: " + str(root))
    print("project: " + str(project_root))


def install_skill(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    config = load_config(root)
    name = args.name
    if name not in CORE_SKILLS:
        stop("仅允许安装已登记的运行依赖 Skill：" + ", ".join(CORE_SKILLS))
    source = skill_paths(config) / name / "SKILL.md"
    if not source.is_file():
        stop("本机未发现请求的 Skill：" + name)
    print("LZHENG_TRAINING_SYSTEM_INSTALL_SKILL: PASS")
    print("skill: " + name)
    print("status: 已由共享 Skill 根目录提供，无需复制到用户项目")


def import_private_pack(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    load_config(root)
    source = Path(args.source).resolve()
    if not source.is_dir():
        stop("私人知识包目录不存在：" + str(source))
    destination = root / "健身知识库" / "私人知识包" / source.name
    if destination.exists():
        stop("同名私人知识包已存在，拒绝覆盖：" + str(destination))
    shutil.copytree(source, destination)
    manifest = {"schema": 1, "scope": "private", "source_name": source.name, "imported_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"), "exclude_from_public_export": True}
    write_json(destination / "knowledge-pack-manifest.json", manifest)
    print("LZHENG_TRAINING_SYSTEM_IMPORT_PRIVATE_PACK: PASS")
    print("destination: " + str(destination))


def upgrade(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    config = load_config(root)
    backup_root = backup_path(root, config)
    backup_root.mkdir(parents=True, exist_ok=True)
    existing = config.get("managed_files", {})
    conflicts = []
    for rel, expected_hash in existing.items():
        path = root / rel
        if path.is_file() and sha256(path) != expected_hash:
            conflicts.append(rel)
    if conflicts:
        print("LZHENG_TRAINING_SYSTEM_UPGRADE: PROTECTED")
        print("用户修改的托管文件未覆盖：" + "、".join(conflicts))
        return
    config["suite_version"] = SUITE_VERSION
    config["upgraded_at"] = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    config["project_root"] = portable_relative(project_path(root, config), root, "project_root")
    config["skills_root"] = RUNTIME_SKILLS
    config["backup_root"] = portable_relative(backup_root, root, "backup_root")
    config["portable_config_version"] = PORTABLE_CONFIG_VERSION
    config["output_locations"] = OUTPUT_LOCATIONS
    for relative in sorted(set(OUTPUT_LOCATIONS.values())):
        (root / relative).mkdir(parents=True, exist_ok=True)
    write_json(config_path(root), config)
    print("LZHENG_TRAINING_SYSTEM_UPGRADE: PASS")
    print("仅升级系统配置；计划、复盘、状态档案和私人知识均未触碰")


def validate(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    doctor(argparse.Namespace(root=str(root)))
    config = load_config(root)
    skills = skill_paths(config)
    codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    validator = codex_home / "skills" / ".system" / "skill-creator" / "scripts" / "quick_validate.py"
    if not validator.is_file():
        stop("找不到 Skill 官方校验器：" + str(validator))
    for name in CORE_SKILLS:
        run([sys.executable, str(validator), str(skills / name)])
    project_root = project_path(root, config)
    run([sys.executable, str(workbench_script("Check-FitnessWorkbench.py")), "--project", str(project_root)])
    print("LZHENG_TRAINING_SYSTEM_VALIDATE: PASS")


def process_handoffs(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    config = load_config(root)
    project_root = project_path(root, config)
    script = HERE / "Process-LzhengHandoffs.py"
    selected_backup = Path(args.backup_dir).resolve() if args.backup_dir else backup_path(root, config) / "workbench-refresh"
    command = [
        sys.executable,
        str(script),
        "--project",
        str(project_root),
        "--backup-dir",
        str(selected_backup),
    ]
    if args.notion:
        command += ["--notion", args.notion]
    if args.notion_mode:
        command += ["--notion-mode", args.notion_mode]
    if args.dry_run:
        command += ["--dry-run"]
    run(command)


def refresh_workbench(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    config = load_config(root)
    project_root = project_path(root, config)
    script = workbench_script("Refresh-FitnessWorkbench.py")
    selected_backup = Path(args.backup_dir).resolve() if args.backup_dir else backup_path(root, config) / "workbench-refresh"
    command = [
        sys.executable,
        str(script),
        "--project",
        str(project_root),
        "--backup-dir",
        str(selected_backup),
    ]
    if args.notion:
        command += ["--notion", args.notion]
    if args.notion_mode:
        command += ["--notion-mode", args.notion_mode]
    if args.replace_main_lift_history:
        command += ["--replace-main-lift-history"]
    if args.confirm_replace_main_lift_history:
        command += ["--confirm-replace-main-lift-history"]
    if args.receipt:
        command += ["--receipt", args.receipt]
    if args.deploy:
        command += ["--deploy", args.deploy]
    if args.release_mode:
        command += ["--release-mode", args.release_mode]
    if args.confirm_private_portable:
        command += ["--confirm-private-portable"]
    run(command)


def inspect_system(args: argparse.Namespace) -> None:
    """Print a compact workbench summary without loading its full HTML into AI context."""
    root = Path(args.root).resolve()
    if config_path(root).is_file():
        config = load_config_readonly(root)
        project_root = project_path(root, config)
    elif (root / "健身工作台.html").is_file():
        project_root = root
    else:
        stop("inspect 需要系统根目录，或直接包含健身工作台.html 的训练项目根目录")
    command = [
        sys.executable,
        str(workbench_script("Inspect-FitnessWorkbench.py")),
        "--project",
        str(project_root),
    ]
    if args.pretty:
        command.append("--pretty")
    run(command)


def main() -> None:
    parser = argparse.ArgumentParser()
    subs = parser.add_subparsers(dest="action", required=True)
    p = subs.add_parser("bootstrap")
    p.add_argument("--target", required=True)
    p.add_argument("--brand", default="LZHENG")
    p.add_argument("--athlete", default="使用者")
    p.add_argument("--title", default="Lzheng 健身工作台")
    p.set_defaults(func=bootstrap)
    for action, fn in (("doctor", doctor), ("upgrade", upgrade), ("validate", validate)):
        p = subs.add_parser(action); p.add_argument("--root", required=True); p.set_defaults(func=fn)
    p = subs.add_parser("inspect"); p.add_argument("--root", required=True); p.add_argument("--pretty", action="store_true"); p.set_defaults(func=inspect_system)
    p = subs.add_parser("process-handoffs"); p.add_argument("--root", required=True); p.add_argument("--notion"); p.add_argument("--notion-mode", choices=("incremental", "full")); p.add_argument("--backup-dir"); p.add_argument("--dry-run", action="store_true"); p.set_defaults(func=process_handoffs)
    p = subs.add_parser("refresh-workbench"); p.add_argument("--root", required=True); p.add_argument("--notion"); p.add_argument("--notion-mode", choices=("incremental", "full")); p.add_argument("--replace-main-lift-history", action="store_true"); p.add_argument("--confirm-replace-main-lift-history", action="store_true"); p.add_argument("--backup-dir"); p.add_argument("--receipt"); p.add_argument("--deploy"); p.add_argument("--release-mode", choices=("private-portable", "public-anonymized")); p.add_argument("--confirm-private-portable", action="store_true"); p.set_defaults(func=refresh_workbench)
    p = subs.add_parser("install-skill"); p.add_argument("--root", required=True); p.add_argument("--name", required=True); p.set_defaults(func=install_skill)
    p = subs.add_parser("import-private-pack"); p.add_argument("--root", required=True); p.add_argument("--source", required=True); p.set_defaults(func=import_private_pack)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
