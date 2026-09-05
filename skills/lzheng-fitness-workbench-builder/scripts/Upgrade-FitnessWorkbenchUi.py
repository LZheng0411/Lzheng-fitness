#!/usr/bin/env python3
"""Explicit, data-preserving UI migration with verified backup and atomic replacement."""
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlparse

from workbench_ui import (BACKGROUND, BRAND, DATA, HASH, NAV, TEMPLATE, TITLE, VARIABLE, VIDEO,
                          UI_REVISION, canonical, data_block, digest, identity, seal, shell_hash, shell_problems, suite_version)


def safe_path(path: Path) -> Path:
    path = Path(os.path.abspath(path))
    for parent in (path, *path.parents):
        try:
            info = parent.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024):
            raise ValueError("路径包含软链接或重解析点，请使用真实目录")
    if path == Path(path.anchor):
        raise ValueError("不能使用磁盘根目录")
    return path.resolve()


def known_shells() -> dict:
    return json.loads((TEMPLATE.parent / "ui-history.json").read_text(encoding="utf-8"))


def inspect_html(html: str) -> dict:
    info = identity(html)
    current = TEMPLATE.read_text(encoding="utf-8")
    full = shell_hash(html)
    if full == shell_hash(current) and not shell_problems(html):
        status, source = ("current" if info["declared_hash_matches"] else "needs_ui_upgrade"), UI_REVISION
    else:
        registry = known_shells()
        source = registry.get("shells", {}).get(full)
        # Only a missing or damaged navigation element is ignored; all other code must match.
        navs = NAV.findall(html)
        repairable_nav = not navs or (len(navs) == 1 and re.fullmatch(r'<nav\b[^>]*>\s*</nav>', navs[0]) is not None)
        if source is None and repairable_nav:
            source = registry.get("without_navigation", {}).get(shell_hash(html, ignore_navigation=True))
        if source is None and repairable_nav and shell_hash(html, ignore_navigation=True) == shell_hash(current, ignore_navigation=True):
            source = UI_REVISION
        status = "needs_ui_upgrade" if source else "unknown_or_customized"
    return dict(info, status=status, source_release=source, target_ui_revision=UI_REVISION,
                runtime_suite_version=suite_version(), runtime_template=str(TEMPLATE))


def local_asset(project: Path, value: str) -> None:
    value = unquote(value)
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc or "\\" in value or Path(value).is_absolute():
        raise ValueError("背景必须使用项目内相对资源")
    target = safe_path(project / value)
    if not target.is_relative_to(project) or not target.is_file():
        raise ValueError("背景资源缺失或越出项目：" + value)


def preserve_customizations(old: str, new: str, project: Path) -> str:
    titles = TITLE.findall(old)
    if len(titles) != 1:
        raise ValueError("页面标题数量异常")
    new = TITLE.sub(lambda _: "<title>" + titles[0] + "</title>", new, count=1)
    brands = {m[1] for m in BRAND.findall(old)}
    if len(brands) != 1:
        raise ValueError("品牌标记不一致，需要人工迁移")
    brand = brands.pop()
    if not re.fullmatch(r"[\w\u4e00-\u9fff -]{1,32}", brand):
        raise ValueError("品牌包含不受支持字符")
    new = new.replace("__FWB_BRAND__", brand)
    blocks = BACKGROUND.findall(old)
    if len(blocks) != 1:
        raise ValueError("受管背景块缺失或重复")
    values = VARIABLE.findall(blocks[0][1])
    if len(values) != 6:
        raise ValueError("受管背景变量不完整")
    for name, value, _ in values:
        if "background-image" in name:
            image = re.fullmatch(r'url\("([^"]+)"\)', value.strip())
            if not image:
                raise ValueError("背景图片配置不受支持")
            local_asset(project, image[1])
        elif not re.fullmatch(r'(?:left|right|top|bottom|center|-?\d+(?:\.\d+)?(?:%|px))(?:\s+(?:left|right|top|bottom|center|-?\d+(?:\.\d+)?(?:%|px)))?', value.strip()):
            raise ValueError("背景取景配置不受支持")
    # Keep the entire block: canonical matching has already excluded unknown changes.
    new = BACKGROUND.sub(lambda _: "".join(blocks[0]), new, count=1)
    videos = VIDEO.findall(old)
    if len(videos) != 1:
        raise ValueError("受管视频块缺失或重复")
    video = videos[0]
    if re.search(r'<\s*(?:script|iframe)|\bon\w+\s*=', video, re.I):
        raise ValueError("视频块有未知脚本自定义")
    if not re.fullmatch(r'<video\b[^>]*>\s*(?:<source\b[^>]*>\s*)?</video>', video):
        raise ValueError("视频块有未知内容")
    for tag in re.findall(r'<(?:video|source)\b([^>]*)>', video):
        rest = re.sub(r'\b(?:id|class|data-background-mode|preload|poster|aria-hidden|src|data-src|type)="[^"]*"|\b(?:muted|loop|playsinline)\b', '', tag)
        if rest.strip():
            raise ValueError("视频块有未知属性")
    for value in re.findall(r'(?:poster|src|data-src)="([^"]+)"', video):
        local_asset(project, value)
    return VIDEO.sub(lambda _: video, new, count=1)


def prepare(html: str, project: Path) -> tuple[str, dict]:
    info = inspect_html(html)
    if info["status"] == "unknown_or_customized":
        # No user content is emitted: only changed shell line counts and hashes.
        diff = difflib.SequenceMatcher(None, canonical(html).splitlines(), canonical(TEMPLATE.read_text(encoding="utf-8")).splitlines())
        info["changed_shell_ranges"] = [{"old_lines": [a+1,b], "new_lines": [c+1,d]} for op,a,b,c,d in diff.get_opcodes() if op != "equal"][:30]
        raise ValueError("无法自动迁移此页面；请根据界面差异保留自定义后迁移：" + json.dumps(info, ensure_ascii=False))
    raw, data = data_block(html)
    if data.get("schema") != 6:
        raise ValueError("只接受 schema 6；先在独立流程迁移旧数据，未修改原页")
    if not isinstance(data.get("meta"), dict) or not isinstance(data.get("days"), dict):
        raise ValueError("页面事实数据不完整，未修改原页")
    new = TEMPLATE.read_text(encoding="utf-8")
    problems = shell_problems(new)
    if problems or not identity(new)["declared_hash_matches"]:
        raise ValueError("运行模板未通过界面校验：" + ";".join(problems))
    new = preserve_customizations(html, new, project)
    new = DATA.sub(lambda m: m[1] + raw + m[3], new)
    new = seal(new)
    if data_block(new)[0] != raw or shell_problems(new):
        raise ValueError("候选页面数据保留或界面校验失败")
    return new, info


def browser_smoke(candidate: Path) -> None:
    result = subprocess.run(["node", str(Path(__file__).with_name("Check-FitnessWorkbenchBrowser.cjs")), str(candidate)],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
    if result.returncode:
        raise ValueError("浏览器验证失败，原页面未升级。需要 Node.js、Playwright 和 Chromium。\n" + result.stdout + result.stderr)


def atomic_bytes(path: Path, content: bytes) -> None:
    fd, name = tempfile.mkstemp(prefix=".fitness-ui-", suffix=".html", dir=path.parent)
    temp = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def upgrade(project: Path, backup: Path | None, apply: bool, *, smoke=browser_smoke) -> dict:
    project = safe_path(project)
    formal = safe_path(project / "健身工作台.html")
    before = formal.read_bytes()
    old = before.decode("utf-8-sig")
    candidate, info = prepare(old, project)
    receipt = dict(info, workbench=str(formal), before_sha256=digest(before), data_sha256=digest(data_block(old)[0]),
                   ui_upgrade_prepared=True, ui_upgraded=False, data_refreshed=False, browser_verified=False,
                   deployed=False, online_verified=False, browser_records_backed_up=False)
    if not apply or info["status"] == "current":
        receipt["status"] = "current" if info["status"] == "current" else "ui_upgrade_prepared"
        return receipt
    if backup is None:
        raise ValueError("实际升级必须指定项目外备份目录")
    backup = safe_path(backup)
    if backup.is_relative_to(project) or project.is_relative_to(backup):
        raise ValueError("备份目录与项目不能包含或重叠")
    backup.mkdir(parents=True, exist_ok=True)
    lock = safe_path(project / ".fitness-ui-upgrade.lock")
    # Same-directory candidate resolves the same relative assets, but is never the final URL.
    fd, name = tempfile.mkstemp(prefix=".fitness-ui-check-", suffix=".html", dir=project)
    temporary = Path(name)
    replaced = False
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    saved = backup / ("workbench-before-ui-" + stamp + ".html")
    lock_fd = None
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(candidate.encode("utf-8"))
        lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        smoke(temporary)
        if formal.read_bytes() != before:
            raise ValueError("升级期间原文件发生变化，已停止以保留并发修改")
        with saved.open("xb") as handle:
            handle.write(before)
            handle.flush()
            os.fsync(handle.fileno())
        if saved.read_bytes() != before:
            raise ValueError("备份内容验证失败")
        os.replace(temporary, formal)
        replaced = True
        if formal.read_bytes() != candidate.encode("utf-8"):
            raise ValueError("正式页面写入后校验失败")
        smoke(formal)
        receipt.update(status="ui_upgraded", ui_upgraded=True, browser_verified=True,
                       after_sha256=digest(formal.read_bytes()), backup=str(saved), after_ui_revision=UI_REVISION)
        atomic_receipt = backup / ("ui-upgrade-" + stamp + ".json")
        atomic_bytes(atomic_receipt, (json.dumps(receipt, ensure_ascii=False, indent=2)+"\n").encode("utf-8"))
        return receipt
    except Exception:
        if replaced:
            # Do not destroy a new edit made by another process during post-verification.
            if formal.read_bytes() != candidate.encode("utf-8"):
                raise ValueError("替换后有并发修改；已保留现页，原页面备份：" + str(saved))
            atomic_bytes(formal, before)
            if formal.read_bytes() != before:
                raise ValueError("回滚校验失败；原页面备份：" + str(saved))
        raise
    finally:
        temporary.unlink(missing_ok=True)
        if lock_fd is not None:
            os.close(lock_fd)
            lock.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--backup-dir", type=Path)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check-only", action="store_true")
    group.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(upgrade(args.project, args.backup_dir, args.apply), ensure_ascii=False, indent=2))
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print("FITNESS_WORKBENCH_UI_UPGRADE: FAIL\n" + str(exc), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
