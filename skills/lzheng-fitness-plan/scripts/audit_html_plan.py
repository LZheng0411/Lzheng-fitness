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
        "quick start": r'id="start"',
        "movement stages": r'id="stages"',
        "fallback rules": r'id="fallback"',
        "knowledge sources": r'id="sources"',
        "print styles": r'@media\s+print',
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
    }
    for label, pattern in forbidden.items():
        if re.search(pattern, text, flags=re.I):
            errors.append(f"contains forbidden {label}")

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
            expected.extend(item.get("source_title") for item in plan.get("knowledge_sources", []))
            for value in filter(None, expected):
                if html.escape(str(value), quote=True) not in text:
                    errors.append(f"rendered HTML does not contain plan value: {value}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("OK: HTML is standalone and consistent with the plan")
    return 0


if __name__ == "__main__":
    sys.exit(main())
