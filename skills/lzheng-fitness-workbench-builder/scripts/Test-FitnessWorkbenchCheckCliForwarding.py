#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify Check forwards explicit Notion merge semantics to both builder passes."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
DATA_BLOCK = re.compile(r'<script id="workbench-data" type="application/json">([\s\S]*?)</script>')


def fail(message: str) -> None:
    raise SystemExit("FITNESS_WORKBENCH_CHECK_CLI_FORWARDING: FAIL\n- " + message)


def execute(command: list[str]) -> str:
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


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="lzheng-check-forwarding-") as raw:
        project = Path(raw) / "训练系统"
        execute(
            [
                sys.executable,
                str(HERE / "Initialize-FitnessWorkbench.py"),
                "--target",
                str(project),
                "--demo-data",
            ]
        )
        notion = project / "工作台与工具/健身工作台开发/notion-data.json"
        build_command = [
            sys.executable,
            str(HERE / "Build-FitnessWorkbenchData.py"),
            "--project",
            str(project),
            "--notion",
            str(notion),
            "--notion-mode",
            "full",
            "--replace-main-lift-history",
            "--apply",
        ]
        execute(build_command)
        blocks = DATA_BLOCK.findall((project / "健身工作台.html").read_text(encoding="utf-8"))
        if len(blocks) != 1:
            fail("应用 full 输入后的工作台数据块异常")
        data = json.loads(blocks[0])
        if data.get("sync", {}).get("merge_mode") != "full":
            fail("准备夹具没有进入 full 合并模式")

        output = execute(
            [
                sys.executable,
                str(HERE / "Check-FitnessWorkbench.py"),
                "--project",
                str(project),
                "--notion",
                str(notion),
                "--notion-mode",
                "full",
                "--replace-main-lift-history",
            ]
        )
        if "FITNESS_WORKBENCH_CHECK: PASS" not in output:
            fail("Check 没有按 full + 权威替换语义完成两次构建校验")

    print("FITNESS_WORKBENCH_CHECK_CLI_FORWARDING: PASS")


if __name__ == "__main__":
    main()
