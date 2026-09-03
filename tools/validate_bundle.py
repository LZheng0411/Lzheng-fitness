#!/usr/bin/env python3
"""Validate metadata, portability, rendering, and clean installation."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
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
    "lzheng-nutrition-system",
    "lzheng-training-system",
    "lzheng-fitness-workbench-builder",
)
TEXT_SUFFIXES = {".md", ".json", ".yaml", ".yml", ".py", ".ps1", ".js", ".sql", ".txt"}
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
    "possible JWT or publishable key": re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    "CloudBase runtime domain": re.compile(r"(?:tcb-api|tcloudbase)\.[A-Za-z0-9.-]+", re.IGNORECASE),
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
        if any(part in {".git", "validation-output", "__pycache__", "node_modules", "test-results", "playwright-report"} for part in rel.parts):
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


def validate_v3_local_first_contract() -> None:
    integration = ROOT / "integrations" / "cloudbase"
    config = integration / "examples" / "cloudbase-config.example.json"
    runner = integration / "local-agent" / "Run-NutritionLocalAgent.ps1"
    safety = integration / "local-agent" / "Test-LocalAgentSafety.ps1"
    protocol = integration / "local-agent" / "Invoke-NutritionLocalAgentProtocol.ps1"
    protocol_status = integration / "local-agent" / "Get-NutritionLocalAgentStatus.ps1"
    poller = integration / "web-agent-contract.js"
    template = SKILLS_ROOT / "lzheng-fitness-workbench-builder" / "assets" / "workbench-template.html"
    for path in (config, runner, safety, protocol, protocol_status, poller, template):
        if not path.is_file():
            fail(f"Missing v3 local-first file: {path.relative_to(ROOT)}")
    value = json.loads(read_text(config))
    if value.get("mode") != "local" or value.get("cloudbase", {}).get("enabled") is not False:
        fail("CloudBase example does not default to disabled local mode")
    if value.get("agent", {}).get("mode") != "manual-on-demand-once":
        fail("CloudBase example does not use manual-on-demand-once")
    runner_text, poller_text, template_text = read_text(runner), read_text(poller), read_text(template)
    for marker in ("$WatchHardLimitMinutes=10", "$WatchHardEmptyLimit=3", "$WatchHardFailureLimit=3"):
        if marker not in runner_text:
            fail(f"Agent safety cap missing: {marker}")
    if "Register-ScheduledTask" in read_text(integration / "local-agent" / "Install-NutritionLocalAgent.ps1"):
        fail("Public installer must not register a scheduled task")
    if "refreshKnownJob" not in poller_text or "reads: 1" not in poller_text:
        fail("Explicit one-read web refresh contract is incomplete")
    if re.search(r"set(?:Timeout|Interval)|visibilitychange|pagehide|pollKnownPendingJob", poller_text):
        fail("Web Agent contract reintroduced automatic polling")
    protocol_text = read_text(protocol)
    if "Host -ne 'run'" not in protocol_text or "-Once" not in protocol_text:
        fail("Windows protocol is not restricted to one explicit run")
    if re.search(r"Register-ScheduledTask|Start-ScheduledTask|while\s*\(", protocol_text):
        fail("Windows protocol reintroduced an automatic trigger")
    for marker in (
        "training-entry-button", "cardio-entry-button", "nutrition-entry-button",
        "confirmed_nutrition", "trainingWeightGroups", "trainingArchiveOverlay",
        "nutritionAdjustPanel", "nutritionFeelingForm", "增加一组",
        'id="fitness-local-store"', "offlineStore.saveSession", "offlineStore.saveMeal",
        "offlineStore.importBackup", "offlineStore.exportBackup", "lzheng-fitness-agent://run",
    ):
        if marker not in template_text:
            fail(f"Workbench template missing v3 local module: {marker}")
    if not re.search(r"enabled:integrationConfig\.enabled===true", template_text):
        fail("Template does not require an explicit enabled integration config")
    if "mergeNutritionContract(D.nutrition_contract)" not in template_text:
        fail("Template does not consume the anonymous nutrition contract")
    if re.search(r"profile:\{sex:'male',age:\d+,height_cm:\d+", template_text):
        fail("Template contains personal nutrition defaults")
    if "function loadCloudbaseSdk()" not in template_text or "document.head.appendChild(tag)" not in template_text:
        fail("Enabled integration cannot load its configured SDK")
    if not re.search(r"accessKey:String\(integrationConfig\.publishable_key\|\|''\)", template_text):
        fail("Template access key is not sourced from explicit config")
    if re.search(r"accessKey\s*:\s*['\"](?!['\"])[^'\"]+", template_text):
        fail("Template contains a non-empty hardcoded access key")
    migration_files = sorted((integration / "migrations").glob("*.sql"))
    migration_text = "\n".join(read_text(path) for path in migration_files)
    tables = set(re.findall(r"\.from\('([a-z_]+)'\)", template_text))
    missing = sorted(name for name in tables if not re.search(r"(?:create table|alter table) public\." + re.escape(name) + r"\b", migration_text))
    if missing:
        fail("Template database tables missing from migration: " + ", ".join(missing))
    rpcs = set(re.findall(r"\.rpc\('([a-z_]+)'", template_text))
    missing_rpcs = sorted(name for name in rpcs if not re.search(r"function public\." + re.escape(name) + r"\b", migration_text))
    if missing_rpcs:
        fail("Template RPC missing from migration: " + ", ".join(missing_rpcs))
    if "enable row level security" not in migration_text or "owner_only" not in migration_text:
        fail("Migration is missing owner-only RLS contract")
    contract = run([sys.executable, str(integration / "Test-MigrationContract.py")])
    if "CLOUDBASE_MIGRATION_CONTRACT: PASS" not in contract:
        fail("CloudBase migration contract regression did not pass")
    isolation = run([sys.executable, str(integration / "Test-InstanceIsolation.py")])
    if "INSTANCE_ISOLATION: PASS" not in isolation:
        fail("Instance-isolation regression did not pass")
    validate_windows_local_agent(integration)


def validate_windows_local_agent(integration: Path) -> None:
    """Keep Windows-only execution in Windows CI, without skipping core gates."""
    if sys.platform != "win32":
        print("SKIP: Windows local-Agent execution (covered by the Windows CI job); "
              "portable, privacy and static integration checks remain enabled.")
        return
    powershell = shutil.which("powershell")
    if not powershell:
        fail("Windows PowerShell is required for the local-Agent safety and concurrency tests")
    for script in ("Test-LocalAgentSafety.ps1", "Test-LocalAgentConcurrency.ps1"):
        output = run([powershell, "-NoProfile", "-ExecutionPolicy", "Bypass",
                      "-File", str(integration / "local-agent" / script)])
        if not re.search(r'"passed"\s*:\s*true', output):
            fail("Local Agent regression did not pass: " + script)
        print("PASS: " + script)


def validate_nutrition_system() -> None:
    skill = SKILLS_ROOT / "lzheng-nutrition-system"
    example = skill / "assets" / "examples" / "nutrition-contract.example.json"
    validator = skill / "scripts" / "validate_nutrition_contract.py"
    test = skill / "scripts" / "test_nutrition_system.py"
    for path in (example, validator, test):
        if not path.is_file():
            fail(f"Missing nutrition-system file: {path.relative_to(ROOT)}")
    if "NUTRITION_CONTRACT: PASS" not in run([sys.executable, str(validator), str(example)]):
        fail("Anonymous nutrition contract did not validate")
    if "NUTRITION_SYSTEM_TEST: PASS" not in run([sys.executable, str(test)]):
        fail("Nutrition-system regression did not pass")
    value = json.loads(read_text(example))
    if value.get("profile", {}).get("current_weight_kg") is not None:
        fail("Nutrition example must remain awaiting-profile without a weight prescription")


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


def run_expect_failure(command: list[str], required: str) -> None:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUTF8"] = "1"
    completed = subprocess.run(
        command,
        cwd=str(ROOT),
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    detail = completed.stdout + completed.stderr
    if completed.returncode == 0 or required not in detail:
        fail(
            "Command did not fail with the required marker:\n"
            + " ".join(command)
            + "\nOUTPUT:\n"
            + detail
        )


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
    run([sys.executable, str(system / "scripts" / "Test-LzhengTrainingSystemInspectReadOnly.py")])
    portable_root = temp / "portable-training-system"
    run([sys.executable, str(system / "scripts" / "lzheng_training_system.py"), "bootstrap", "--target", str(portable_root)])
    run([sys.executable, str(system / "scripts" / "lzheng_training_system.py"), "doctor", "--root", str(portable_root)])
    system_summary = run([sys.executable, str(system / "scripts" / "lzheng_training_system.py"), "inspect", "--root", str(portable_root)])
    if json.loads(system_summary).get("kind") != "lzheng_fitness_workbench_compact_summary":
        fail("Training-system inspect command did not return the compact workbench summary")

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
    workbench_html = universal_root / "健身工作台.html"
    run([sys.executable, str(ui_validator), str(workbench_html), "--kind", "workbench"])

    compact_raw = run([
        sys.executable,
        str(workbench / "scripts" / "Inspect-FitnessWorkbench.py"),
        "--project",
        str(universal_root),
    ])
    compact = json.loads(compact_raw)
    if not compact.get("shell", {}).get("ok"):
        fail("Compact workbench inspector did not prove the fixed shell")
    if len(compact_raw.encode("utf-8")) >= 8_000:
        fail("Compact workbench inspector exceeded the 8 KB agent-context budget")
    if compact.get("html_bytes", 0) < len(compact_raw.encode("utf-8")) * 10:
        fail("Compact workbench inspector did not materially reduce HTML context")
    if "<style" in compact_raw or "workbench-data" in compact_raw:
        fail("Compact workbench inspector leaked generated HTML into agent context")

    tampered_root = temp / "tampered-workbench-shell"
    shutil.copytree(universal_root, tampered_root)
    tampered_html = tampered_root / "健身工作台.html"
    tampered_text = read_text(tampered_html)
    marker = '<nav class="nav" id="navBar"></nav>'
    if tampered_text.count(marker) != 1:
        fail("Cannot build missing-navigation regression fixture")
    tampered_html.write_text(tampered_text.replace(marker, "", 1), encoding="utf-8")
    run_expect_failure(
        [sys.executable, str(ui_validator), str(tampered_html), "--kind", "workbench"],
        "固定导航容器 navBar",
    )
    run_expect_failure(
        [sys.executable, str(workbench / "scripts" / "Check-FitnessWorkbench.py"), "--project", str(tampered_root)],
        "固定导航容器 navBar",
    )
    release_root = temp / "universal-plan-release"
    run([
        sys.executable,
        str(workbench / "scripts" / "Prepare-FitnessWorkbenchRelease.py"),
        "--project",
        str(universal_root),
        "--deploy",
        str(release_root),
        "--mode",
        "public-anonymized",
    ])
    run([
        sys.executable,
        str(workbench / "scripts" / "Check-FitnessWorkbench.py"),
        "--project",
        str(universal_root),
        "--deploy",
        str(release_root),
        "--expect-release-mode",
        "public-anonymized",
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
    for required in (
        "LZHENG_FITNESS_INSTALL: PASS",
        "LZHENG_FITNESS_VERIFY: PASS",
        "LZHENG_FITNESS_AI_ONBOARDING:",
        "开始建立我的健身系统",
        "不要让用户先看 README",
    ):
        if required not in install_output:
            fail(f"Installer is missing required output: {required}")
    state = target / ".lzheng-fitness" / "install-state.json"
    if not state.is_file():
        fail("Installer did not record the post-install file manifest")
    verify_output = run(
        [sys.executable, str(ROOT / "tools" / "install.py"), "--target-root", str(target), "--all", "--verify"]
    )
    if "LZHENG_FITNESS_VERIFY: PASS" not in verify_output:
        fail("Installed bundle did not pass the standalone drift check")
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
    platform_test = run([sys.executable, str(ROOT / "tools" / "test_validation_platform.py")])
    if "VALIDATION_PLATFORM_TEST: PASS" not in platform_test:
        fail("Validation platform-routing regression did not pass")
    validate_v3_local_first_contract()
    validate_nutrition_system()
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
        template = SKILLS_ROOT / "lzheng-fitness-workbench-builder" / "assets" / "workbench-template.html"
        protected = temp / "protected-template.html"
        protected.write_bytes(template.read_bytes())
        old_source = temp / "old-source.html"
        old_source.write_text('<script id="workbench-data" type="application/json">{}</script>', encoding="utf-8")
        run_expect_failure(
            [sys.executable, str(template.parent.parent / "scripts" / "Refresh-FitnessWorkbenchTemplate.py"),
             "--source", str(old_source), "--out", str(protected)],
            "源页面缺少当前离线记录层",
        )
        if protected.read_bytes() != template.read_bytes():
            fail("Rejected template refresh modified the protected offline template")
        validate_renderers(temp)
        validate_install(temp)
        installer_test = run([sys.executable, str(ROOT / "tools" / "test_installer.py")])
        if "LZHENG_FITNESS_INSTALLER_TEST: PASS" not in installer_test:
            fail("Installer regression test did not report PASS")

    print("OK: Lzheng Fitness bundle is portable, renderable, and installable.")
    print(f"Validated Skills: {len(EXPECTED)}")


if __name__ == "__main__":
    try:
        main()
    except ValidationFailure as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
