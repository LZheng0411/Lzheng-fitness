#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""End-to-end regression for plan edits, data-only refresh, and sidebar safety."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
INITIALIZE = SCRIPT_DIR / "Initialize-FitnessWorkbench.py"
BUILDER = SCRIPT_DIR / "Build-FitnessWorkbenchData.py"
CHECKER = SCRIPT_DIR / "Check-FitnessWorkbench.py"
DATA_BLOCK = re.compile(r'(<script id="workbench-data" type="application/json">)[\s\S]*?(</script>)')
NAV_CONTAINER = '<nav class="nav" id="navBar"></nav>'


def run(command: list[str], expect_success: bool = True) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    result = subprocess.run(command, text=True, encoding="utf-8", errors="replace", capture_output=True, env=env)
    if expect_success and result.returncode != 0:
        raise AssertionError("命令失败:\n" + " ".join(command) + "\n" + result.stdout + result.stderr)
    if not expect_success and result.returncode == 0:
        raise AssertionError("预期命令失败但实际成功:\n" + " ".join(command))
    return result


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def html_parts(path: Path) -> tuple[str, str, str]:
    html = path.read_text(encoding="utf-8")
    match = DATA_BLOCK.search(html)
    require(match is not None, "正式 HTML 缺少唯一 workbench-data")
    data_match = re.search(r'<script id="workbench-data" type="application/json">([\s\S]*?)</script>', html)
    require(data_match is not None, "无法提取 workbench-data")
    json.loads(data_match.group(1))
    shell = DATA_BLOCK.sub(r"\1{}\2", html, count=1)
    return html, data_match.group(1), hashlib.sha256(shell.encode("utf-8")).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-project", help="可选：复制真实项目到隔离目录后执行同一回归")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="fitness-data-only-refresh-") as tmp:
        base = Path(tmp)
        project = base / "project"
        backup = base / "backups"
        if args.source_project:
            source = Path(args.source_project).resolve()
            require(source.is_dir(), "真实项目源目录不存在")
            shutil.copytree(source, project)
        else:
            monday = dt.date.today() - dt.timedelta(days=dt.date.today().weekday())
            run([
                sys.executable,
                str(INITIALIZE),
                "--target", str(project),
                "--brand", "TEST",
                "--athlete", "匿名测试者",
                "--start-date", monday.isoformat(),
            ])

        formal = project / "健身工作台.html"
        before_html, before_data, before_shell_hash = html_parts(formal)
        require(before_html.count(NAV_CONTAINER) == 1, "初始化页面缺少固定导航容器")

        plans = list((project / "训练与周期" / "当前周期").glob("*-v*.json"))
        require(len(plans) == 1, "隔离项目当前计划数量异常")
        plan_path = plans[0]
        plan = json.loads(plan_path.read_text(encoding="utf-8-sig"))
        old_title = plan["plan"]["title"]
        new_title = old_title + "｜数据块刷新回归"
        plan["plan"]["title"] = new_title
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        run([sys.executable, str(BUILDER), "--project", str(project), "--check-only"])
        run([sys.executable, str(BUILDER), "--project", str(project), "--apply", "--backup-dir", str(backup)])
        run([sys.executable, str(CHECKER), "--project", str(project)])

        after_html, after_data, after_shell_hash = html_parts(formal)
        require(before_data != after_data, "修改计划后 workbench-data 没有变化")
        require(before_shell_hash == after_shell_hash, "修改计划后视图壳发生变化")
        require(after_html.count(NAV_CONTAINER) == 1, "修改计划后固定导航容器丢失")
        parsed_after = json.loads(after_data)
        require(parsed_after.get("meta", {}).get("title") == new_title, "修改后的计划标题没有进入工作台数据")

        tampered = base / "tampered"
        shutil.copytree(project, tampered)
        tampered_formal = tampered / "健身工作台.html"
        tampered_html = tampered_formal.read_text(encoding="utf-8")
        require(NAV_CONTAINER in tampered_html, "无法构造导航缺失回归")
        tampered_formal.write_text(tampered_html.replace(NAV_CONTAINER, "", 1), encoding="utf-8")
        failure = run([sys.executable, str(CHECKER), "--project", str(tampered)], expect_success=False)
        require("固定导航容器" in (failure.stdout + failure.stderr), "检查器未明确报告导航缺失")

    print("FITNESS_WORKBENCH_DATA_ONLY_REFRESH: PASS")


if __name__ == "__main__":
    main()
