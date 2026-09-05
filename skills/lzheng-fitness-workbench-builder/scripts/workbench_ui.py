"""Shared UI identity and compatibility checks. No user data is regenerated here."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

UI_REVISION = "2026.09.05.1"
HERE = Path(__file__).resolve().parent
TEMPLATE = HERE.parent / "assets/workbench-template.html"
DATA = re.compile(r'(<script id="workbench-data" type="application/json">)([\s\S]*?)(</script>)')
NAV = re.compile(r'<nav\b[^>]*\bid="navBar"[^>]*>[\s\S]*?</nav>')
TITLE = re.compile(r'^<title>([^\r\n]*?)</title>', re.M)
BRAND = re.compile(r'(content:")([^";]+?)( / |\\A TRAINING| / TRAINING)(")')
BACKGROUND = re.compile(r'(/\* FITNESS_WORKBENCH_BACKGROUND_CONFIG_START \*/)([\s\S]*?)(/\* FITNESS_WORKBENCH_BACKGROUND_CONFIG_END \*/)')
VARIABLE = re.compile(r'(--workbench-(?:background-image|background-desktop-position|background-mobile-position|hero-desktop-position|hero-mobile-position|nav-position)\s*:\s*)([^;]+)(;)')
VIDEO = re.compile(r'<video\s+id="workbenchBgVideo"[\s\S]*?</video>')
HASH = re.compile(r'(<meta name="workbench-shell-sha256" content=")[^"]*(">)')
ITEMS = (("today", "训练"), ("week", "计划"), ("trend", "负荷"), ("record", "复盘"), ("settings", "指南"))


def digest(value: str | bytes) -> str:
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


def data_block(html: str) -> tuple[str, dict]:
    matches = list(DATA.finditer(html))
    if len(matches) != 1:
        raise ValueError("需要唯一的 workbench-data 数据块")
    raw = matches[0].group(2)
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("工作台数据必须是 JSON 对象")
    return raw, data


def canonical(html: str, *, ignore_navigation: bool = False) -> str:
    """Ignore only documented customizations; unknown CSS/JS still changes the hash."""
    html = html.replace("\r\n", "\n").lstrip("\ufeff")
    html = DATA.sub(lambda m: m[1] + "{}" + m[3], html)
    html = TITLE.sub("<title>__TITLE__</title>", html)
    html = BRAND.sub(lambda m: m[1] + "__FWB_BRAND__" + m[3] + m[4], html)
    html = BACKGROUND.sub(lambda m: m[1] + VARIABLE.sub(lambda v: v[1] + "__VALUE__" + v[3], m[2]) + m[3], html)
    html = VIDEO.sub('<video id="workbenchBgVideo">__MANAGED_VIDEO__</video>', html)
    html = HASH.sub(lambda m: m[1] + "__HASH__" + m[2], html)
    if ignore_navigation:
        html = NAV.sub("", html)
    return html.strip()


def shell_hash(html: str, *, ignore_navigation: bool = False) -> str:
    return digest(canonical(html, ignore_navigation=ignore_navigation))


def seal(html: str) -> str:
    if len(HASH.findall(html)) != 1:
        raise ValueError("界面指纹标记数量异常")
    return HASH.sub(lambda m: m[1] + shell_hash(html) + m[2], html)


def nav_items(html: str) -> tuple:
    matches = NAV.findall(html)
    if len(matches) != 1:
        return ()
    return tuple(re.findall(r'<a\b[^>]*data-k="([^"]+)"[^>]*>[\s\S]*?<span>([^<]+)</span>[\s\S]*?</a>', matches[0]))


def shell_problems(html: str) -> list[str]:
    problems = []
    if len(NAV.findall(html)) != 1:
        problems.append("固定导航容器 navBar 数量异常")
    elif not re.search(r'<nav\b[^>]*class="[^"]*\bnav\b[^"]*"', NAV.findall(html)[0]):
        problems.append("固定导航布局类缺失")
    if nav_items(html) != ITEMS:
        problems.append("固定导航入口缺失或顺序异常")
    if '<script id="workbench-shell">' not in html or "window.FitnessShell" not in html:
        problems.append("独立导航脚本缺失")
    if f'data-ui-revision="{UI_REVISION}"' not in html:
        problems.append("界面版本需要升级")
    for key, _ in ITEMS:
        if len(re.findall(r'\bid="m-' + key + '"', html)) != 1:
            problems.append("固定工作台区块数量异常: " + key)
    return problems


def identity(html: str) -> dict:
    revision = re.search(r'data-ui-revision="([^"]+)"', html)
    declared = HASH.search(html)
    actual = shell_hash(html)
    return {"ui_revision": revision[1] if revision else None, "shell_sha256": actual,
            "declared_hash_matches": bool(declared and declared[0] == declared[1] + actual + declared[2])}


def suite_version() -> str:
    source = HERE.parents[1] / "lzheng-training-system/scripts/lzheng_training_system.py"
    match = re.search(r'^SUITE_VERSION = "([^"]+)"', source.read_text(encoding="utf-8"), re.M)
    if not match:
        raise ValueError("无法识别当前套件版本")
    return match[1]
