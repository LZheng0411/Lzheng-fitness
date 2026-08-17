#!/usr/bin/env python3
"""Audit rendered Lzheng fitness-plan HTML for portability and consistency."""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

from validate_plan import load_plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("html", type=Path)
    parser.add_argument("--plan", type=Path)
    args = parser.parse_args()
    if not args.html.is_file():
        print(f"ERROR: HTML not found: {args.html}")
        return 1
    text = args.html.read_text(encoding="utf-8")
    errors: list[str] = []
    checks = {
        "UTF-8 charset": r'<meta\s+charset="utf-8"',
        "viewport": r'<meta\s+name="viewport"',
        "plan id": r'data-plan-id="[^"]+"',
        "snapshot id": r'data-snapshot-id="[^"]+"',
        "fixed template": r'data-ui-template="lzheng-fitness-plan-v4"',
        "overview": r'id="overview"[^>]+data-template-section="overview"',
        "weekly structure": r'id="week"[^>]+data-template-section="week"',
        "training section": r'id="training"',
        "progression section": r'id="progression"',
        "coverage section": r'id="coverage"',
        "training day cards": r'class="training-grid"',
        "weekly training focus": r'class="schedule-focus"',
        "AI-led cycle review": r'>进阶与周期复盘<',
        "AI review confirmation": r'AI 主动向用户确认',
        "next phase generation": r'生成下一阶段计划',
        "pattern coverage": r'>动作模式<',
        "bodybuilding coverage": r'>健美肌群<',
        "coverage sources": r'>全部来源<',
        "print styles": r'@media\s+print',
        "fixed primary navigation": r'\.sticky\{position:fixed;',
    }
    for label, pattern in checks.items():
        if not re.search(pattern, text, flags=re.I):
            errors.append(f"missing {label}")
    forbidden = {
        "external stylesheet": r'<link[^>]+rel=["\']stylesheet',
        "external script": r'<script[^>]+src=',
        "remote image": r'<img[^>]+src=["\']https?://',
        "iframe": r'<iframe\b',
        "CSS import": r'@import\b',
        "placeholder": r'\bTODO\b|\[TODO',
        "unresolved template token": r'__[A-Z0-9_]+__',
        "workbench-only next workout": r'>\s*下一次训练\s*<',
        "workbench-only completion action": r'>\s*(?:标记完成|完成训练|开始训练)\s*<',
        "internal safety status": r'>\s*安全状态\s*<',
        "internal tracking cards": r'>\s*本阶段追踪项\s*<',
        "internal execution rules": r'>\s*执行规则\s*<',
        "internal assumptions": r'>\s*假设/待确认\s*<',
        "legacy green token": r'--green\b|#174f3d|#e7f0ec|#bdd1c6',
        "zero coverage row": r'class="[^"]*coverage-zero[^"]*"',
    }
    for label, pattern in forbidden.items():
        if re.search(pattern, text, flags=re.I):
            errors.append(f"contains forbidden {label}")

    nav = re.search(r'<nav class="sticky"[^>]*>([\s\S]*?)</nav>', text)
    if not nav:
        errors.append("missing primary navigation")
    elif len(re.findall(r'<a\s+href=', nav.group(1))) != 5:
        errors.append("primary navigation must contain exactly five execution entries")

    if args.plan:
        try:
            plan = load_plan(args.plan)
        except ValueError as exc:
            errors.append(str(exc))
        else:
            expected = [
                plan.get("plan_meta", {}).get("plan_id"),
                plan.get("profile_snapshot", {}).get("snapshot_id"),
            ]
            expected.extend(item.get("name") for day in plan.get("training_days", []) for item in day.get("exercises", []))
            for value in filter(None, expected):
                if html.escape(str(value), quote=True) not in text:
                    errors.append(f"rendered HTML does not contain plan value: {value}")
            schedule_focus_count = text.count('class="schedule-focus"')
            if schedule_focus_count != len(plan.get("weekly_schedule", [])):
                errors.append("each weekly schedule card must include one training-focus summary")

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("OK: HTML is standalone and consistent with the plan")
    return 0


if __name__ == "__main__":
    sys.exit(main())
