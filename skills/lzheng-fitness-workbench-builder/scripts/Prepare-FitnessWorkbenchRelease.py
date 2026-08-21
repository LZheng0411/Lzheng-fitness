#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Create a shareable workbench copy without machine-local paths or deep links."""

import argparse
import json
import os
import re
import shutil
from pathlib import Path


DATA_BLOCK = re.compile(r'(<script id="workbench-data" type="application/json">)([\s\S]*?)(</script>)')
WINDOWS_PATH = re.compile(r"^[A-Za-z]:[\\/]")
WINDOWS_PATH_IN_TEXT = re.compile(r'''(?m)(?:^|["'`\s(])([A-Za-z]:[\\/])''')


def fail(message):
    raise SystemExit("FITNESS_WORKBENCH_RELEASE: FAIL\n- " + message)


def scrub(value):
    if isinstance(value, dict):
        cleaned = {}
        for key, child in value.items():
            if key.endswith("_path"):
                continue
            if key.endswith("_href") and isinstance(child, str) and child.lower().startswith("obsidian://"):
                continue
            cleaned[key] = scrub(child)
        return cleaned
    if isinstance(value, list):
        return [scrub(item) for item in value]
    if isinstance(value, str):
        if value.lower().startswith("obsidian://") or WINDOWS_PATH.match(value):
            return "本地来源已在分享版隐藏"
    return value


def sanitize_html(source):
    match = DATA_BLOCK.search(source)
    if not match:
        fail("正式工作台缺少唯一 workbench-data 数据块")
    if len(DATA_BLOCK.findall(source)) != 1:
        fail("正式工作台 workbench-data 数量不是 1")
    try:
        data = json.loads(match.group(2))
    except json.JSONDecodeError as exc:
        fail("workbench-data 不是合法 JSON: %s" % exc)
    cleaned = scrub(data)
    payload = json.dumps(cleaned, ensure_ascii=False)
    output = source[:match.start()] + match.group(1) + payload + match.group(3) + source[match.end():]
    if WINDOWS_PATH_IN_TEXT.search(output) or re.search(r"obsidian://open\?path=", payload, re.I):
        fail("分享版仍包含本机路径或 Obsidian 深链")
    if re.search(r"__[A-Z0-9_]+__", output):
        fail("分享版仍包含未替换占位符")
    return output


def project_file(root, relative):
    value = str(relative or "").replace("/", os.sep)
    if not value or os.path.isabs(value):
        return None
    target = (root / value).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return None
    return target


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--deploy", required=True)
    args = parser.parse_args()

    project = Path(args.project).resolve()
    deploy = Path(args.deploy).resolve()
    source_path = project / "健身工作台.html"
    if not source_path.is_file():
        fail("正式工作台不存在: " + str(source_path))
    deploy.mkdir(parents=True, exist_ok=True)
    output_path = deploy / "index.html"
    sanitized = sanitize_html(source_path.read_text(encoding="utf-8"))
    temporary = output_path.with_suffix(".html.tmp")
    temporary.write_text(sanitized, encoding="utf-8")
    os.replace(temporary, output_path)

    match = DATA_BLOCK.search(sanitized)
    cleaned_data = json.loads(match.group(2))
    plan_relative = cleaned_data.get("meta", {}).get("plan_file")
    source_plan = project_file(project, plan_relative)
    target_plan = project_file(deploy, plan_relative)
    if not source_plan or not source_plan.is_file() or not target_plan:
        fail("完整计划 HTML 不存在或路径不可迁移")
    target_plan.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_plan, target_plan)

    relative_assets = Path("工作台与工具") / "健身工作台开发" / "界面素材"
    source_assets = project / relative_assets
    target_assets = deploy / relative_assets
    if not source_assets.is_dir():
        fail("工作台素材目录不存在: " + str(source_assets))
    target_assets.mkdir(parents=True, exist_ok=True)
    for source in source_assets.iterdir():
        if source.is_file():
            shutil.copy2(source, target_assets / source.name)
    print("FITNESS_WORKBENCH_RELEASE: PASS")
    print("index: " + str(output_path))


if __name__ == "__main__":
    main()
