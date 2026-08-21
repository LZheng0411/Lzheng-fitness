#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify that a generated workbench still opens its plan after the whole folder moves."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlparse


HERE = Path(__file__).resolve().parent
DATA_BLOCK = re.compile(r'<script id="workbench-data" type="application/json">([\s\S]*?)</script>')


def fail(message: str) -> None:
    raise SystemExit("FITNESS_WORKBENCH_PORTABILITY: FAIL\n- " + message)


def run(command: list[str]) -> str:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    completed = subprocess.run(
        command,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    if completed.returncode:
        fail("命令失败：" + " ".join(command) + "\n" + (completed.stdout + completed.stderr).strip())
    return completed.stdout


def run_expect_failure(command: list[str]) -> str:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    completed = subprocess.run(
        command,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    if completed.returncode == 0:
        fail("本应失败的缺失资源检查却通过：" + " ".join(command))
    return completed.stdout + completed.stderr


def load_data(project: Path) -> dict:
    html = (project / "健身工作台.html").read_text(encoding="utf-8")
    blocks = DATA_BLOCK.findall(html)
    if len(blocks) != 1:
        fail("工作台数据块数量异常")
    return json.loads(blocks[0])


def resolve_plan(project: Path, data: dict) -> Path:
    meta = data.get("meta", {})
    href = str(meta.get("plan_href") or "")
    parsed = urlparse(href)
    if parsed.scheme or parsed.netloc or not parsed.path:
        fail("完整计划不是相对浏览器链接：" + href)
    if href.lower().startswith(("obsidian:", "file:")):
        fail("完整计划仍依赖 Obsidian 或固定 file URI")
    target = (project / unquote(parsed.path)).resolve()
    try:
        target.relative_to(project.resolve())
    except ValueError:
        fail("完整计划链接越出健身系统目录")
    if not target.is_file() or target.suffix.lower() != ".html":
        fail("完整计划 HTML 不存在：" + str(target))
    if meta.get("plan_file", "").replace("\\", "/") != unquote(parsed.path).replace("\\", "/"):
        fail("plan_file 与 plan_href 不一致")
    return target


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="lzheng-portable-") as raw:
        temp = Path(raw)
        source = temp / "原始 健身系统"
        moved = temp / "移动后 知识库"
        run([sys.executable, str(HERE / "Initialize-FitnessWorkbench.py"), "--target", str(source)])

        before = load_data(source)
        before_href = before.get("meta", {}).get("plan_href")
        resolve_plan(source, before)
        for relative in (
            "训练与周期/当前周期",
            "训练与周期/力量周期",
            "训练复盘与状态/训练复盘",
            "训练复盘与状态/状态档案",
        ):
            if not (source / relative).is_dir():
                fail("正式产物目录缺失：" + relative)

        shutil.move(str(source), str(moved))
        after = load_data(moved)
        if after.get("meta", {}).get("plan_href") != before_href:
            fail("移动目录后相对计划链接发生变化")
        resolve_plan(moved, after)

        check_output = run([sys.executable, str(HERE / "Check-FitnessWorkbench.py"), "--project", str(moved)])
        if "FITNESS_WORKBENCH_CHECK: PASS" not in check_output:
            fail("移动目录后的工作台检查未通过")

        release = temp / "发布副本（无 Obsidian）"
        run([
            sys.executable,
            str(HERE / "Prepare-FitnessWorkbenchRelease.py"),
            "--project",
            str(moved),
            "--deploy",
            str(release),
        ])
        release_check = run([
            sys.executable,
            str(HERE / "Check-FitnessWorkbench.py"),
            "--project",
            str(moved),
            "--deploy",
            str(release),
        ])
        if "FITNESS_WORKBENCH_CHECK: PASS" not in release_check:
            fail("无 Obsidian 发布副本检查未通过")
        release_data = json.loads(DATA_BLOCK.findall((release / "index.html").read_text(encoding="utf-8"))[0])
        for key in ("review_index", "status_index"):
            if not release_data.get("documents", {}).get(key, {}).get("content_markdown"):
                fail("发布副本无法直接阅读文档：" + key)

        video = release / "工作台与工具/健身工作台开发/界面素材/workbench-background.mp4"
        if not video.is_file():
            fail("发布副本没有复制动态背景")
        missing = video.with_suffix(".mp4.missing")
        video.rename(missing)
        failure = run_expect_failure([
            sys.executable,
            str(HERE / "Check-FitnessWorkbench.py"),
            "--project",
            str(moved),
            "--deploy",
            str(release),
        ])
        if "workbench-background.mp4" not in failure:
            fail("验收没有明确报告缺失的视频资源")

    print("FITNESS_WORKBENCH_PORTABILITY: PASS")


if __name__ == "__main__":
    main()
