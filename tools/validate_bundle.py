#!/usr/bin/env python3
"""Validate metadata, portability, rendering, and clean installation."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = ROOT / "skills"
EXPECTED = (
    "lzheng-fitness-plan",
    "lzheng-training-return",
    "lzheng-strength-cycle-planner",
    "lzheng-strength-training-review",
    "lzheng-training-expert-library",
    "lzheng-training-system",
    "lzheng-fitness-workbench-builder",
)
TEXT_SUFFIXES = {".md", ".json", ".yaml", ".yml", ".py", ".txt"}
BLOCKED = {
    "private Windows absolute path": re.compile(r"\b[A-Za-z]:\\(?:[^\\/:*?\"<>|\r\n]+\\)+"),
    "private macOS home": re.compile(r"/Users/[^/\s]+/"),
    "private Linux home": re.compile(r"/home/[^/\s]+/"),
    "private project name": re.compile(r"lz政系统健身|个人健身知识库|李政"),
}
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
REPOSITORY_BLOCKED = {
    "private Windows absolute path": re.compile(r"\b[A-Za-z]:\\(?:[^\\/:*?\"<>|\r\n]+\\)+"),
    "private macOS home": re.compile(r"/Users/[^/\s]+/"),
    "private Linux home": re.compile(r"/home/[^/\s]+/"),
    "private project identity": re.compile(r"lz政系统健身|个人健身知识库|李政"),
    "possible OpenAI secret": re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    "possible bearer secret": re.compile(r"Bearer\s+[A-Za-z0-9._-]{20,}", re.IGNORECASE),
}


class ValidationFailure(RuntimeError):
    pass


def fail(message: str) -> None:
    raise ValidationFailure(message)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        fail(f"Not UTF-8: {path}: {exc}")
    raise AssertionError("unreachable")


def parse_frontmatter(path: Path) -> dict[str, str]:
    text = read_text(path)
    if not text.startswith("---\n"):
        fail(f"Missing YAML frontmatter: {path}")
    end = text.find("\n---\n", 4)
    if end < 0:
        fail(f"Unclosed YAML frontmatter: {path}")
    fields: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if not line.strip():
            continue
        if ":" not in line:
            fail(f"Invalid frontmatter line in {path}: {line}")
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip().strip('"')
    if set(fields) != {"name", "description"}:
        fail(f"Frontmatter must contain only name and description: {path}")
    return fields


def validate_skill(skill: Path) -> None:
    name = skill.name
    if not re.fullmatch(r"lzheng-[a-z0-9-]+", name):
        fail(f"Invalid Lzheng Skill folder name: {name}")

    skill_md = skill / "SKILL.md"
    agent_yaml = skill / "agents" / "openai.yaml"
    if not skill_md.is_file() or not agent_yaml.is_file():
        fail(f"Missing SKILL.md or agents/openai.yaml: {name}")

    fields = parse_frontmatter(skill_md)
    if fields["name"] != name:
        fail(f"Frontmatter name does not match folder: {name}")
    if len(fields["description"]) < 40:
        fail(f"Description is too short: {name}")

    body = read_text(skill_md)
    if "Lzheng" not in body:
        fail(f"Lzheng branding missing from SKILL.md: {name}")
    if len(body.splitlines()) > 500:
        fail(f"SKILL.md exceeds 500 lines: {name}")

    agent_text = read_text(agent_yaml)
    if "Lzheng" not in agent_text or f"${name}" not in agent_text:
        fail(f"Agent metadata does not identify {name}: {agent_yaml}")

    for path in skill.rglob("*"):
        if path.is_dir():
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = read_text(path)
        for label, pattern in BLOCKED.items():
            if pattern.search(text):
                fail(f"{label} found in {path.relative_to(ROOT)}")
        if path.suffix.lower() == ".md":
            for target in LINK_RE.findall(text):
                target = target.strip().strip("<>").split("#", 1)[0]
                if not target or target.startswith(("http://", "https://", "mailto:")):
                    continue
                resolved = (path.parent / target).resolve()
                if not resolved.exists():
                    fail(f"Broken local link in {path.relative_to(ROOT)}: {target}")

    for script in skill.rglob("*.py"):
        source = read_text(script).lstrip("\ufeff")
        try:
            compile(source, str(script), "exec")
        except SyntaxError as exc:
            fail(f"Python syntax error in {script.relative_to(ROOT)}: {exc}")


def validate_repository_hygiene() -> None:
    for path in ROOT.rglob("*"):
        rel = path.relative_to(ROOT)
        if any(part in {".git", "validation-output", "__pycache__"} for part in rel.parts):
            continue
        if path.resolve() == Path(__file__).resolve():
            continue
        if path.is_dir():
            continue
        if path.is_symlink():
            fail(f"Symlink is not allowed in the portable bundle: {rel}")
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = read_text(path)
        for label, pattern in REPOSITORY_BLOCKED.items():
            if pattern.search(text):
                fail(f"{label} found in repository file: {rel}")


def validate_beginner_guide() -> None:
    guide = ROOT / "BEGINNER-GUIDE.md"
    readme = ROOT / "README.md"
    if not guide.is_file():
        fail("Missing beginner setup guide: BEGINNER-GUIDE.md")

    guide_text = read_text(guide)
    for required in (
        "开始建立我的健身系统",
        "个人训练系统\\健身工作台.html",
        "迁移到新电脑",
        "不要只复制 `健身工作台.html`",
        "安全边界",
    ):
        if required not in guide_text:
            fail(f"Beginner guide is missing required section or instruction: {required}")

    for path in (readme, guide):
        text = read_text(path)
        for target in LINK_RE.findall(text):
            target = target.strip().strip("<>").split("#", 1)[0]
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            resolved = (path.parent / target).resolve()
            if not resolved.exists():
                fail(f"Broken local link in {path.relative_to(ROOT)}: {target}")


def run(command: list[str], cwd: Path | None = None) -> str:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUTF8"] = "1"
    completed = subprocess.run(
        command,
        cwd=str(cwd or ROOT),
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    if completed.returncode != 0:
        fail(
            "Command failed:\n"
            + " ".join(command)
            + "\nSTDOUT:\n"
            + completed.stdout
            + "\nSTDERR:\n"
            + completed.stderr
        )
    return completed.stdout.strip()


def validate_renderers(temp: Path) -> None:
    expert_library = SKILLS_ROOT / "lzheng-training-expert-library"
    run([sys.executable, str(expert_library / "scripts" / "validate_expert_library.py")])

    fitness = SKILLS_ROOT / "lzheng-fitness-plan"
    plan_json = fitness / "references" / "plan-contract.example.json"
    output_html = temp / "lzheng-fitness-plan-example.html"
    run([sys.executable, str(fitness / "scripts" / "validate_plan.py"), str(plan_json)])
    run([sys.executable, str(fitness / "scripts" / "render_fitness_plan.py"), str(plan_json), str(output_html)])
    run(
        [
            sys.executable,
            str(fitness / "scripts" / "audit_html_plan.py"),
            str(output_html),
            "--plan",
            str(plan_json),
        ]
    )

    cycle = SKILLS_ROOT / "lzheng-strength-cycle-planner"
    cycle_json = ROOT / "examples" / "lzheng-strength-cycle-example.json"
    cycle_html = temp / "lzheng-strength-cycle-example.html"
    run([sys.executable, str(cycle / "scripts" / "render_strength_cycle_html.py"), str(cycle_json), str(cycle_html)])

    ui_validator = SKILLS_ROOT / "lzheng-training-system" / "scripts" / "validate_ui_contract.py"
    run([sys.executable, str(ui_validator), str(output_html), "--kind", "plan"])
    run([sys.executable, str(ui_validator), str(cycle_html), "--kind", "cycle"])

    for html in (output_html, cycle_html):
        text = read_text(html)
        if "<html" not in text.lower() or "data:image/" not in text:
            fail(f"Rendered HTML is incomplete or image is not embedded: {html}")
        if "html,body{max-width:100%;overflow-x:hidden}" not in text:
            fail(f"Rendered HTML is missing the mobile overflow guard: {html}")
        if re.search(r"(?:src|href)=[\"']https?://", text, re.IGNORECASE):
            fail(f"Rendered HTML has an external runtime dependency: {html}")

    workbench = SKILLS_ROOT / "lzheng-fitness-workbench-builder"
    run([sys.executable, str(workbench / "scripts" / "Validate-FitnessWorkbenchSkill.py"), "--skill", str(workbench)])

    system = SKILLS_ROOT / "lzheng-training-system"
    run([sys.executable, str(system / "scripts" / "Test-LzhengTrainingSystemPortability.py")])
    portable_root = temp / "portable-training-system"
    run([sys.executable, str(system / "scripts" / "lzheng_training_system.py"), "bootstrap", "--target", str(portable_root)])
    run([sys.executable, str(system / "scripts" / "lzheng_training_system.py"), "doctor", "--root", str(portable_root)])

    adapted_plan = temp / "个人训练计划-v01.json"
    run([
        sys.executable,
        str(workbench / "scripts" / "Adapt-PlanContract.py"),
        str(plan_json),
        str(adapted_plan),
        "--start-date",
        "2026-08-17",
    ])
    universal_root = temp / "universal-plan-system"
    run([
        sys.executable,
        str(workbench / "scripts" / "Initialize-FitnessWorkbench.py"),
        "--target",
        str(universal_root),
        "--brand",
        "TRAIN",
        "--athlete",
        "使用者",
        "--start-date",
        "2026-08-17",
        "--plan",
        str(plan_json),
    ])
    run([sys.executable, str(workbench / "scripts" / "Check-FitnessWorkbench.py"), "--project", str(universal_root)])
    release_root = temp / "universal-plan-release"
    run([
        sys.executable,
        str(workbench / "scripts" / "Prepare-FitnessWorkbenchRelease.py"),
        "--project",
        str(universal_root),
        "--deploy",
        str(release_root),
    ])
    run([
        sys.executable,
        str(workbench / "scripts" / "Check-FitnessWorkbench.py"),
        "--project",
        str(universal_root),
        "--deploy",
        str(release_root),
    ])


def tree_hash(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        if "__pycache__" in path.parts or path.suffix.lower() == ".pyc":
            continue
        rel = path.relative_to(root).as_posix()
        result[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def validate_install(temp: Path) -> None:
    target = temp / "test-agent"
    install_output = run([sys.executable, str(ROOT / "tools" / "install.py"), "--target-root", str(target), "--all"])
    for required in ("LZHENG_FITNESS_AI_ONBOARDING:", "开始建立我的健身系统", "不要让用户先看 README"):
        if required not in install_output:
            fail(f"Installer is missing required AI onboarding text: {required}")
    for name in EXPECTED:
        source = SKILLS_ROOT / name
        installed = target / "skills" / name
        if not installed.is_dir():
            fail(f"Installer did not create: {installed}")
        if tree_hash(source) != tree_hash(installed):
            fail(f"Installed files differ from source: {name}")
        validate_skill(installed)


def main() -> None:
    validate_beginner_guide()
    validate_repository_hygiene()
    manifest = json.loads(read_text(ROOT / "lzheng-fitness.manifest.json"))
    manifest_names = tuple(item["name"] for item in manifest.get("skills", []))
    if manifest_names != EXPECTED:
        fail(f"Manifest Skill list mismatch: {manifest_names}")

    actual = tuple(sorted(path.name for path in SKILLS_ROOT.iterdir() if path.is_dir()))
    if tuple(sorted(EXPECTED)) != actual:
        fail(f"Unexpected Skill directory set: {actual}")

    for name in EXPECTED:
        validate_skill(SKILLS_ROOT / name)

    with tempfile.TemporaryDirectory(prefix="lzheng-fitness-validation-") as raw:
        temp = Path(raw)
        validate_renderers(temp)
        validate_install(temp)

    print("OK: Lzheng Fitness bundle is portable, renderable, and installable.")
    print(f"Validated Skills: {len(EXPECTED)}")


if __name__ == "__main__":
    try:
        main()
    except ValidationFailure as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
