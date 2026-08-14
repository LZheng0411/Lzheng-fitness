#!/usr/bin/env python3
"""Static UI Contract v1 validator for standalone training HTML."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("html", type=Path)
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
    if errors:
        print("UI_CONTRACT: FAIL")
        for error in errors: print("- " + error)
        return 1
    print("UI_CONTRACT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
