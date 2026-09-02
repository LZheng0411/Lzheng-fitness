#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Check-FitnessWorkbench.py — 健身工作台发布前自动检查（P0-3，权威入口）
============================================================
检查项：
1. 结构：根目录白名单（4 文件 + 01-06/99 七目录）、当前周期单版本、
   无 tmp/__pycache__/chrome-profile、06 无 skills 副本、无 .pyc。
2. 数据：调用 Build-FitnessWorkbenchData.py --check-only（版本/周次/曲线一致性）。
3. HTML：唯一 workbench-data 数据块、JSON 可解析、schema=6、
   source_version 与当前周期最新版本一致。
4. 发布目录：递归核对 manifest、精确允许列表、资源哈希和本机隐私边界。

任一失败输出 FAIL 并退出码 1，不得发布。

用法：
  python Check-FitnessWorkbench.py --project <项目根> [--notion <notion-data.json>]
    [--notion-mode incremental|full] [--replace-main-lift-history]
    [--deploy <发布目录>] [--expect-release-mode <模式>] [--allow-private-portable]
"""
import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

WHITELIST_FILES = {"AGENTS.md", "README.md"}
WHITELIST_DIR_NAMES = ("训练与周期", "知识库入口", "训练复盘与状态", "工作台与工具", "历史与治理")
RELEASE_MODES = ("private-portable", "public-anonymized")
MANIFEST_NAME = "release-manifest.json"
MANIFEST_SCHEMA = 2
MANIFEST_KIND = "lzheng-fitness-workbench-release"
MANIFEST_PRODUCER = "Prepare-FitnessWorkbenchRelease.py"
PUBLIC_SHELL_ID = "fitness-public-anonymous-v1"
PUBLIC_SHELL_VIEW_SHA256 = "6f338f560d2e59e2699cb8f93d56c474af8690d9e7d96fd4f8283022de537e6b"
PUBLIC_DAY_NAMES = ("上肢A", "腿B", "上肢B", "腿A")
WINDOWS_PATH_IN_TEXT = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]")
LOCAL_EDIT_EXPRESSION = re.compile(
    r'''(["'])obsidian://open\?path=\1\s*\+\s*encodeURIComponent\(absolute\)''',
    re.I,
)
TEXT_RELEASE_SUFFIXES = {".html", ".json", ".md", ".txt", ".css", ".js", ".svg", ".xml", ".yml", ".yaml", ".toml"}
WORKBENCH_TEMPLATE_MARKER = 'data-ui-template="lzheng-fitness-workbench-v3"'
WORKBENCH_SECTION_IDS = ("m-today", "m-week", "m-trend", "m-record", "m-settings")
WORKBENCH_NAV_ITEMS = (("today", "训练"), ("week", "计划"), ("trend", "负荷"), ("record", "复盘"), ("settings", "指南"))


def run_utf8(command):
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    return subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)


def check_workbench_shell(html):
    """Validate the fixed shell that data-only refreshes must never remove."""
    problems = []
    if WORKBENCH_TEMPLATE_MARKER not in html:
        problems.append("缺少固定工作台模板版本标记")
    nav_tags = re.findall(r"<nav\b[^>]*>", html, re.I)
    nav_containers = [
        tag for tag in nav_tags
        if re.search(r'\bid=["\']navBar["\']', tag, re.I)
        and re.search(r'\bclass=["\'][^"\']*\bnav\b[^"\']*["\']', tag, re.I)
    ]
    if len(nav_containers) != 1:
        problems.append("固定导航容器 navBar 数量异常: %d" % len(nav_containers))
    for section_id in WORKBENCH_SECTION_IDS:
        if not re.search(r'id=["\']%s["\']' % re.escape(section_id), html):
            problems.append("缺少固定工作台区块: " + section_id)
    nav_match = re.search(r"var navs\s*=\s*\[([\s\S]*?)\];", html)
    nav_items = tuple(re.findall(r"\[['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]", "[" + nav_match.group(1))) if nav_match else ()
    if nav_items != WORKBENCH_NAV_ITEMS:
        problems.append("固定导航配置缺失或顺序异常")
    if "navBar.appendChild(a)" not in html:
        problems.append("固定导航初始化逻辑缺失")
    return problems


def fail(msg):
    print("FITNESS_WORKBENCH_CHECK: FAIL")
    print("- " + msg)
    sys.exit(1)


def check_structure(project):
    problems = []
    root_files = [f for f in os.listdir(project) if os.path.isfile(os.path.join(project, f))]
    html = [f for f in root_files if f.endswith(".html")]
    op_md = [f for f in root_files if f.endswith(".md") and f not in WHITELIST_FILES]
    unexpected = [f for f in root_files if f not in WHITELIST_FILES and not f.endswith((".html", ".md"))]
    if len(html) != 1:
        problems.append("根目录正式 HTML 数量异常: %d" % len(html))
    if len(op_md) != 1:
        problems.append("根目录操作型 md 数量异常: %d" % len(op_md))
    for f in unexpected:
        problems.append("白名单外文件: %s" % f)
    dirs = [d for d in os.listdir(project) if os.path.isdir(os.path.join(project, d))]
    for name in WHITELIST_DIR_NAMES:
        if dirs.count(name) != 1:
            problems.append("根目录目录缺失或重复: %s" % name)
    for d in dirs:
        if d not in WHITELIST_DIR_NAMES:
            problems.append("白名单外目录: %s" % d)
    # 工作台与工具目录无 skills 副本
    tools = [d for d in dirs if d == "工作台与工具"]
    if tools and os.path.isdir(os.path.join(project, tools[0], "skills")):
        problems.append("工作台与工具目录存在 skills 代码副本")
    # 禁止生成物
    for root, subdirs, files in os.walk(project):
        for sd in subdirs:
            if sd in ("tmp", "__pycache__") or sd.startswith("chrome-profile"):
                problems.append("禁止目录: " + os.path.join(root, sd))
        for f in files:
            if f.endswith(".pyc"):
                problems.append("禁止编译文件: " + os.path.join(root, f))
    # 当前周期单版本
    cur = os.path.join(project, "训练与周期", "当前周期")
    if os.path.isdir(cur):
        groups = {}
        for name in os.listdir(cur):
            m = re.match(r"^(.*)-v(\d+)\.(html|json)$", name)
            if m:
                groups.setdefault(m.group(1), set()).add(int(m.group(2)))
        for base, vers in groups.items():
            if len(vers) > 1:
                problems.append("当前周期多版本: %s %s" % (base, sorted(vers)))
    return problems


def run_builder(
    project,
    notion,
    restore_notion_from_html=None,
    notion_mode=None,
    replace_main_lift_history=False,
):
    cmd = [PY, os.path.join(SCRIPT_DIR, "Build-FitnessWorkbenchData.py"), "--project", project, "--check-only"]
    if notion and os.path.isfile(notion):
        cmd += ["--notion", notion]
        if notion_mode:
            cmd += ["--notion-mode", notion_mode]
        if replace_main_lift_history:
            cmd += ["--replace-main-lift-history"]
    if restore_notion_from_html and os.path.isfile(restore_notion_from_html):
        cmd += ["--restore-notion-from-html", restore_notion_from_html]
    out = run_utf8(cmd)
    if out.returncode != 0 or "FITNESS_WORKBENCH_DATA: PASS" not in out.stdout:
        return "数据校验未通过:\n" + (out.stdout + out.stderr).strip()
    return None


def load_generated_data(
    project,
    notion,
    restore_notion_from_html=None,
    notion_mode=None,
    replace_main_lift_history=False,
):
    cmd = [PY, os.path.join(SCRIPT_DIR, "Build-FitnessWorkbenchData.py"), "--project", project, "--check-only", "--out", "-"]
    if notion and os.path.isfile(notion):
        cmd += ["--notion", notion]
        if notion_mode:
            cmd += ["--notion-mode", notion_mode]
        if replace_main_lift_history:
            cmd += ["--replace-main-lift-history"]
    if restore_notion_from_html and os.path.isfile(restore_notion_from_html):
        cmd += ["--restore-notion-from-html", restore_notion_from_html]
    out = run_utf8(cmd)
    if out.returncode != 0:
        return None
    for line in out.stdout.splitlines():
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                return None
    return None


def normalize_generated(data):
    """忽略每次生成都会变化、但不影响工作台事实内容的审计时间。"""
    value = json.loads(json.dumps(data, ensure_ascii=False))
    if isinstance(value.get("sync"), dict):
        value["sync"].pop("last_attempt", None)
    if isinstance(value.get("provenance"), dict):
        for item in value["provenance"].values():
            if isinstance(item, dict):
                item.pop("verified_at", None)
    return value


def resolve_project_entry(project, value):
    """Resolve a stored relative path/href and reject schemes or path traversal."""
    parsed = urlparse(str(value or ""))
    if parsed.scheme or parsed.netloc:
        return None
    decoded = unquote(parsed.path).replace("/", os.sep)
    if not decoded or os.path.isabs(decoded):
        return None
    root = os.path.abspath(project)
    target = os.path.abspath(os.path.join(root, decoded))
    try:
        if os.path.commonpath([root, target]) != root:
            return None
    except ValueError:
        return None
    return target


def extract_asset_paths(html):
    paths = []
    candidates = re.findall(r'url\(["\']?([^"\')]+)', html)
    candidates += re.findall(r'''(?:src|poster)\s*=\s*["']([^"']+)["']''', html, re.I)
    for raw in candidates:
        value = raw.strip()
        if not value or value.startswith(("data:", "http://", "https://", "#", "blob:")):
            continue
        parsed = urlparse(value)
        if parsed.scheme or parsed.netloc or not parsed.path:
            continue
        paths.append(unquote(parsed.path))
    return list(dict.fromkeys(paths))


def disable_local_edit_capability(html):
    return LOCAL_EDIT_EXPRESSION.sub("''", html)


def release_view(html):
    block_pattern = r'(<script id="workbench-data" type="application/json">)[\s\S]*?(</script>)'
    without_data = re.sub(block_pattern, r"\1{}\2", html, count=1)
    return disable_local_edit_capability(without_data)


def validate_public_shell_html(html):
    problems = []
    view_hash = hashlib.sha256(release_view(html).encode("utf-8")).hexdigest()
    if view_hash != PUBLIC_SHELL_VIEW_SHA256:
        problems.append("public-anonymized 不是身份中立的固定静态壳")
    if html.count('data-release-shell="' + PUBLIC_SHELL_ID + '"') != 1:
        problems.append("public-anonymized 缺少固定公开壳标记")
    if extract_asset_paths(html):
        problems.append("public-anonymized 禁止引用任何本地或外部媒体资源")
    if re.search(r"<(?:img|video|audio|source|iframe|object|embed)\b", html, re.I):
        problems.append("public-anonymized 禁止包含媒体或嵌入标签")
    return problems


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_link_like(path):
    is_junction = getattr(path, "is_junction", None)
    if path.is_symlink() or bool(is_junction and is_junction()):
        return True
    try:
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def first_link_component(path):
    """Inspect the lexical path before resolve; reject link-like parents too."""
    absolute = Path(path).expanduser().absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if os.path.lexists(current) and is_link_like(current):
            return current
    return None


def release_tree(deploy_dir):
    root = Path(deploy_dir).resolve()
    files = {}
    directories = set()
    problems = []
    for current, subdirs, names in os.walk(root, followlinks=False):
        current_path = Path(current)
        for name in list(subdirs):
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            if is_link_like(path):
                problems.append("发布目录包含符号链接、junction 或 reparse 目录: " + relative)
                subdirs.remove(name)
            else:
                directories.add(relative)
        for name in names:
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            if is_link_like(path):
                problems.append("发布目录包含符号链接或 reparse 文件: " + relative)
            else:
                files[relative] = path
    return files, directories, problems


def expected_parent_directories(files):
    expected = set()
    for relative in files:
        parent = PurePosixPath(relative).parent
        while str(parent) not in ("", "."):
            expected.add(parent.as_posix())
            parent = parent.parent
    return expected


def safe_manifest_relative(value):
    if not isinstance(value, str) or not value or "\\" in value:
        return None
    relative = PurePosixPath(value)
    if relative.is_absolute() or any(part in ("", ".", "..") for part in relative.parts):
        return None
    return relative.as_posix()


def validate_public_anonymized_data(data):
    problems = []
    release = data.get("release", {})
    if release != {
        "mode": "public-anonymized",
        "anonymized": True,
        "contains_personal_data": False,
    }:
        problems.append("公开匿名版的数据标记不完整")
    meta = data.get("meta", {})
    if not isinstance(meta, dict):
        problems.append("公开匿名版渲染契约类型错误: meta 必须是对象")
        meta = {}
    if meta.get("source_version") != "public-anonymized":
        problems.append("公开匿名版仍使用个人计划版本")
    if meta.get("plan_file") or meta.get("plan_href") or meta.get("baseline_file"):
        problems.append("公开匿名版仍包含个人计划或执行基准入口")
    for key, empty in (
        ("timeline", []),
        ("week", []),
        ("phases", []),
        ("charts", {}),
        ("goal_metrics", []),
        ("reviews", []),
        ("rules", []),
        ("links", {}),
        ("documents", {}),
    ):
        if data.get(key) != empty:
            problems.append("公开匿名版仍包含个人数据字段: " + key)

    if not isinstance(data.get("rest_days"), str):
        problems.append("公开匿名版渲染契约类型错误: rest_days 必须是字符串")
    days = data.get("days")
    weekday = data.get("weekday")
    if not isinstance(days, dict) or set(days) != set(PUBLIC_DAY_NAMES):
        problems.append("公开匿名版渲染契约错误: days 必须提供四个无处方占位训练日")
    else:
        for name in PUBLIC_DAY_NAMES:
            item = days[name]
            if not isinstance(item, dict) or item.get("exercises") != []:
                problems.append("公开匿名版训练日仍含处方或类型错误: days." + name)
                continue
            if item.get("date") or not isinstance(item.get("title"), str) or not isinstance(item.get("role"), str):
                problems.append("公开匿名版训练日仍含日期或渲染字段类型错误: days." + name)
    if not isinstance(weekday, dict) or any(not isinstance(weekday.get(name), str) for name in PUBLIC_DAY_NAMES):
        problems.append("公开匿名版渲染契约类型错误: weekday")

    notion = data.get("notion", {})
    if not isinstance(notion, dict):
        problems.append("公开匿名版渲染契约类型错误: notion 必须是对象")
        notion = {}
    for key in ("bodyweight", "sessions", "main_lifts", "activity"):
        if notion.get(key) != []:
            problems.append("公开匿名版 Notion 字段必须是空列表: " + key)
    if notion.get("latest_by_exercise") != {}:
        problems.append("公开匿名版 Notion 字段必须是空对象: latest_by_exercise")
    if notion.get("baseline_kg") is not None:
        problems.append("公开匿名版仍包含 Notion 体重基线: baseline_kg")
    if notion.get("notion_url") not in (None, ""):
        problems.append("公开匿名版仍包含 Notion URL: notion_url")
    serialized = json.dumps(data, ensure_ascii=False)
    if re.search(r"https?://[^\s\"']*notion\.", serialized, re.I):
        problems.append("公开匿名版仍包含 Notion URL")
    return problems


def validate_release_manifest(manifest, mode, actual_files, expected_files):
    problems = []
    private = mode == "private-portable"
    expected_flags = {
        "anonymized": not private,
        "contains_personal_data": private,
        "required_access": "private-authenticated" if private else "public",
    }
    if manifest.get("schema") != MANIFEST_SCHEMA:
        problems.append("release-manifest schema 必须为 %d" % MANIFEST_SCHEMA)
    if manifest.get("kind") != MANIFEST_KIND or manifest.get("producer") != MANIFEST_PRODUCER:
        problems.append("release-manifest 缺少发布器所有权标记")
    if manifest.get("release_mode") != mode:
        problems.append("release-manifest 模式与 index.html 不一致")
    if manifest.get("entrypoint") != "index.html" or manifest.get("fresh_staging") is not True:
        problems.append("release-manifest 未声明 fresh staging 与固定入口")
    for key, value in expected_flags.items():
        if manifest.get(key) != value:
            problems.append("release-manifest 隐私标记错误: " + key)
    if mode == "public-anonymized":
        if manifest.get("public_shell") != PUBLIC_SHELL_ID:
            problems.append("release-manifest 公开静态壳标记错误")
        if manifest.get("public_shell_view_sha256") != PUBLIC_SHELL_VIEW_SHA256:
            problems.append("release-manifest 公开静态壳哈希错误")

    allowed = manifest.get("allowed_files")
    if (
        not isinstance(allowed, list)
        or any(safe_manifest_relative(path) is None for path in allowed)
        or len(allowed) != len(set(allowed))
    ):
        problems.append("release-manifest allowed_files 无效或重复")
    elif {safe_manifest_relative(path) for path in allowed} != expected_files:
        problems.append("release-manifest 允许列表与页面实际依赖不一致")

    entries = manifest.get("files")
    if not isinstance(entries, list):
        problems.append("release-manifest 缺少文件哈希列表")
        return problems
    entry_map = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            problems.append("release-manifest 文件条目无效")
            continue
        relative = safe_manifest_relative(entry["path"])
        if not relative:
            problems.append("release-manifest 文件路径非法")
            continue
        if relative in entry_map:
            problems.append("release-manifest 文件条目重复: " + relative)
        entry_map[relative] = entry
    expected_artifacts = expected_files - {MANIFEST_NAME}
    if set(entry_map) != expected_artifacts:
        problems.append("release-manifest 哈希列表与精确允许列表不一致")
    for relative in expected_artifacts & set(entry_map) & set(actual_files):
        entry = entry_map[relative]
        path = actual_files[relative]
        if entry.get("bytes") != path.stat().st_size or entry.get("sha256") != file_sha256(path):
            problems.append("发布文件与 manifest 哈希不一致: " + relative)
    return problems


def check_html(
    project,
    notion=None,
    restore_notion_from_html=None,
    notion_mode=None,
    replace_main_lift_history=False,
):
    problems = []
    html_path = os.path.join(project, "健身工作台.html")
    if not os.path.isfile(html_path):
        return ["缺少根目录健身工作台.html"]
    with open(html_path, encoding="utf-8") as fh:
        html = fh.read()
    problems.extend(check_workbench_shell(html))
    blocks = re.findall(r'<script id="workbench-data" type="application/json">([\s\S]*?)</script>', html)
    if len(blocks) != 1:
        problems.append("数据块数量异常: %d" % len(blocks))
        return problems
    try:
        data = json.loads(blocks[0])
    except Exception as e:
        problems.append("数据块 JSON 解析失败: %s" % e)
        return problems
    generated = load_generated_data(
        project,
        notion,
        restore_notion_from_html,
        notion_mode,
        replace_main_lift_history,
    )
    if generated is None:
        problems.append("无法生成用于比对的最新数据")
    else:
        if normalize_generated(data) != normalize_generated(generated):
            problems.append("正式 HTML 数据块不是最新生成结果")
    if data.get("schema") != 6:
        problems.append("schema 必须为 6: %s" % data.get("schema"))
    data_end = html.find("</script>", html.find('id="workbench-data"'))
    view_source = html[data_end + len("</script>"):] if data_end >= 0 else html
    if html.count("FITNESS_WORKBENCH_BACKGROUND_CONFIG_START") != 1 or html.count("FITNESS_WORKBENCH_BACKGROUND_CONFIG_END") != 1:
        problems.append("背景配置块数量异常")
    video_blocks = re.findall(r'<video\s+id="workbenchBgVideo"[\s\S]*?</video>', html)
    if len(video_blocks) != 1:
        problems.append("背景视频块数量异常")
    else:
        mode_match = re.search(r'data-background-mode="(static|video)"', video_blocks[0])
        if not mode_match:
            problems.append("背景模式未声明")
        elif mode_match.group(1) == "video" and 'id="workbenchVideoSource"' not in video_blocks[0]:
            problems.append("动态背景模式缺少 MP4 source")
        elif mode_match.group(1) == "static" and 'id="workbenchVideoSource"' in video_blocks[0]:
            problems.append("静态背景模式仍引用视频 source")
    if re.search(r"当前\s*v\d+|页面按\s*v\d+|打开\s*v\d+|验证计划-v\d+", view_source):
        problems.append("视图代码仍写死具体计划版本")
    cur = os.path.join(project, "训练与周期", "当前周期")
    latest = 0
    if os.path.isdir(cur):
        for name in os.listdir(cur):
            m = re.match(r".*-v(\d+)\.json$", name)
            if m:
                latest = max(latest, int(m.group(1)))
    src_ver = data.get("meta", {}).get("source_version", "")
    m2 = re.search(r"v(\d+)$", src_ver)
    if not m2 or int(m2.group(1)) != latest:
        problems.append("source_version %s 与当前周期最新 v%d 不一致" % (src_ver, latest))
    meta = data.get("meta", {})
    if meta.get("baseline_version") != src_ver:
        problems.append("执行基准版本与当前计划不一致")
    if not meta.get("plan_start") or not meta.get("plan_end"):
        problems.append("周期起止日期缺失")
    plan_target = resolve_project_entry(project, meta.get("plan_href"))
    plan_file_target = resolve_project_entry(project, meta.get("plan_file"))
    if not plan_target or not plan_file_target or plan_target != plan_file_target or not os.path.isfile(plan_target):
        problems.append("完整计划入口无效")
    timeline = data.get("timeline", [])
    expected_done = {
        x.get("day"): "已执行 " + x.get("date", "")[5:]
        for x in timeline
        if x.get("type") == "training" and x.get("status") == "done" and x.get("day") and x.get("date")
    }
    if data.get("done") != expected_done:
        problems.append("完成状态与当前时间线不一致")
    for day, item in data.get("days", {}).items():
        mains = [x for x in item.get("exercises", []) if x.get("main")]
        if not mains:
            problems.append("训练日未识别到主项: " + day)
        for exercise in mains:
            if data.get("onboarding", {}).get("completed") is False:
                continue
            if not exercise.get("w") or not exercise.get("d"):
                problems.append("主项缺少精确处方: %s/%s" % (day, exercise.get("name")))
    for review in data.get("reviews", []):
        target = resolve_project_entry(project, review.get("file_path"))
        if not target or not os.path.isfile(target):
            problems.append("复盘入口无效: " + str(review.get("file")))
        elif review.get("content_markdown") != Path(target).read_text(encoding="utf-8-sig"):
            problems.append("复盘内置内容不是当前文件: " + str(review.get("file")))
    links = data.get("links", {})
    documents = data.get("documents", {})
    for key, label in (("review_index", "训练复盘索引"), ("status_index", "状态档案索引")):
        target = resolve_project_entry(project, links.get(key + "_file"))
        if not target or not os.path.isfile(target):
            problems.append(label + "文件入口无效")
            continue
        document = documents.get(key) if isinstance(documents, dict) else None
        if not isinstance(document, dict) or document.get("file_path") != links.get(key + "_file"):
            problems.append(label + "未嵌入工作台内置阅读器")
        elif document.get("content_markdown") != Path(target).read_text(encoding="utf-8-sig"):
            problems.append(label + "内置内容不是当前文件")
    summary = data.get("today_summary")
    if summary and not any(x.get("date") == summary.get("date") and x.get("day") == summary.get("day") and x.get("status") == "done" for x in timeline):
        problems.append("今日复盘与今日时间线不一致")
    for rel in extract_asset_paths(html):
        target = resolve_project_entry(project, rel)
        if not target or not os.path.isfile(target):
            problems.append("页面资源不存在: " + rel)
    onboarding = data.get("onboarding", {})
    system = data.get("system", {})
    knowledge = data.get("knowledge", {})
    status = data.get("status", {})
    provenance = data.get("provenance", {})
    goal_metrics = data.get("goal_metrics")
    for key, value in (("onboarding", onboarding), ("system", system), ("knowledge", knowledge), ("status", status), ("provenance", provenance)):
        if not isinstance(value, dict) or not value:
            problems.append("schema 6 缺少对象: " + key)
    if not isinstance(goal_metrics, list):
        problems.append("schema 6 缺少目标数据列表: goal_metrics")
    if onboarding.get("completed") is False and any(exercise.get("w") for day in data.get("days", {}).values() for exercise in day.get("exercises", [])):
        problems.append("待建档状态不应出现正式训练重量")
    if status.get("state") == "stale" and not status.get("reason"):
        problems.append("过期训练状态缺少原因")
    if system.get("workbench_schema") != 6:
        problems.append("system.workbench_schema 与 schema 6 不一致")
    return problems


def check_deploy(
    deploy_dir,
    source_html=None,
    allow_private_portable=False,
    expected_release_mode=None,
):
    if not deploy_dir:
        return []
    deploy_path = Path(deploy_dir).expanduser().absolute()
    link_component = first_link_component(deploy_path)
    if link_component:
        return ["发布目录路径经过符号链接、junction 或 reparse point: " + str(link_component)]
    root = deploy_path.resolve()
    if not root.is_dir():
        return ["发布目录不存在、不是目录或是符号链接"]

    actual_files, actual_directories, problems = release_tree(root)
    if "index.html" not in actual_files:
        return problems + ["发布目录缺少 index.html"]
    if MANIFEST_NAME not in actual_files:
        return problems + ["发布目录缺少 release-manifest.json；不能证明来自 fresh staging"]

    try:
        manifest = json.loads(actual_files[MANIFEST_NAME].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return problems + ["release-manifest.json 无法解析: %s" % exc]
    if not isinstance(manifest, dict):
        return problems + ["release-manifest.json 顶层必须是对象"]
    mode = manifest.get("release_mode")
    if mode not in RELEASE_MODES:
        problems.append("发布模式无效: " + str(mode))
    if expected_release_mode and mode != expected_release_mode:
        problems.append("发布模式不是预期的 %s: %s" % (expected_release_mode, mode))
    if mode == "private-portable" and not allow_private_portable:
        problems.append(
            "private-portable 含个人训练数据且不等于匿名版；仅在确认私有鉴权后使用 --allow-private-portable"
        )

    html = actual_files["index.html"].read_text(encoding="utf-8")
    blocks = re.findall(r'<script id="workbench-data" type="application/json">([\s\S]*?)</script>', html)
    deploy_data = None
    if len(blocks) != 1:
        problems.append("发布目录 workbench-data 数量异常")
    else:
        try:
            deploy_data = json.loads(blocks[0])
        except json.JSONDecodeError:
            problems.append("发布目录 workbench-data 无法解析")
        if deploy_data is not None and not isinstance(deploy_data, dict):
            problems.append("发布目录 workbench-data 顶层必须是对象")
            deploy_data = None

    expected_files = {"index.html", MANIFEST_NAME}
    for rel in extract_asset_paths(html):
        target = resolve_project_entry(root, rel)
        if not target or not os.path.isfile(target):
            problems.append("发布目录缺少页面资源: " + rel)
        else:
            expected_files.add(Path(target).relative_to(root).as_posix())

    if deploy_data is not None:
        release = deploy_data.get("release", {})
        if not isinstance(release, dict):
            release = {}
        if release.get("mode") != mode:
            problems.append("index.html 发布模式与 manifest 不一致")
        if mode == "private-portable":
            if release.get("anonymized") is not False or release.get("contains_personal_data") is not True:
                problems.append("private-portable 被错误标记为匿名或无个人数据")
            plan_target = resolve_project_entry(root, deploy_data.get("meta", {}).get("plan_href"))
            if not plan_target or not os.path.isfile(plan_target):
                problems.append("private-portable 发布目录缺少完整计划 HTML")
            else:
                expected_files.add(Path(plan_target).relative_to(root).as_posix())
            documents = deploy_data.get("documents", {})
            for key, label in (("review_index", "训练复盘索引"), ("status_index", "状态档案索引")):
                document = documents.get(key) if isinstance(documents, dict) else None
                if not isinstance(document, dict) or not document.get("content_markdown"):
                    problems.append("private-portable 发布目录缺少内置" + label)
        elif mode == "public-anonymized":
            problems.extend(validate_public_anonymized_data(deploy_data))
    if mode == "public-anonymized":
        problems.extend(validate_public_shell_html(html))

    problems.extend(validate_release_manifest(manifest, mode, actual_files, expected_files))
    unexpected_files = sorted(set(actual_files) - expected_files)
    missing_files = sorted(expected_files - set(actual_files))
    if unexpected_files:
        problems.append("发布目录存在允许列表外文件: " + "、".join(unexpected_files))
    if missing_files:
        problems.append("发布目录缺少允许列表文件: " + "、".join(missing_files))
    expected_directories = expected_parent_directories(expected_files)
    unexpected_directories = sorted(actual_directories - expected_directories)
    if unexpected_directories:
        problems.append("发布目录存在允许列表外目录: " + "、".join(unexpected_directories))

    for relative, path in sorted(actual_files.items()):
        if path.suffix.lower() not in TEXT_RELEASE_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            problems.append("发布文本文件不是 UTF-8: " + relative)
            continue
        if WINDOWS_PATH_IN_TEXT.search(text):
            problems.append("发布文件仍包含本机绝对路径: " + relative)
        if re.search(r"(?:obsidian|file)://", text, re.I):
            problems.append("发布文件仍包含本机深链或 file URI: " + relative)
        if re.search(r'''href=["'][^"']*\.md(?:[?#][^"']*)?["']''', text, re.I):
            problems.append("发布文件存在指向本地 .md 的链接: " + relative)
        if re.search(r"__[A-Z0-9_]+__", text):
            problems.append("发布文件仍包含未替换占位符: " + relative)

    if mode == "private-portable" and source_html and os.path.isfile(source_html):
        with open(source_html, encoding="utf-8") as fh:
            source = fh.read()
        if release_view(source) != release_view(html):
            problems.append("发布版视图模板与正式工作台不一致")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--notion")
    ap.add_argument("--notion-mode", choices=("incremental", "full"))
    ap.add_argument("--restore-notion-from-html")
    ap.add_argument("--replace-main-lift-history", action="store_true")
    ap.add_argument("--deploy")
    ap.add_argument("--allow-private-portable", action="store_true")
    ap.add_argument("--expect-release-mode", choices=RELEASE_MODES)
    args = ap.parse_args()
    project = os.path.abspath(args.project)

    problems = check_structure(project)
    if problems:
        fail("结构检查未通过；".join(problems))
    print("structure: PASS")
    if args.notion and args.restore_notion_from_html:
        fail("--notion 与 --restore-notion-from-html 不能同时使用")
    if args.notion_mode and not args.notion:
        fail("--notion-mode 只能与 --notion 一起使用")
    if args.replace_main_lift_history and not args.notion:
        fail("--replace-main-lift-history 只能与 --notion 一起使用")
    err = run_builder(
        project,
        args.notion,
        args.restore_notion_from_html,
        args.notion_mode,
        args.replace_main_lift_history,
    )
    if err:
        fail(err)
    print("data: PASS")
    problems = check_html(
        project,
        args.notion,
        args.restore_notion_from_html,
        args.notion_mode,
        args.replace_main_lift_history,
    )
    if problems:
        fail("HTML 检查未通过；".join(problems))
    print("html: PASS")
    problems = check_deploy(
        args.deploy,
        os.path.join(project, "健身工作台.html"),
        allow_private_portable=args.allow_private_portable,
        expected_release_mode=args.expect_release_mode,
    )
    if problems:
        fail("发布目录检查未通过；".join(problems))
    if args.deploy:
        with open(os.path.join(args.deploy, MANIFEST_NAME), encoding="utf-8") as fh:
            release_mode = json.load(fh).get("release_mode")
        print("deploy: PASS (%s)" % release_mode)
    else:
        print("deploy: PASS")
    print("FITNESS_WORKBENCH_CHECK: PASS")
    sys.exit(0)


if __name__ == "__main__":
    main()
