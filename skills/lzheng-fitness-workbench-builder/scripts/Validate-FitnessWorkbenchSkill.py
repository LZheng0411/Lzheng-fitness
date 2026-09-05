#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate package completeness, portability and bundled images."""

import argparse
import json
import re
import struct
import subprocess
import sys
from pathlib import Path


REQUIRED = [
    "SKILL.md",
    "agents/openai.yaml",
    "scripts/Initialize-FitnessWorkbench.py",
    "scripts/Build-FitnessWorkbenchData.py",
    "scripts/Check-FitnessWorkbench.py",
    "scripts/Inspect-FitnessWorkbench.py",
    "scripts/workbench_ui.py",
    "scripts/Upgrade-FitnessWorkbenchUi.py",
    "scripts/Check-FitnessWorkbenchBrowser.cjs",
    "assets/ui-history.json",
    "scripts/Prepare-FitnessWorkbenchRelease.py",
    "scripts/Replace-FitnessWorkbenchBackground.py",
    "scripts/Refresh-FitnessWorkbench.py",
    "scripts/Refresh-FitnessWorkbenchTemplate.py",
    "scripts/Validate-FitnessWorkbenchSkill.py",
    "scripts/Test-FitnessWorkbenchWeekTransition.py",
    "scripts/Test-FitnessWorkbenchPortability.py",
    "scripts/Test-FitnessWorkbenchBackgroundReplacement.py",
    "scripts/Test-FitnessWorkbenchNotionSync.py",
    "scripts/Test-FitnessWorkbenchReleaseSafety.py",
    "scripts/Test-FitnessWorkbenchCheckCliForwarding.py",
    "scripts/Test-FitnessWorkbenchRefresh.py",
    "scripts/Test-FitnessWorkbenchReviewProjection.py",
    "scripts/Test-FitnessWorkbenchDataOnlyRefresh.py",
    "scripts/Deploy-FitnessWorkbenchCloudBase.py",
    "scripts/Verify-FitnessWorkbenchCloudBase.py",
    "scripts/Publish-FitnessWorkbenchCloudBase.py",
    "scripts/Test-FitnessWorkbenchCloudBaseRelease.py",
    "scripts/Prepare-FitnessWorkbenchEncryptedRelease.py",
    "scripts/Deploy-FitnessWorkbenchCloudBaseEncrypted.py",
    "scripts/Verify-FitnessWorkbenchCloudBaseEncrypted.py",
    "scripts/Publish-FitnessWorkbenchCloudBasePrivate.py",
    "scripts/Test-FitnessWorkbenchEncryptedRelease.py",
    "scripts/Test-FitnessWorkbenchCloudBasePrivatePublish.py",
    "scripts/Prepare-FitnessWorkbenchPublicPersonalRelease.py",
    "scripts/Deploy-FitnessWorkbenchCloudBasePublicPersonal.py",
    "scripts/Verify-FitnessWorkbenchCloudBasePublicPersonal.py",
    "scripts/Publish-FitnessWorkbenchCloudBasePublicPersonal.py",
    "scripts/Test-FitnessWorkbenchPublicPersonalRelease.py",
    "scripts/Migrate-FitnessWorkbenchSchema.py",
    "../lzheng-training-system/scripts/Process-LzhengHandoffs.py",
    "references/input-contract.md",
    "references/visual-contract.md",
    "references/migration-and-release.md",
    "references/background-replacement.md",
    "references/cloudbase-publishing.md",
    "references/path-portability-repair.md",
    "assets/workbench-template.html",
    "assets/backgrounds/workbench-background.mp4",
    "assets/backgrounds/workbench-background.png",
    "assets/backgrounds/garou-cosmic-crouch.png",
    "assets/backgrounds/garou-landscape.png",
    "assets/backgrounds/garou-portrait.png",
    "assets/examples/plan-template-v01.json",
    "assets/examples/notion-data.example.json",
]
def png_size(path):
    with path.open("rb") as handle:
        header = handle.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("不是有效 PNG")
    return struct.unpack(">II", header[16:24])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skill", required=True)
    args = parser.parse_args()
    root = Path(args.skill).resolve()
    problems = []

    for relative in REQUIRED:
        if not (root / relative).is_file():
            problems.append("缺少文件: " + relative)

    template_path = root / "assets/workbench-template.html"
    if template_path.is_file():
        html = template_path.read_text(encoding="utf-8")
        blocks = re.findall(r'<script id="workbench-data" type="application/json">([\s\S]*?)</script>', html)
        if len(blocks) != 1:
            problems.append("模板 workbench-data 数量不是 1")
        else:
            try:
                if json.loads(blocks[0]) != {}:
                    problems.append("模板仍包含非空个人数据块")
            except json.JSONDecodeError:
                problems.append("模板数据块不是合法 JSON")
        if "__FWB_BRAND__" not in html:
            problems.append("模板缺少品牌占位符")
        if 'data-ui-template="lzheng-fitness-workbench-v3"' not in html:
            problems.append("模板缺少固定 UI 模板版本")
        from workbench_ui import shell_problems, identity
        if shell_problems(html) or not identity(html)['declared_hash_matches']:
            problems.append("模板缺少固定侧栏/底栏导航结构")
        if "workbench-background.png" not in html or "workbench-background.mp4" not in html:
            problems.append("模板没有引用正式动态背景及静态兜底")
        if "onboarding" not in html or "trainingStatus" not in html:
            problems.append("模板未实现 schema 6 建档或状态显示")
        if re.search(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b", html):
            problems.append("模板包含 JWT 或 publishable key")
        if re.search(r"(?:tcb-api|tcloudbase)\.[A-Za-z0-9.-]+", html, re.I):
            problems.append("模板包含真实 CloudBase 域名")
        if re.search(r"accessKey\s*:\s*['\"](?!['\"])[^'\"]+", html):
            problems.append("模板包含非空硬编码 accessKey")
        if "enabled:integrationConfig.enabled===true" not in html:
            problems.append("模板没有显式关闭的可选云端配置契约")
        if "mergeNutritionContract(D.nutrition_contract)" not in html:
            problems.append("模板没有读取匿名 nutrition_contract")
        if re.search(r"profile:\{sex:'male',age:\d+,height_cm:\d+", html):
            problems.append("模板包含个人营养默认资料")
        if "饮食工作台/营养方案-v" in html:
            problems.append("模板包含个人营养方案路径")
        for marker in ("trainingArchiveOverlay", "nutritionAdjustPanel", "nutritionFeelingForm", "增加一组"):
            if marker not in html:
                problems.append("模板缺少最新版交互: " + marker)
        if "doc-overlay" not in html or "openDocument" not in html:
            problems.append("模板未实现不依赖 Obsidian 的内置文档阅读")
        if 'data-background-mode="video"' not in html or "FITNESS_WORKBENCH_BACKGROUND_CONFIG_START" not in html:
            problems.append("模板未声明可管理的背景模式和配置块")

    skill_path = root / "SKILL.md"
    if skill_path.is_file():
        skill_text = skill_path.read_text(encoding="utf-8-sig")
        if "references/path-portability-repair.md" not in skill_text:
            problems.append("SKILL 未路由到路径可迁移修复协议")

    repair_path = root / "references/path-portability-repair.md"
    if repair_path.is_file():
        repair_text = repair_path.read_text(encoding="utf-8-sig")
        for marker in ("路径清单", "旧路径迁移", "发布副本", "回归矩阵", "强制验证"):
            if marker not in repair_text:
                problems.append("路径修复协议缺少章节: " + marker)

    background_guide = root / "references/background-replacement.md"
    if background_guide.is_file():
        guide = background_guide.read_text(encoding="utf-8-sig")
        for marker in ("纯静态背景", "动态背景", "首次初始化", "自动完成", "完成标准", "禁止做法"):
            if marker not in guide:
                problems.append("壁纸替换指南缺少章节: " + marker)

    builder_path = root / "scripts" / "Build-FitnessWorkbenchData.py"
    if builder_path.is_file():
        builder = builder_path.read_text(encoding="utf-8-sig")
        if "prev.get(\"notion\")" not in builder:
            problems.append("刷新未保留最近一次已核验的 Notion 数据")
        if "find_latest_status_artifact" not in builder:
            problems.append("构建器未读取状态档案/接回状态")
        if "build_portable_documents" not in builder or "content_markdown" not in builder:
            problems.append("构建器未嵌入可迁移文档内容")
        for marker in ("schedule_contract_snapshot", "current_week_from_schedule", "validate_week_transition_contract", "declared_training_frequency"):
            if marker not in builder:
                problems.append("构建器缺少周切换契约: " + marker)
        if '"nutrition_contract": nutrition_contract' not in builder:
            problems.append("构建器未投影 nutrition_contract")

    transition_test = root / "scripts" / "Test-FitnessWorkbenchWeekTransition.py"
    if transition_test.is_file():
        completed = subprocess.run(
            [sys.executable, str(transition_test)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if completed.returncode != 0 or "FITNESS_WORKBENCH_WEEK_TRANSITION: PASS" not in completed.stdout:
            detail = (completed.stdout + completed.stderr).strip()
            problems.append("周切换回归未通过" + (": " + detail if detail else ""))

    portability_test = root / "scripts" / "Test-FitnessWorkbenchPortability.py"
    if portability_test.is_file():
        completed = subprocess.run(
            [sys.executable, str(portability_test)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if completed.returncode != 0 or "FITNESS_WORKBENCH_PORTABILITY: PASS" not in completed.stdout:
            detail = (completed.stdout + completed.stderr).strip()
            problems.append("目录迁移回归未通过" + (": " + detail if detail else ""))

    background_test = root / "scripts" / "Test-FitnessWorkbenchBackgroundReplacement.py"
    if background_test.is_file():
        completed = subprocess.run(
            [sys.executable, str(background_test)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if completed.returncode != 0 or "FITNESS_WORKBENCH_BACKGROUND_TEST: PASS" not in completed.stdout:
            detail = (completed.stdout + completed.stderr).strip()
            problems.append("壁纸替换回归未通过" + (": " + detail if detail else ""))

    additional_regressions = (
        (
            "Test-FitnessWorkbenchNotionSync.py",
            "FITNESS_WORKBENCH_NOTION_SYNC: PASS",
            "Notion 同步回归",
        ),
        (
            "Test-FitnessWorkbenchReleaseSafety.py",
            "FITNESS_WORKBENCH_RELEASE_SAFETY: PASS",
            "发布安全回归",
        ),
        (
            "Test-FitnessWorkbenchCheckCliForwarding.py",
            "FITNESS_WORKBENCH_CHECK_CLI_FORWARDING: PASS",
            "检查器 CLI 参数转发回归",
        ),
        (
            "Test-FitnessWorkbenchRefresh.py",
            "FITNESS_WORKBENCH_REFRESH_TEST: PASS",
            "刷新编排回归",
        ),
        (
            "Test-FitnessWorkbenchReviewProjection.py",
            "FITNESS_WORKBENCH_REVIEW_PROJECTION: PASS",
            "完整复盘投影回归",
        ),
        (
            "Test-FitnessWorkbenchDataOnlyRefresh.py",
            "FITNESS_WORKBENCH_DATA_ONLY_REFRESH: PASS",
            "规划修改数据块刷新与侧边栏防回退回归",
        ),
    )
    for filename, pass_marker, label in additional_regressions:
        test_path = root / "scripts" / filename
        if not test_path.is_file():
            continue
        completed = subprocess.run(
            [sys.executable, str(test_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if completed.returncode != 0 or pass_marker not in completed.stdout:
            detail = (completed.stdout + completed.stderr).strip()
            problems.append(label + "未通过" + (": " + detail if detail else ""))

    text_suffixes = {".md", ".py", ".json", ".html", ".yaml", ".yml"}
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in text_suffixes:
            continue
        text = path.read_text(encoding="utf-8-sig")
        absolute_path = r'(?m)(?:^|["\'`\s])([A-Za-z]:\\(?:[^\\/:*?"<>|\r\n]+\\)+)'
        if re.search(absolute_path, text):
            problems.append("包含固定 Windows 绝对路径: " + str(path.relative_to(root)))
        if re.search(r"obsidian://open\?path=[A-Za-z](?:%3A|:)", text, re.I):
            problems.append("包含指向固定磁盘的个人 Obsidian 深链: " + str(path.relative_to(root)))

    for path in (root / "assets/backgrounds").glob("*.png"):
        try:
            width, height = png_size(path)
            if width < 600 or height < 600:
                problems.append("背景图分辨率过低: %s %dx%d" % (path.name, width, height))
        except ValueError as exc:
            problems.append("背景图无效: %s (%s)" % (path.name, exc))

    video_path = root / "assets/backgrounds/workbench-background.mp4"
    if video_path.is_file():
        with video_path.open("rb") as handle:
            header = handle.read(32)
        if video_path.stat().st_size < 100_000 or b"ftyp" not in header:
            problems.append("动态背景不是有效的本地 MP4")

    if problems:
        print("FITNESS_WORKBENCH_SKILL: FAIL")
        for problem in problems:
            print("- " + problem)
        raise SystemExit(1)
    print("FITNESS_WORKBENCH_SKILL: PASS")
    print("files: %d" % sum(1 for path in root.rglob("*") if path.is_file()))


if __name__ == "__main__":
    main()
