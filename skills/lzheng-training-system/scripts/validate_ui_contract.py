#!/usr/bin/env python3
"""Validate fixed standalone HTML templates and responsibility boundaries."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("html", type=Path)
    parser.add_argument("--kind", choices=("plan", "cycle", "workbench"))
    args = parser.parse_args()
    if not args.html.is_file():
        print("UI_CONTRACT: FAIL\n- HTML 不存在")
        return 1
    text = args.html.read_text(encoding="utf-8")
    errors = []
    required = {
        "viewport": r'<meta\s+name=["\']viewport',
        "responsive layout": r'@media\s*\([^)]*max-width\s*:',
        "max width": r'max-width\s*:',
        "offline style": r'<style>',
    }
    forbidden = {"CDN/remote script": r'<script[^>]+src=["\']https?://', "remote stylesheet": r'<link[^>]+href=["\']https?://', "CSS import": r'@import\s+(?:url\()?\s*["\']?https?://'}
    for label, pattern in required.items():
        if not re.search(pattern, text, re.I): errors.append("缺少 " + label)
    for label, pattern in forbidden.items():
        if re.search(pattern, text, re.I): errors.append("包含 " + label)
    kind = args.kind
    if kind is None:
        for candidate, marker in (
            ("plan", "lzheng-fitness-plan-v4"),
            ("cycle", "lzheng-strength-cycle-v1"),
            ("workbench", "lzheng-fitness-workbench-v3"),
        ):
            if marker in text:
                kind = candidate
                break
    contracts = {
        "plan": {
            "marker": "lzheng-fitness-plan-v4",
            "sections": ("overview", "week", "training", "progression", "coverage"),
            "nav": ("概览", "本周", "训练日", "进阶", "覆盖"),
            "required_text": ("训练日安排", "进阶与周期复盘", "AI 主动向用户确认", "生成下一阶段计划", "动作模式", "健美肌群", "直接组", "间接折算", "全部来源"),
            "forbidden": (
                r">\s*下一次训练\s*<",
                r">\s*(?:标记完成|完成训练|开始训练)\s*<",
                r">\s*安全状态\s*<",
                r">\s*本阶段追踪项\s*<",
                r">\s*执行规则\s*<",
                r">\s*动作分层与当前职责\s*<",
                r">\s*假设/待确认\s*<",
                r">\s*停止普通推进的信号\s*<",
            ),
        },
        "cycle": {
            "marker": "lzheng-strength-cycle-v1",
            "sections": ("overview", "schedule", "sessions", "cycles", "rules"),
            "nav": ("概览", "周结构", "训练日", "周期", "规则"),
            "forbidden": (r">\s*下一次训练\s*<", r">\s*(?:标记完成|完成训练|开始训练)\s*<"),
            "required_text": (),
        },
        "workbench": {
            "marker": "lzheng-fitness-workbench-v3",
            "sections": ("m-today", "m-week", "m-trend", "m-record", "m-settings"),
            "nav": ("训练", "计划", "负荷", "复盘", "指南"),
            "forbidden": (),
            "required_text": (),
        },
    }
    if kind:
        contract = contracts[kind]
        if f'data-ui-template="{contract["marker"]}"' not in text:
            errors.append("固定模板版本不匹配: " + contract["marker"])
        for section_id in contract["sections"]:
            if not re.search(rf'id=["\']{re.escape(section_id)}["\']', text):
                errors.append("缺少固定区块: " + section_id)
        for label in contract["nav"]:
            if label not in text:
                errors.append("缺少固定导航文案: " + label)
        for label in contract["required_text"]:
            if label not in text:
                errors.append("缺少固定页面文案: " + label)
        for pattern in contract["forbidden"]:
            if re.search(pattern, text):
                errors.append("包含工作台专属操作")
        if kind == "workbench":
            nav_tags = re.findall(r"<nav\b[^>]*>", text, re.I)
            nav_containers = [
                tag for tag in nav_tags
                if re.search(r'\bid=["\']navBar["\']', tag, re.I)
                and re.search(r'\bclass=["\'][^"\']*\bnav\b[^"\']*["\']', tag, re.I)
            ]
            if len(nav_containers) != 1:
                errors.append("固定导航容器 navBar 缺失或重复")
            import sys
            sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lzheng-fitness-workbench-builder/scripts"))
            from workbench_ui import shell_problems
            errors.extend(shell_problems(text))
        if kind == "plan" and re.search(r"--green\b|#174f3d|#e7f0ec|#bdd1c6", text, re.I):
            errors.append("计划页包含旧绿色视觉令牌")
    else:
        errors.append("无法识别固定模板类型")
    if kind != "workbench" and re.search(r"__[A-Z0-9_]+__", text):
        errors.append("仍有未替换模板占位符")
    if kind == "workbench" and "__FWB_BRAND__" in text:
        errors.append("工作台品牌占位符未替换")
    if errors:
        print("UI_CONTRACT: FAIL")
        for error in errors: print("- " + error)
        return 1
    print("UI_CONTRACT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
