#!/usr/bin/env python3
"""Regression tests for safe static and video workbench background replacement."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
ASSETS = SKILL / "assets/backgrounds"
INITIALIZE = HERE / "Initialize-FitnessWorkbench.py"
REPLACE = HERE / "Replace-FitnessWorkbenchBackground.py"
CHECK = HERE / "Check-FitnessWorkbench.py"
RELEASE = HERE / "Prepare-FitnessWorkbenchRelease.py"


def fail(message: str) -> None:
    raise SystemExit("FITNESS_WORKBENCH_BACKGROUND_TEST: FAIL\n- " + message)


def execute(command: list[str], expect_success: bool = True) -> subprocess.CompletedProcess[str]:
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
    if expect_success and completed.returncode:
        fail("命令失败：" + " ".join(command) + "\n" + (completed.stdout + completed.stderr).strip())
    if not expect_success and completed.returncode == 0:
        fail("本应拒绝的命令却通过：" + " ".join(command))
    return completed


def assert_check(project: Path) -> None:
    output = execute([sys.executable, str(CHECK), "--project", str(project)]).stdout
    if "FITNESS_WORKBENCH_CHECK: PASS" not in output:
        fail("工作台检查未通过")


def main() -> None:
    help_output = execute([sys.executable, str(REPLACE), "--help"]).stdout
    if "--desktop-position" not in help_output or "60% center" not in help_output:
        fail("壁纸替换命令帮助不可用")
    initialize_help = execute([sys.executable, str(INITIALIZE), "--help"]).stdout
    if "--background-image" not in initialize_help or "--background-video" not in initialize_help:
        fail("初始化器没有公开自定义背景参数")

    with tempfile.TemporaryDirectory(prefix="lzheng-background-test-") as raw:
        temp = Path(raw)
        project = temp / "原始工作台"
        static_source = temp / "新的 静态壁纸（中文）.png"
        dynamic_source = temp / "新的动态壁纸.png"
        shutil.copy2(ASSETS / "garou-portrait.png", static_source)
        shutil.copy2(ASSETS / "garou-landscape.png", dynamic_source)

        execute([sys.executable, str(INITIALIZE), "--target", str(project)])
        execute(
            [
                sys.executable,
                str(REPLACE),
                "--project",
                str(project),
                "--image",
                str(static_source),
                "--desktop-position",
                "55% center",
                "--mobile-position",
                "72% center",
            ]
        )
        html_path = project / "健身工作台.html"
        html = html_path.read_text(encoding="utf-8")
        if 'data-background-mode="static"' not in html or 'id="workbenchVideoSource"' in html:
            fail("只提供图片时没有切换为静态模式")
        if "--workbench-background-desktop-position:55% center" not in html:
            fail("桌面取景没有写入")
        if "--workbench-background-mobile-position:72% center" not in html:
            fail("手机取景没有写入")
        installed_image = project / "工作台与工具/健身工作台开发/界面素材/workbench-background.png"
        if installed_image.read_bytes() != static_source.read_bytes():
            fail("静态背景没有复制到工作台")
        backups = list((project / "历史与治理/背景备份").glob("*"))
        if len(backups) != 1:
            fail("首次替换没有生成唯一备份")
        for required in ("健身工作台.html", "background-backup.json", "界面素材/workbench-background.png", "界面素材/workbench-background.mp4"):
            if not (backups[0] / required).is_file():
                fail("背景备份缺少：" + required)
        assert_check(project)

        moved = temp / "新电脑（目录已改名）" / "健身工作台"
        moved.parent.mkdir(parents=True)
        shutil.move(str(project), str(moved))
        assert_check(moved)

        execute(
            [
                sys.executable,
                str(REPLACE),
                "--project",
                str(moved),
                "--image",
                str(dynamic_source),
                "--video",
                str(ASSETS / "workbench-background.mp4"),
            ]
        )
        html = (moved / "健身工作台.html").read_text(encoding="utf-8")
        if 'data-background-mode="video"' not in html or 'id="workbenchVideoSource"' not in html:
            fail("提供 MP4 后没有启用动态模式")
        assert_check(moved)

        release = temp / "分享副本"
        execute([sys.executable, str(RELEASE), "--project", str(moved), "--deploy", str(release)])
        output = execute(
            [sys.executable, str(CHECK), "--project", str(moved), "--deploy", str(release)]
        ).stdout
        if "FITNESS_WORKBENCH_CHECK: PASS" not in output:
            fail("自定义动态背景没有进入发布副本")

        bad_image = temp / "损坏壁纸.png"
        bad_image.write_bytes(b"not-an-image")
        before = (moved / "健身工作台.html").read_bytes()
        rejected = execute(
            [sys.executable, str(REPLACE), "--project", str(moved), "--image", str(bad_image)],
            expect_success=False,
        )
        if "只支持有效的 PNG" not in rejected.stderr:
            fail("损坏图片没有给出可读错误")
        if (moved / "健身工作台.html").read_bytes() != before:
            fail("损坏图片被拒绝后仍修改了工作台")

        unexpected = moved / "unexpected.bin"
        unexpected.write_bytes(b"force-post-change-check-failure")
        before_html = (moved / "健身工作台.html").read_bytes()
        before_image = (moved / "工作台与工具/健身工作台开发/界面素材/workbench-background.png").read_bytes()
        rolled_back = execute(
            [sys.executable, str(REPLACE), "--project", str(moved), "--image", str(static_source)],
            expect_success=False,
        )
        if "已自动回滚" not in rolled_back.stderr:
            fail("替换后检查失败没有明确报告自动回滚")
        if (moved / "健身工作台.html").read_bytes() != before_html:
            fail("替换后检查失败没有恢复 HTML")
        if (moved / "工作台与工具/健身工作台开发/界面素材/workbench-background.png").read_bytes() != before_image:
            fail("替换后检查失败没有恢复背景图片")
        unexpected.unlink()
        assert_check(moved)

        initialized = temp / "首次初始化自定义背景"
        execute(
            [
                sys.executable,
                str(INITIALIZE),
                "--target",
                str(initialized),
                "--background-image",
                str(static_source),
                "--background-video",
                str(ASSETS / "workbench-background.mp4"),
            ]
        )
        initialized_html = (initialized / "健身工作台.html").read_text(encoding="utf-8")
        if 'data-background-mode="video"' not in initialized_html:
            fail("初始化参数没有接入动态背景替换")
        assert_check(initialized)

    print("FITNESS_WORKBENCH_BACKGROUND_TEST: PASS")


if __name__ == "__main__":
    main()
