#!/usr/bin/env python3
"""Safely replace a generated workbench background and verify the result."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ASSET_RELATIVE = Path("工作台与工具/健身工作台开发/界面素材")
CONFIG_BLOCK = re.compile(
    r"(/\* FITNESS_WORKBENCH_BACKGROUND_CONFIG_START \*/)([\s\S]*?)(/\* FITNESS_WORKBENCH_BACKGROUND_CONFIG_END \*/)",
)
VIDEO_BLOCK = re.compile(r'<video\s+id="workbenchBgVideo"[\s\S]*?</video>')
POSITION_TOKEN = re.compile(r"^(?:left|right|top|bottom|center|-?\d+(?:\.\d+)?(?:%|px))$", re.I)


def fail(message: str) -> None:
    raise SystemExit("FITNESS_WORKBENCH_BACKGROUND: FAIL\n- " + message)


def css_position(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.split())
    parts = normalized.split(" ")
    if not 1 <= len(parts) <= 2 or any(not POSITION_TOKEN.fullmatch(part) for part in parts):
        fail(f"{label} 不是安全的 CSS 取景位置：{value}")
    return normalized


def detect_image_suffix(path: Path) -> str:
    with path.open("rb") as handle:
        header = handle.read(32)
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if header.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return ".webp"
    fail("背景图片只支持有效的 PNG、JPEG 或 WebP")


def validate_video(path: Path) -> None:
    if path.suffix.lower() != ".mp4":
        fail("动态背景只支持 MP4")
    with path.open("rb") as handle:
        header = handle.read(32)
    if path.stat().st_size < 100_000 or b"ftyp" not in header:
        fail("动态背景不是有效的 MP4")


def replace_css_variable(block: str, name: str, value: str) -> str:
    pattern = re.compile(r"(--" + re.escape(name) + r"\s*:\s*)[^;]+(;)")
    updated, count = pattern.subn(lambda match: match.group(1) + value + match.group(2), block, count=1)
    if count != 1:
        fail("背景配置缺少变量：--" + name)
    return updated


def build_html(
    html: str,
    image_relative: str,
    video_relative: str | None,
    desktop_position: str | None,
    mobile_position: str | None,
    nav_position: str | None,
) -> str:
    matches = CONFIG_BLOCK.findall(html)
    if len(matches) != 1:
        fail("工作台背景配置块数量不是 1")
    block_match = CONFIG_BLOCK.search(html)
    assert block_match is not None
    body = block_match.group(2)
    body = replace_css_variable(body, "workbench-background-image", f'url("{image_relative}")')
    if desktop_position:
        body = replace_css_variable(body, "workbench-background-desktop-position", desktop_position)
        body = replace_css_variable(body, "workbench-hero-desktop-position", desktop_position)
    if mobile_position:
        body = replace_css_variable(body, "workbench-background-mobile-position", mobile_position)
        body = replace_css_variable(body, "workbench-hero-mobile-position", mobile_position)
    if nav_position:
        body = replace_css_variable(body, "workbench-nav-position", nav_position)
    html = html[: block_match.start()] + block_match.group(1) + body + block_match.group(3) + html[block_match.end() :]

    if len(VIDEO_BLOCK.findall(html)) != 1:
        fail("工作台背景视频块数量不是 1")
    mode = "video" if video_relative else "static"
    source = (
        f'\n  <source id="workbenchVideoSource" src="{video_relative}" type="video/mp4">'
        if video_relative
        else ""
    )
    video = (
        f'<video id="workbenchBgVideo" class="workbench-video" data-background-mode="{mode}" '
        f'muted loop playsinline preload="auto" poster="{image_relative}" aria-hidden="true">'
        f"{source}\n</video>"
    )
    return VIDEO_BLOCK.sub(video, html, count=1)


def atomic_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".new")
    shutil.copy2(source, temporary)
    os.replace(temporary, target)


def atomic_text(path: Path, value: str) -> None:
    temporary = path.with_suffix(path.suffix + ".new")
    temporary.write_text(value.rstrip() + "\n", encoding="utf-8")
    os.replace(temporary, path)


def run_check(project: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    return subprocess.run(
        [sys.executable, str(HERE / "Check-FitnessWorkbench.py"), "--project", str(project)],
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, help="已经生成的个人训练系统目录")
    parser.add_argument("--image", required=True, help="PNG、JPEG 或 WebP 静态背景；始终作为视频兜底")
    parser.add_argument("--video", help="可选 MP4；不提供时自动切换为纯静态背景")
    parser.add_argument("--desktop-position", help="可选桌面取景，例如 '60%% center'")
    parser.add_argument("--mobile-position", help="可选手机取景，例如 '66%% center'")
    parser.add_argument("--nav-position", help="可选桌面侧栏取景，例如 '70%% center'")
    parser.add_argument("--backup-dir", help="可选备份目录；默认写入项目的历史与治理/背景备份")
    args = parser.parse_args()

    project = Path(args.project).resolve()
    html_path = project / "健身工作台.html"
    image_source = Path(args.image).resolve()
    video_source = Path(args.video).resolve() if args.video else None
    if not project.is_dir() or not html_path.is_file():
        fail("项目目录缺少健身工作台.html：" + str(project))
    if not image_source.is_file():
        fail("背景图片不存在：" + str(image_source))
    image_suffix = detect_image_suffix(image_source)
    if video_source:
        if not video_source.is_file():
            fail("背景视频不存在：" + str(video_source))
        validate_video(video_source)

    desktop_position = css_position(args.desktop_position, "桌面取景")
    mobile_position = css_position(args.mobile_position, "手机取景")
    nav_position = css_position(args.nav_position, "侧栏取景")
    asset_root = project / ASSET_RELATIVE
    if not asset_root.is_dir():
        fail("工作台界面素材目录不存在：" + str(asset_root))

    image_target = asset_root / ("workbench-background" + image_suffix)
    video_target = asset_root / "workbench-background.mp4" if video_source else None
    image_relative = image_target.relative_to(project).as_posix()
    video_relative = video_target.relative_to(project).as_posix() if video_target else None
    old_html = html_path.read_text(encoding="utf-8")
    new_html = build_html(
        old_html,
        image_relative,
        video_relative,
        desktop_position,
        mobile_position,
        nav_position,
    )

    stamp = dt.datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")
    backup = Path(args.backup_dir).resolve() if args.backup_dir else project / "历史与治理/背景备份" / stamp
    if backup.exists():
        if not backup.is_dir() or any(backup.iterdir()):
            fail("备份目录不是空目录：" + str(backup))
    backup.mkdir(parents=True, exist_ok=True)
    shutil.copy2(html_path, backup / "健身工作台.html")
    previous_assets = sorted(asset_root.glob("workbench-background.*"))
    backup_assets = backup / "界面素材"
    backup_assets.mkdir(parents=True, exist_ok=True)
    for source in previous_assets:
        if source.is_file():
            shutil.copy2(source, backup_assets / source.name)
    manifest = {
        "schema": 1,
        "created_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "mode": "video" if video_source else "static",
        "html": "健身工作台.html",
        "assets": ["界面素材/" + path.name for path in previous_assets if path.is_file()],
    }
    (backup / "background-backup.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    previous_values: dict[Path, bytes | None] = {}
    changed_targets = [image_target] + ([video_target] if video_target else [])
    for target in changed_targets:
        assert target is not None
        previous_values[target] = target.read_bytes() if target.is_file() else None
    try:
        atomic_copy(image_source, image_target)
        if video_source and video_target:
            atomic_copy(video_source, video_target)
        atomic_text(html_path, new_html)
        checked = run_check(project)
        if checked.returncode != 0 or "FITNESS_WORKBENCH_CHECK: PASS" not in checked.stdout:
            detail = (checked.stdout + checked.stderr).strip()
            raise RuntimeError("替换后的工作台检查失败\n" + detail)
    except Exception as exc:
        atomic_text(html_path, old_html)
        for target, previous in previous_values.items():
            if previous is None:
                target.unlink(missing_ok=True)
            else:
                temporary = target.with_suffix(target.suffix + ".restore")
                temporary.write_bytes(previous)
                os.replace(temporary, target)
        fail("已自动回滚；" + str(exc))

    if checked.stdout:
        print(checked.stdout.rstrip())
    print("FITNESS_WORKBENCH_BACKGROUND: PASS")
    print("mode: " + ("video" if video_source else "static"))
    print("image: " + str(image_target))
    if video_target:
        print("video: " + str(video_target))
    print("backup: " + str(backup))


if __name__ == "__main__":
    main()
