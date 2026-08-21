#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Initialize a portable fitness workbench project and run its build gates."""

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from importlib.machinery import SourceFileLoader


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
ASSET_DIR = SKILL_DIR / "assets"
ADAPTER = SourceFileLoader("plan_contract_adapter", str(SCRIPT_DIR / "Adapt-PlanContract.py")).load_module()


def fail(message):
    raise SystemExit("FITNESS_WORKBENCH_INIT: FAIL\n- " + message)


def write_text(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip() + "\n", encoding="utf-8")


def replace_tokens(value, tokens):
    if isinstance(value, dict):
        return {key: replace_tokens(item, tokens) for key, item in value.items()}
    if isinstance(value, list):
        return [replace_tokens(item, tokens) for item in value]
    if isinstance(value, str):
        for key, replacement in tokens.items():
            value = value.replace(key, replacement)
    return value


def safe_brand(value):
    cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff _-]", "", value or "").strip()
    if not cleaned:
        fail("品牌短名不能为空")
    return cleaned[:16]


def run_checked(command):
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    if result.stdout:
        print(result.stdout.rstrip())
    if result.returncode != 0:
        if result.stderr:
            print(result.stderr.rstrip(), file=sys.stderr)
        fail("命令执行失败: " + " ".join(str(x) for x in command))


def plan_filename(source):
    if not source:
        return "匿名工作台示例计划-v01.json"
    match = re.search(r"-v(\d+)\.json$", source.name, re.I)
    version = match.group(1) if match else "01"
    return "个人训练计划-v%s.json" % version


def plan_title(plan, fallback):
    return str(plan.get("plan", {}).get("title") or fallback)


def render_plan_html(plan):
    title = plan_title(plan, "个人训练计划")
    goal = str(plan.get("plan", {}).get("goal") or "待补充")
    frequency = str(plan.get("plan", {}).get("frequency") or "待补充")
    return """<!DOCTYPE html>
<html lang=\"zh-CN\"><head><meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>{title}</title><style>body{{font-family:system-ui,'Microsoft YaHei',sans-serif;max-width:860px;margin:48px auto;padding:0 24px;line-height:1.7;color:#191919}}.card{{border:1px solid #ddd;border-radius:18px;padding:24px;background:#fafafa}}small{{color:#777}}</style></head>
<body><h1>{title}</h1><div class=\"card\"><p><b>目标：</b>{goal}</p><p><b>频率：</b>{frequency}</p><small>这是工作台计划入口。完整结构以同名 JSON 为主源。</small></div></body></html>""".format(
        title=title, goal=goal, frequency=frequency
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--brand", default="TRAIN")
    parser.add_argument("--athlete", default="使用者")
    parser.add_argument("--title", default="健身工作台")
    parser.add_argument("--start-date", help="周期所在周的任意日期，YYYY-MM-DD；默认今天")
    parser.add_argument("--plan", help="可选：用户自己的版本化计划 JSON")
    parser.add_argument("--notion", help="可选：用户自己的 notion-data.json")
    parser.add_argument("--demo-data", action="store_true", help="使用匿名 Notion 示例数据测试界面")
    parser.add_argument("--background-image", help="可选：首次初始化时使用的 PNG、JPEG 或 WebP 背景")
    parser.add_argument("--background-video", help="可选：首次初始化时使用的 MP4 动态背景；必须同时提供图片兜底")
    parser.add_argument("--background-desktop-position", help="可选桌面取景，例如 '60%% center'")
    parser.add_argument("--background-mobile-position", help="可选手机取景，例如 '66%% center'")
    args = parser.parse_args()

    if args.background_video and not args.background_image:
        fail("使用动态背景时必须同时提供 --background-image 静态兜底")
    if (args.background_desktop_position or args.background_mobile_position) and not args.background_image:
        fail("调整背景取景时必须同时提供 --background-image")

    target = Path(args.target).resolve()
    if target.exists() and any(target.iterdir()):
        fail("目标目录不是空目录，拒绝覆盖: " + str(target))
    target.mkdir(parents=True, exist_ok=True)

    try:
        selected = dt.date.fromisoformat(args.start_date) if args.start_date else dt.date.today()
    except ValueError:
        fail("start-date 必须是 YYYY-MM-DD")
    week_start = selected - dt.timedelta(days=selected.weekday())
    period_end = week_start + dt.timedelta(days=55)
    dates = [week_start + dt.timedelta(days=index) for index in range(7)]
    tokens = {
        "__ATHLETE__": args.athlete,
        "__TODAY_ISO__": dt.date.today().isoformat(),
        "__DATE_MON__": dates[0].strftime("%m-%d"),
        "__DATE_TUE__": dates[1].strftime("%m-%d"),
        "__DATE_WED__": dates[2].strftime("%m-%d"),
        "__DATE_THU__": dates[3].strftime("%m-%d"),
        "__DATE_FRI__": dates[4].strftime("%m-%d"),
        "__DATE_SAT__": dates[5].strftime("%m-%d"),
        "__DATE_SUN__": dates[6].strftime("%m-%d"),
    }

    fixed_dirs = [
        "训练与周期/当前周期",
        "训练与周期/力量周期",
        "知识库入口",
        "训练复盘与状态/训练复盘",
        "训练复盘与状态/当前执行基准",
        "训练复盘与状态/状态档案",
        "工作台与工具/健身工作台开发/界面素材",
        "历史与治理",
    ]
    for relative in fixed_dirs:
        (target / relative).mkdir(parents=True, exist_ok=True)

    template = (ASSET_DIR / "workbench-template.html").read_text(encoding="utf-8")
    brand = safe_brand(args.brand)
    template = template.replace("__FWB_BRAND__", brand)
    template = template.replace("<title>健身工作台</title>", "<title>%s</title>" % args.title)
    write_text(target / "健身工作台.html", template)

    image_target = target / "工作台与工具/健身工作台开发/界面素材"
    for source in sorted((ASSET_DIR / "backgrounds").iterdir()):
        if source.is_file() and source.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".mp4"):
            shutil.copy2(source, image_target / source.name)

    supplied_plan = Path(args.plan).resolve() if args.plan else None
    if supplied_plan and not supplied_plan.is_file():
        fail("计划 JSON 不存在: " + str(supplied_plan))
    if supplied_plan:
        plan = json.loads(supplied_plan.read_text(encoding="utf-8-sig"))
        if ADAPTER.is_plan_contract(plan):
            plan = ADAPTER.adapt(plan, selected.isoformat())
    else:
        plan = json.loads((ASSET_DIR / "examples/plan-template-v01.json").read_text(encoding="utf-8"))
        plan = replace_tokens(plan, tokens)
    period_end = week_start + dt.timedelta(days=int(plan.get("plan", {}).get("weeks", 8)) * 7 - 1)
    filename = plan_filename(supplied_plan)
    plan_path = target / "训练与周期/当前周期" / filename
    write_text(plan_path, json.dumps(plan, ensure_ascii=False, indent=2))
    html_plan = plan_path.with_suffix(".html")
    write_text(html_plan, render_plan_html(plan))

    version_match = re.search(r"-v(\d+)\.json$", filename)
    version = "v" + version_match.group(1)
    title = plan_title(plan, filename[:-5])
    baseline = """---
status: 执行中
period: {start} 至 {end}
source_plan: [[训练与周期/当前周期/{stem}|{title}]]
---

# 当前训练执行基准

- 当前版本：{version}
- 当前周次：W1
- 数据边界：初始化文件只负责建立系统；正式训练重量以用户确认后的计划 JSON 为准。
""".format(
        start=week_start.isoformat(),
        end=period_end.isoformat(),
        stem=plan_path.stem,
        title=title,
        version=version,
    )
    write_text(target / "训练复盘与状态/当前执行基准/当前训练执行基准.md", baseline)

    review_date = dt.date.today().isoformat()
    review_stem = review_date + "-W1-工作台初始化记录"
    review = """---
date: {date}
week: W1
day: 系统初始化
status: 待补充
workbench_title: W1 工作台初始化记录
workbench_lead: 工作台结构已创建，等待首个真实训练记录
workbench_points:
  - 当前计划已接入
  - 执行基准已建立
  - Notion 数据可选
workbench_decision: 完成首练后用真实复盘替换初始化记录
---

# W1 工作台初始化记录

本文件不是训练完成记录，只用于让新工作台建立可追溯的初始周次。
""".format(date=review_date)
    write_text(target / "训练复盘与状态/训练复盘" / (review_stem + ".md"), review)
    index = """# 训练复盘索引

| 日期 | 周次 | 训练日 | 主判断 | 状态 | 文件 |
| --- | --- | --- | --- | --- | --- |
| {date} | W1 | 系统初始化 | 等待首个真实训练记录 | 待补充 | [[{stem}]] |
""".format(date=review_date, stem=review_stem)
    write_text(target / "训练复盘与状态/训练复盘/INDEX.md", index)
    status_index = """# 状态档案索引

当前尚未写入个人状态档案。正式制定计划前，记录会影响训练安排的目标、经验、器械、时间、恢复和健康限制。
"""
    write_text(target / "训练复盘与状态/状态档案/INDEX.md", status_index)

    root_agents = """# 个人训练系统工作台规则

- 动态数据只写入 `健身工作台.html` 的唯一 `workbench-data` 数据块。
- 当前计划使用 `训练与周期/当前周期` 中版本号最大的 `*-vNN.json`。
- 完整计划、力量周期、复盘和接回卡优先写入本知识库的固定目录，不在工作目录散落新文件。
- 训练重量、完成状态和复盘必须可追溯；未知时显示待确认。
- 完整计划 HTML 使用相对链接，可在普通文件夹或 Obsidian 仓库中打开；复盘索引链接到真实 Markdown。
- 临时文件、发布副本和浏览器缓存不得放入项目根目录。
"""
    root_readme = """# 个人训练系统

本目录由 `lzheng-fitness-workbench-builder` 创建。日常只打开 `健身工作台.html`；计划、复盘和执行基准是页面事实来源。

内置匿名数据只用于验证系统。正式使用前应完成建档和动作重量校准；正式计划可以直接使用 lzheng-fitness-plan 生成的 plan_contract，由构建器自动接入。

正式产物统一归档：完整计划进入 `训练与周期/当前周期`，专项力量周期进入 `训练与周期/力量周期`，训练复盘进入 `训练复盘与状态/训练复盘`，状态快照和接回卡进入 `训练复盘与状态/状态档案`。
"""
    route = """# 健身工作台

- 查看：打开 [[健身工作台.html|健身工作台]]。
- 更新计划：替换 `训练与周期/当前周期` 的版本化 JSON，并重新构建数据块。
- 训练后：写入复盘文件并更新 `训练复盘与状态/训练复盘/INDEX.md`。
- 动态训练和体重：可通过 `notion-data.json` 接入；缺失时页面显示待同步。
"""
    write_text(target / "AGENTS.md", root_agents)
    write_text(target / "README.md", root_readme)
    write_text(target / "健身工作台.md", route)

    notion_path = None
    if args.notion and args.demo_data:
        fail("--notion 与 --demo-data 不能同时使用")
    if args.notion:
        source = Path(args.notion).resolve()
        if not source.is_file():
            fail("Notion JSON 不存在: " + str(source))
        try:
            raw = json.loads(source.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            fail("Notion JSON 无法解析: " + str(exc))
        raw = replace_tokens(raw, tokens)
        notion_path = target / "工作台与工具/健身工作台开发/notion-data.json"
        write_text(notion_path, json.dumps(raw, ensure_ascii=False, indent=2))
    elif args.demo_data:
        raw = json.loads((ASSET_DIR / "examples/notion-data.example.json").read_text(encoding="utf-8"))
        raw = replace_tokens(raw, tokens)
        notion_path = target / "工作台与工具/健身工作台开发/notion-data.json"
        write_text(notion_path, json.dumps(raw, ensure_ascii=False, indent=2))

    builder = [sys.executable, str(SCRIPT_DIR / "Build-FitnessWorkbenchData.py"), "--project", str(target), "--apply"]
    checker = [sys.executable, str(SCRIPT_DIR / "Check-FitnessWorkbench.py"), "--project", str(target)]
    if notion_path:
        builder += ["--notion", str(notion_path)]
        checker += ["--notion", str(notion_path)]
    run_checked(builder)
    run_checked(checker)

    if args.background_image:
        replacement = [
            sys.executable,
            str(SCRIPT_DIR / "Replace-FitnessWorkbenchBackground.py"),
            "--project",
            str(target),
            "--image",
            args.background_image,
        ]
        if args.background_video:
            replacement += ["--video", args.background_video]
        if args.background_desktop_position:
            replacement += ["--desktop-position", args.background_desktop_position]
        if args.background_mobile_position:
            replacement += ["--mobile-position", args.background_mobile_position]
        run_checked(replacement)

    print("FITNESS_WORKBENCH_INIT: PASS")
    print("project: " + str(target))
    print("workbench: " + str(target / "健身工作台.html"))
    if not supplied_plan:
        print("mode: anonymous demo plan; replace before real training")


if __name__ == "__main__":
    main()
