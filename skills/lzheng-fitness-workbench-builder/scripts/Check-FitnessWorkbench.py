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
4. 发布目录：不存在指向本地 .md 的链接。

任一失败输出 FAIL 并退出码 1，不得发布。

用法：
  python Check-FitnessWorkbench.py --project <项目根> [--notion <notion-data.json>] [--deploy <发布目录>]
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

WHITELIST_FILES = {"AGENTS.md", "README.md"}
WHITELIST_DIR_NAMES = ("训练与周期", "知识库入口", "训练复盘与状态", "工作台与工具", "历史与治理")


def run_utf8(command):
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    return subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)


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


def run_builder(project, notion, restore_notion_from_html=None):
    cmd = [PY, os.path.join(SCRIPT_DIR, "Build-FitnessWorkbenchData.py"), "--project", project, "--check-only"]
    if notion and os.path.isfile(notion):
        cmd += ["--notion", notion]
    if restore_notion_from_html and os.path.isfile(restore_notion_from_html):
        cmd += ["--restore-notion-from-html", restore_notion_from_html]
    out = run_utf8(cmd)
    if out.returncode != 0 or "FITNESS_WORKBENCH_DATA: PASS" not in out.stdout:
        return "数据校验未通过:\n" + (out.stdout + out.stderr).strip()
    return None


def load_generated_data(project, notion, restore_notion_from_html=None):
    cmd = [PY, os.path.join(SCRIPT_DIR, "Build-FitnessWorkbenchData.py"), "--project", project, "--check-only", "--out", "-"]
    if notion and os.path.isfile(notion):
        cmd += ["--notion", notion]
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


def check_html(project, notion=None, restore_notion_from_html=None):
    problems = []
    html_path = os.path.join(project, "健身工作台.html")
    if not os.path.isfile(html_path):
        return ["缺少根目录健身工作台.html"]
    with open(html_path, encoding="utf-8") as fh:
        html = fh.read()
    blocks = re.findall(r'<script id="workbench-data" type="application/json">([\s\S]*?)</script>', html)
    if len(blocks) != 1:
        problems.append("数据块数量异常: %d" % len(blocks))
        return problems
    try:
        data = json.loads(blocks[0])
    except Exception as e:
        problems.append("数据块 JSON 解析失败: %s" % e)
        return problems
    generated = load_generated_data(project, notion, restore_notion_from_html)
    if generated is None:
        problems.append("无法生成用于比对的最新数据")
    else:
        if normalize_generated(data) != normalize_generated(generated):
            problems.append("正式 HTML 数据块不是最新生成结果")
    if data.get("schema") != 6:
        problems.append("schema 必须为 6: %s" % data.get("schema"))
    data_end = html.find("</script>", html.find('id="workbench-data"'))
    view_source = html[data_end + len("</script>"):] if data_end >= 0 else html
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


def check_deploy(deploy_dir, source_html=None):
    if not deploy_dir:
        return []
    problems = []
    idx = os.path.join(deploy_dir, "index.html")
    if not os.path.isfile(idx):
        return ["发布目录缺少 index.html"]
    with open(idx, encoding="utf-8") as fh:
        html = fh.read()
    if re.search(r'href="[^"]*\.md"', html):
        problems.append("发布目录存在指向本地 .md 的链接")
    if re.search(r'''(?m)(?:^|["'`\s(])([A-Za-z]:[\\/])''', html):
        problems.append("发布目录仍包含本机绝对路径")
    blocks = re.findall(r'<script id="workbench-data" type="application/json">([\s\S]*?)</script>', html)
    if len(blocks) != 1:
        problems.append("发布目录 workbench-data 数量异常")
    elif re.search(r"obsidian://open\?path=", blocks[0], re.I):
        problems.append("发布数据仍包含本机 Obsidian 深链")
    else:
        try:
            deploy_data = json.loads(blocks[0])
            plan_target = resolve_project_entry(deploy_dir, deploy_data.get("meta", {}).get("plan_href"))
            if not plan_target or not os.path.isfile(plan_target):
                problems.append("发布目录缺少完整计划 HTML")
            documents = deploy_data.get("documents", {})
            for key, label in (("review_index", "训练复盘索引"), ("status_index", "状态档案索引")):
                document = documents.get(key) if isinstance(documents, dict) else None
                if not isinstance(document, dict) or not document.get("content_markdown"):
                    problems.append("发布目录缺少内置" + label)
        except json.JSONDecodeError:
            problems.append("发布目录 workbench-data 无法解析")
    if re.search(r"__[A-Z0-9_]+__", html):
        problems.append("发布目录仍包含未替换占位符")
    if source_html and os.path.isfile(source_html):
        with open(source_html, encoding="utf-8") as fh:
            source = fh.read()
        block_pattern = r'(<script id="workbench-data" type="application/json">)[\s\S]*?(</script>)'
        source_view = re.sub(block_pattern, r"\1{}\2", source, count=1)
        deploy_view = re.sub(block_pattern, r"\1{}\2", html, count=1)
        if source_view != deploy_view:
            problems.append("发布版视图模板与正式工作台不一致")
    for rel in extract_asset_paths(html):
        target = resolve_project_entry(deploy_dir, rel)
        if not target or not os.path.isfile(target):
            problems.append("发布目录缺少页面资源: " + rel)
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--notion")
    ap.add_argument("--restore-notion-from-html")
    ap.add_argument("--deploy")
    args = ap.parse_args()
    project = os.path.abspath(args.project)

    problems = check_structure(project)
    if problems:
        fail("结构检查未通过；".join(problems))
    print("structure: PASS")
    if args.notion and args.restore_notion_from_html:
        fail("--notion 与 --restore-notion-from-html 不能同时使用")
    err = run_builder(project, args.notion, args.restore_notion_from_html)
    if err:
        fail(err)
    print("data: PASS")
    problems = check_html(project, args.notion, args.restore_notion_from_html)
    if problems:
        fail("HTML 检查未通过；".join(problems))
    print("html: PASS")
    problems = check_deploy(args.deploy, os.path.join(project, "健身工作台.html"))
    if problems:
        fail("发布目录检查未通过；".join(problems))
    print("deploy: PASS")
    print("FITNESS_WORKBENCH_CHECK: PASS")
    sys.exit(0)


if __name__ == "__main__":
    main()
