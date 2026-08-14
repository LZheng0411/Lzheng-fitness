#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Create a portable, data-free workbench template from a finished HTML page."""

import argparse
import json
import re
from pathlib import Path


DATA_RE = re.compile(
    r'<script id="workbench-data" type="application/json">[\s\S]*?</script>'
)


def fail(message):
    raise SystemExit("FITNESS_WORKBENCH_TEMPLATE: FAIL\n- " + message)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    source = Path(args.source).resolve()
    output = Path(args.out).resolve()
    if not source.is_file():
        fail("源 HTML 不存在: " + str(source))

    html = source.read_text(encoding="utf-8")
    if len(DATA_RE.findall(html)) != 1:
        fail("源 HTML 必须且只能包含一个 workbench-data 数据块")

    html = DATA_RE.sub(
        '<script id="workbench-data" type="application/json">{}</script>',
        html,
        count=1,
    )
    replacements = {
        'content:"LZ / ";': 'content:"__FWB_BRAND__ / ";',
        'content:"LZ\\A TRAINING";': 'content:"__FWB_BRAND__\\A TRAINING";',
        'content:"LZ / TRAINING";': 'content:"__FWB_BRAND__ / TRAINING";',
    }
    for original, portable in replacements.items():
        html = html.replace(original, portable)

    if "__FWB_BRAND__" not in html:
        fail("没有生成品牌占位符，请检查源页面品牌写法")
    absolute_path = r'(?m)(?:^|["\'`\s])([A-Za-z]:\\(?:[^\\/:*?"<>|\r\n]+\\)+)'
    if re.search(absolute_path, html):
        fail("模板仍包含 Windows 绝对路径")
    if re.search(r"obsidian://open\?path=[A-Za-z](?:%3A|:)", html, re.I):
        fail("模板仍包含指向固定磁盘的个人 Obsidian 深链")

    blocks = re.findall(
        r'<script id="workbench-data" type="application/json">([\s\S]*?)</script>',
        html,
    )
    try:
        if json.loads(blocks[0]) != {}:
            fail("模板数据块未清空")
    except json.JSONDecodeError as exc:
        fail("模板数据块不是合法 JSON: " + str(exc))

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    print("FITNESS_WORKBENCH_TEMPLATE: PASS")
    print("template: " + str(output))


if __name__ == "__main__":
    main()
