#!/usr/bin/env python3
"""Embed the standard line-art header image into a standalone HTML plan."""

from __future__ import annotations

import argparse
import base64
import mimetypes
import re
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Inline a local header image as a CSS data URL.")
    parser.add_argument("html", type=Path, help="UTF-8 HTML plan to update")
    parser.add_argument("--asset", required=True, type=Path, help="Header image to embed")
    parser.add_argument("--reference", default="header-lineart.png", help="Relative image name used in url(...)")
    args = parser.parse_args()

    html = args.html.read_text(encoding="utf-8")
    mime = mimetypes.guess_type(args.asset.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(args.asset.read_bytes()).decode("ascii")
    data_url = f"data:{mime};base64,{encoded}"
    pattern = re.compile(r"url\((['\"]?)" + re.escape(args.reference) + r"\1\)")
    updated, count = pattern.subn(f'url("{data_url}")', html)
    if count != 1:
        raise SystemExit(f"Expected one url({args.reference}) reference, found {count}.")
    args.html.write_text(updated, encoding="utf-8")
    print(f"Embedded {args.asset.name} into {args.html.name}.")


if __name__ == "__main__":
    main()
