#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build-FitnessWorkbenchData.py — 健身工作台 workbench-data 生成器与校验器（P0）
============================================================
职责：从固定输入（当前计划 JSON、执行基准、复盘索引、可核验的 Notion 结果）
生成并校验 workbench-data 数据块，然后原子替换 健身工作台.html 中的唯一数据块。
本脚本不修改页面视图；校验不通过时不得替换。

用法：
  python Build-FitnessWorkbenchData.py --project <训练项目根目录> [--notion <notion-data.json> --notion-mode incremental|full] [--check-only] [--out <workbench-data.json>]

约定：
- 当前周期 JSON：自动发现 <project>/训练与周期/当前周期 下版本号最大的 *-vNN.json。
- 复盘索引：<project>/训练复盘与状态/训练复盘/INDEX.md
- 执行基准：<project>/训练复盘与状态/当前执行基准/ 下的 md（作为约束说明，不解析数据）
- Notion 结果：--notion 指定 JSON；历史按稳定键合并，查询时间与本地构建时间分离。
- 输出 schema=6；失败保护：无法核验的字段用 null/空态，绝不继承旧值冒充新数据。
"""
import argparse
import datetime as dt
import json
import math
import os
import re
import sys
import uuid
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

SCHEMA_VERSION = 6
DEFAULT_CALENDAR = {"1": "上肢A", "2": "腿B", "4": "上肢B", "6": "腿A"}
DEFAULT_WEEKDAY = {"上肢A": "周一", "腿B": "周二", "上肢B": "周四", "腿A": "周六"}
MAX_NOTION_AGE_DAYS = 2

WEEKDAY_CN = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"]

NOTION_SYNC_MODES = {"incremental", "full"}
MAIN_LIFT_ALIASES = {
    "负重引体": "负重引体",
    "负重引体向上": "负重引体",
    "卧推": "卧推",
    "杠铃卧推": "卧推",
    "深蹲": "深蹲",
    "杠铃深蹲": "深蹲",
    "硬拉": "硬拉",
    "杠铃硬拉": "硬拉",
}
MAIN_LIFT_NAMES = ("负重引体", "卧推", "深蹲", "硬拉")
NOTION_HISTORY_KEYS = {
    "bodyweight": ("date",),
    "sessions": ("date", "day"),
    "main_lifts": ("name", "date"),
    "activity": ("date",),
}
NOTION_MONOTONIC_FIELDS = (
    "source_queried_at",
    "snapshot_generated_at",
    "latest_training_record_date",
    "latest_bodyweight_record_date",
)


class NotionSyncConflict(ValueError):
    """Raised when a new snapshot would silently rewrite verified history."""


def canonical_main_lift_name(name):
    """Normalize portable aliases without turning accessory variants into main lifts."""
    text = str(name or "").strip()
    return MAIN_LIFT_ALIASES.get(text, text)


def normalized_session_date(value, default_year=None):
    """Return a full ISO date; legacy MM-DD requires a metadata-derived year."""
    text = str(value or "").strip()
    full = re.match(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ].*)?$", text)
    if full:
        try:
            return dt.date(int(full.group(1)), int(full.group(2)), int(full.group(3))).isoformat()
        except ValueError:
            return text
    legacy = re.match(r"^(\d{2})-(\d{2})$", text)
    if legacy and default_year:
        try:
            return dt.date(int(default_year), int(legacy.group(1)), int(legacy.group(2))).isoformat()
        except ValueError:
            return text
    return text


def normalized_full_date(value):
    text = str(value or "").strip()
    match = re.match(r"^(\d{4}-\d{2}-\d{2})(?:[T ].*)?$", text)
    return match.group(1) if match else text


def _year_from_temporal(value):
    match = re.match(r"^(\d{4})[-/]", str(value or "").strip())
    return int(match.group(1)) if match else None


def history_default_year(notion, field):
    """Choose the record-domain year before falling back to snapshot/query metadata."""
    domain_field = "latest_bodyweight_record_date" if field == "bodyweight" else "latest_training_record_date"
    for candidate in (
        notion.get(domain_field),
        notion.get("source_queried_at"),
        notion.get("snapshot_generated_at"),
        notion.get("last_sync"),
    ):
        year = _year_from_temporal(candidate)
        if year:
            return year
    return None


def normalized_day_label(value):
    return re.sub(r"[\s　]+", "", str(value or "").strip()).replace("（", "(").replace("）", ")")


def _meaningful(value):
    return value not in (None, "", [], {})


def _same_value(left, right):
    if isinstance(left, (int, float)) and not isinstance(left, bool) and isinstance(right, (int, float)) and not isinstance(right, bool):
        return float(left) == float(right)
    return left == right


def _is_iso_date(value):
    try:
        return dt.date.fromisoformat(str(value)).isoformat() == str(value)
    except ValueError:
        return False


def _history_key(field, row):
    if field == "bodyweight":
        key = (normalized_full_date(row.get("date")),)
    elif field == "sessions":
        key = (normalized_full_date(row.get("date")), normalized_day_label(row.get("day")))
    elif field == "main_lifts":
        key = (canonical_main_lift_name(row.get("name")), normalized_full_date(row.get("date")))
    elif field == "activity":
        key = (normalized_full_date(row.get("date")),)
    else:
        raise NotionSyncConflict("未知历史字段: %s" % field)
    if any(value in (None, "") for value in key):
        raise NotionSyncConflict("%s 记录缺少稳定键 %s: %r" % (field, "+".join(NOTION_HISTORY_KEYS[field]), row))
    record_date = key[-1] if field == "main_lifts" else key[0]
    if field in ("bodyweight", "sessions", "main_lifts", "activity") and not _is_iso_date(record_date):
        raise NotionSyncConflict("%s 记录日期必须是 YYYY-MM-DD；旧 MM-DD 需要查询元数据提供默认年份: %r" % (field, row))
    return key


def _merge_compatible_record(field, key, previous, incoming):
    """Allow enrichment, but reject changing an already verified non-empty value."""
    key_fields = set(NOTION_HISTORY_KEYS[field])
    result = dict(previous)
    for name, value in incoming.items():
        old = result.get(name)
        if name not in key_fields and _meaningful(old) and _meaningful(value) and not _same_value(old, value):
            correction_hint = "；权威纠错需使用 full + --replace-main-lift-history" if field == "main_lifts" else ""
            raise NotionSyncConflict(
                "%s 历史发生冲突：稳定键 %s 的 %s 已核验为 %r，本次为 %r%s"
                % (field, key, name, old, value, correction_hint)
            )
        if _meaningful(value) or name not in result:
            result[name] = value
    return result


def _normalize_history_row(field, row, default_year=None):
    item = dict(row)
    if field == "bodyweight":
        item["date"] = normalized_session_date(item.get("date"), default_year)
    elif field == "sessions":
        item["date"] = normalized_session_date(item.get("date"), default_year)
        item["day"] = normalized_day_label(item.get("day"))
    elif field == "main_lifts":
        item["name"] = canonical_main_lift_name(item.get("name"))
        item["date"] = normalized_session_date(item.get("date"), default_year)
        if isinstance(item.get("week"), str) and item["week"].isdigit():
            item["week"] = int(item["week"])
    elif field == "activity":
        item["date"] = normalized_session_date(item.get("date"), default_year)
    return item


def _index_history(field, rows, default_year=None):
    indexed = {}
    for raw in rows or []:
        if not isinstance(raw, dict):
            raise NotionSyncConflict("%s 历史包含非对象记录" % field)
        row = _normalize_history_row(field, raw, default_year)
        key = _history_key(field, row)
        indexed[key] = _merge_compatible_record(field, key, indexed[key], row) if key in indexed else row
    return indexed


def _history_sort_key(field, item):
    key, _row = item
    if field == "main_lifts":
        return (MAIN_LIFT_NAMES.index(key[0]) if key[0] in MAIN_LIFT_NAMES else len(MAIN_LIFT_NAMES), str(key[1]))
    return tuple(str(value) for value in key)


def _normalize_latest_by_exercise(raw):
    latest = {}
    for name, value in (raw or {}).items():
        canonical = canonical_main_lift_name(name)
        if canonical in latest and _meaningful(latest[canonical]) and _meaningful(value) and latest[canonical] != value:
            raise NotionSyncConflict("latest_by_exercise 别名归一化后发生冲突: %s" % canonical)
        latest[canonical] = value
    return latest


def normalize_notion_payload(notion):
    if not isinstance(notion, dict):
        return notion
    value = dict(notion)
    source_queried_at = value.get("source_queried_at") or value.get("last_sync")
    if source_queried_at:
        value["source_queried_at"] = source_queried_at
        # Compatibility alias for schema-6 views that still render last_sync.
        value["last_sync"] = source_queried_at
    value["latest_by_exercise"] = _normalize_latest_by_exercise(value.get("latest_by_exercise"))
    for field in NOTION_HISTORY_KEYS:
        indexed = _index_history(field, value.get(field) or [], history_default_year(value, field))
        value[field] = [row for _key, row in sorted(indexed.items(), key=lambda item: _history_sort_key(field, item))]
    return value


def resolve_notion_mode(cli_mode, notion):
    payload_mode = (notion or {}).get("sync_mode") if isinstance(notion, dict) else None
    if payload_mode is not None:
        payload_mode = str(payload_mode).strip().lower()
        if payload_mode not in NOTION_SYNC_MODES:
            raise NotionSyncConflict("sync_mode 必须是 incremental 或 full")
    if cli_mode and payload_mode and cli_mode != payload_mode:
        raise NotionSyncConflict("--notion-mode 与 JSON sync_mode 不一致")
    mode = cli_mode or payload_mode
    return (mode or "incremental"), bool(mode)


def _comparable_time(value):
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(text)
        if parsed.tzinfo:
            parsed = parsed.astimezone(dt.timezone.utc).replace(tzinfo=None)
        return parsed
    except ValueError:
        for pattern in ("%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y/%m/%d"):
            try:
                return dt.datetime.strptime(text, pattern)
            except ValueError:
                continue
        try:
            return dt.datetime.combine(dt.date.fromisoformat(text[:10]), dt.time.min)
        except ValueError:
            return None


def _reject_metadata_regression(previous, incoming):
    for field in NOTION_MONOTONIC_FIELDS:
        old = _comparable_time(previous.get(field))
        new = _comparable_time(incoming.get(field))
        if old and new and new < old:
            raise NotionSyncConflict("%s 倒退：已有 %s，本次 %s" % (field, previous.get(field), incoming.get(field)))


def merge_notion_history(previous, incoming, mode="incremental", replace_main_lifts=False):
    """Merge verified histories by stable key; only full+replace may rewrite main-lift history."""
    if mode not in NOTION_SYNC_MODES:
        raise NotionSyncConflict("Notion 输入模式必须是 incremental 或 full")
    if replace_main_lifts and mode != "full":
        raise NotionSyncConflict("--replace-main-lift-history 只允许用于 full 输入")
    previous = normalize_notion_payload(previous) or {}
    incoming = normalize_notion_payload(incoming) or {}
    _reject_metadata_regression(previous, incoming)

    merged = dict(previous)
    for name, value in incoming.items():
        if name in NOTION_HISTORY_KEYS or name == "latest_by_exercise":
            continue
        if _meaningful(value) or name not in merged:
            merged[name] = value
    merged["sync_mode"] = mode

    for field in NOTION_HISTORY_KEYS:
        old_rows = _index_history(field, previous.get(field) or [])
        new_rows = _index_history(field, incoming.get(field) or [])
        if field == "main_lifts" and replace_main_lifts:
            combined = new_rows
        else:
            if mode == "full":
                missing = sorted(set(old_rows) - set(new_rows), key=str)
                if missing:
                    raise NotionSyncConflict("full 输入缺少既有 %s 稳定键，拒绝缩短历史: %s" % (field, missing))
            combined = dict(old_rows)
            for key, row in new_rows.items():
                combined[key] = _merge_compatible_record(field, key, combined[key], row) if key in combined else row
        merged[field] = [row for _key, row in sorted(combined.items(), key=lambda item: _history_sort_key(field, item))]

    previous_latest = previous.get("latest_by_exercise") or {}
    incoming_latest = incoming.get("latest_by_exercise") or {}
    merged["latest_by_exercise"] = dict(incoming_latest) if mode == "full" else {**previous_latest, **incoming_latest}
    return normalize_notion_payload(merged)


def fail(msg):
    print("FITNESS_WORKBENCH_DATA: FAIL")
    print("- " + msg)
    sys.exit(1)


def warn(msg):
    print("- warning: " + msg)


def find_active_plan_json(project_root):
    cur = os.path.join(project_root, "训练与周期", "当前周期")
    if not os.path.isdir(cur):
        fail("当前周期目录不存在: " + cur)
    candidates = []
    for name in os.listdir(cur):
        m = re.match(r"^(.*)-v(\d+)\.json$", name)
        if m:
            candidates.append((int(m.group(2)), name))
    if not candidates:
        fail("当前周期目录没有版本化 JSON 计划: " + cur)
    candidates.sort()
    return os.path.join(cur, candidates[-1][1]), candidates[-1][1]


def find_execution_baseline(project_root, source_version):
    base_dir = os.path.join(project_root, "训练复盘与状态", "当前执行基准")
    if not os.path.isdir(base_dir):
        fail("执行基准目录不存在: " + base_dir)
    mds = sorted(f for f in os.listdir(base_dir) if f.endswith(".md"))
    if not mds:
        fail("执行基准目录没有 md 文件: " + base_dir)
    ranked = []
    for name in mds:
        path = os.path.join(base_dir, name)
        with open(path, encoding="utf-8-sig") as fh:
            text = fh.read()
        score = 0
        if re.search(r"source_plan:.*-" + re.escape(source_version) + r"(?:\||\]])", text):
            score += 8
        if re.search(r"^status:\s*执行中\s*$", text, re.M):
            score += 4
        if re.search(r"^period:\s*\d{4}-\d{2}-\d{2}\s*至\s*\d{4}-\d{2}-\d{2}\s*$", text, re.M):
            score += 2
        ranked.append((score, path, text))
    ranked.sort(key=lambda x: (x[0], x[1]), reverse=True)
    score, path, text = ranked[0]
    if score < 8:
        fail("没有找到与当前计划 %s 对应的执行基准" % source_version)
    period = re.search(r"^period:\s*(\d{4}-\d{2}-\d{2})\s*至\s*(\d{4}-\d{2}-\d{2})\s*$", text, re.M)
    version = re.search(r"source_plan:.*-v(\d+)", text)
    period_start = dt.date.fromisoformat(period.group(1)) if period else None
    week_start = period_start - dt.timedelta(days=period_start.weekday()) if period_start else None
    return {
        "path": path,
        "file": os.path.basename(path),
        "source_version": "v" + version.group(1) if version else None,
        "period_start": period_start.isoformat() if period_start else None,
        "week_start": week_start.isoformat() if week_start else None,
        "period_end": period.group(2) if period else None,
    }


def parse_review_index(project_root):
    idx = os.path.join(project_root, "训练复盘与状态", "训练复盘", "INDEX.md")
    if not os.path.isfile(idx):
        fail("复盘索引不存在: " + idx)
    rows = []
    with open(idx, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line.startswith("|"):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) < 6 or not re.match(r"^\d{4}-\d{2}-\d{2}$", cells[0]):
                continue
            rows.append({
                "date": cells[0][5:],          # MM-DD
                "full_date": cells[0],         # YYYY-MM-DD
                "week": cells[1],              # W1/W2...
                "day": cells[2],
                "verdict": cells[3],
                "status": cells[4],
                "file": review_file_from_cell(cells[5]),
            })
    if not rows:
        fail("复盘索引没有可解析的记录行")
    return rows


def review_file_from_cell(cell):
    m = re.search(r"\[\[([^\]|#]+)", cell or "")
    return m.group(1).strip() if m else None


def parse_week(week_str):
    m = re.search(r"W(\d+)", week_str)
    return int(m.group(1)) if m else None


def schedule_contract_snapshot(plan_json, plan_start, today):
    """提取当前排程事实；训练标签定周次，全部有日期事件共同决定覆盖范围。"""
    training = []
    all_events = []
    weeks = set()
    missing_week_labels = []
    for item in plan_json.get("schedule", []):
        date = parse_schedule_date(str(item.get("day") or ""), plan_start)
        if date:
            all_events.append({"date": date, "type": "training" if "exercises" in item else "recovery"})
        if "exercises" not in item:
            continue
        week = parse_week(str(item.get("label") or ""))
        if week:
            weeks.add(week)
        else:
            missing_week_labels.append(str(item.get("day") or item.get("theme") or "未命名训练日"))
        normalized = str(item.get("theme") or "").replace(" ", "")
        day_key = next((key for key in DEFAULT_WEEKDAY if key in normalized), None)
        if not day_key:
            day_key = str(item.get("day_key") or item.get("title") or item.get("theme") or "训练日")
        training.append({
            "date": date,
            "day": day_key,
            "week": week,
            "exercises": item.get("exercises") or [],
        })
    dates = [dt.date.fromisoformat(item["date"]) for item in all_events if item.get("date")]
    return {
        "training": training,
        "events": all_events,
        "weeks": weeks,
        "missing_week_labels": missing_week_labels,
        "covers_today": bool(dates) and min(dates) <= today <= max(dates),
        "first_date": min(dates).isoformat() if dates else None,
        "last_date": max(dates).isoformat() if dates else None,
    }


def current_week_from_schedule(plan_json, plan_start, today):
    """排程明确覆盖今天时，以其唯一 Wn 为准，处理新周尚无训练复盘的窗口。"""
    snapshot = schedule_contract_snapshot(plan_json, plan_start, today)
    if snapshot["missing_week_labels"] or len(snapshot["weeks"]) != 1:
        return None
    if snapshot["covers_today"]:
        return next(iter(snapshot["weeks"]))
    return None


def declared_training_frequency(plan_json):
    """读取“每周 4 练”等声明；无法解析时交给其他契约，不臆测次数。"""
    value = plan_json.get("plan", {}).get("frequency")
    if isinstance(value, int):
        return value if value > 0 else None
    match = re.search(r"(\d+)\s*练", str(value or "")) or re.search(r"(\d+)", str(value or ""))
    return int(match.group(1)) if match and int(match.group(1)) > 0 else None


def schedule_day_key(item):
    explicit = normalized_day_label(item.get("day_key"))
    if explicit:
        return explicit
    text = normalized_day_label(" ".join(str(item.get(key) or "") for key in ("theme", "label", "title", "role")))
    for key in DEFAULT_WEEKDAY:
        if normalized_day_label(key) in text:
            return normalized_day_label(key)
    match = re.search(r"(上肢|下肢|腿|推|拉)([A-DＡ-Ｄ])", text, re.I)
    if match:
        suffix = chr(ord(match.group(2).upper()) - 0xFEE0) if "Ａ" <= match.group(2).upper() <= "Ｄ" else match.group(2).upper()
        return match.group(1) + suffix
    return None


def _lift_from_text(value):
    text = normalized_day_label(value)
    for alias in sorted(MAIN_LIFT_ALIASES, key=len, reverse=True):
        if text.startswith(normalized_day_label(alias)):
            return MAIN_LIFT_ALIASES[alias]
    return None


def _segment_mentions_lift(segment, lift):
    text = normalized_day_label(segment)
    return any(normalized_day_label(alias) in text for alias, canonical in MAIN_LIFT_ALIASES.items() if canonical == lift)


def build_main_lift_day_map(plan_json):
    """Resolve main-lift duties from the plan instead of assuming one global split."""
    explicit = plan_json.get("main_lift_day_map")
    if not isinstance(explicit, dict):
        explicit = plan_json.get("plan", {}).get("main_lift_day_map")
    mapping = {}
    for name, day in (explicit or {}).items():
        canonical = canonical_main_lift_name(name)
        if canonical in MAIN_LIFT_NAMES and normalized_day_label(day):
            mapping[canonical] = normalized_day_label(day)

    role_candidates = {name: set() for name in MAIN_LIFT_NAMES}
    exercise_candidates = {name: set() for name in MAIN_LIFT_NAMES}
    known_days = set()
    for item in plan_json.get("schedule", []):
        if "exercises" not in item:
            continue
        day = schedule_day_key(item)
        if not day:
            continue
        known_days.add(day)
        segments = re.split(r"[/／;；,，+＋]", str(item.get("role") or ""))
        for lift in MAIN_LIFT_NAMES:
            for segment in segments:
                normalized = normalized_day_label(segment)
                is_strength_duty = any(marker in normalized for marker in ("强度", "主项", "暴露", "重硬拉", "硬拉日"))
                is_secondary = any(marker in normalized for marker in ("容量", "技术", "辅助"))
                if is_strength_duty and not is_secondary and _segment_mentions_lift(segment, lift):
                    role_candidates[lift].add(day)
        for exercise in item.get("exercises") or []:
            if not isinstance(exercise, dict):
                continue
            lift = canonical_main_lift_name(exercise.get("name"))
            if lift in MAIN_LIFT_NAMES:
                exercise_candidates[lift].add(day)

    cycle_candidates = {name: set() for name in MAIN_LIFT_NAMES}
    for cycle in plan_json.get("cycles", []):
        lift = _lift_from_text(cycle.get("title"))
        if not lift:
            continue
        for header in cycle.get("headers") or []:
            normalized = normalized_day_label(header)
            if not any(marker in normalized for marker in ("强度", "主项", "硬拉日")):
                continue
            for day in known_days:
                if day in normalized:
                    cycle_candidates[lift].add(day)

    for lift in MAIN_LIFT_NAMES:
        if lift in mapping:
            continue
        preferred = role_candidates[lift] | cycle_candidates[lift]
        if len(preferred) == 1:
            mapping[lift] = next(iter(preferred))
        elif not preferred and len(exercise_candidates[lift]) == 1:
            mapping[lift] = next(iter(exercise_candidates[lift]))
    return mapping


def day_labels_match(expected, actual):
    expected = normalized_day_label(expected)
    actual = normalized_day_label(actual)
    return bool(expected and actual and (expected == actual or expected in actual))


def strength_history_validation_enabled(plan_json):
    """Respect an explicit objective first; infer only for legacy plans with a clear strength contract."""
    plan = plan_json.get("plan", {})
    objective_mode = str(plan.get("objective_mode") or "").strip().lower()
    if objective_mode:
        return objective_mode == "strength"
    tracking_flag = plan.get("main_lift_tracking", plan_json.get("main_lift_tracking"))
    if isinstance(tracking_flag, bool):
        return tracking_flag
    explicit_map = plan.get("main_lift_day_map") or plan_json.get("main_lift_day_map")
    if isinstance(explicit_map, dict) and explicit_map:
        return True
    cycle_lifts = {_lift_from_text(cycle.get("title")) for cycle in plan_json.get("cycles", []) if cycle.get("chart")}
    strength_text = " ".join(str(plan.get(key) or "") for key in ("title", "subtitle", "goal"))
    return "力量" in strength_text and bool(cycle_lifts & set(MAIN_LIFT_NAMES))


def validate_main_lift_history(notion, current_week, plan_json):
    """Verify actual strength points against the plan-declared duty mapping and executed sessions."""
    problems = []
    if not strength_history_validation_enabled(plan_json) or not notion or not notion.get("main_lifts"):
        return problems
    plan_mapping = build_main_lift_day_map(plan_json)
    sessions = {}
    for row in notion.get("sessions") or []:
        if isinstance(row, dict) and row.get("date") and row.get("day"):
            sessions.setdefault(normalized_session_date(row.get("date")), set()).add(normalized_day_label(row.get("day")))
    seen = set()
    for row in notion.get("main_lifts") or []:
        if not isinstance(row, dict):
            problems.append("主项实际记录必须是对象")
            continue
        name = canonical_main_lift_name(row.get("name"))
        week = row.get("week")
        date = normalized_full_date(row.get("date"))
        key = (name, date)
        if name not in MAIN_LIFT_NAMES:
            problems.append("主项实际记录名称无法识别: %s" % (row.get("name") or "空"))
            continue
        if key in seen:
            problems.append("主项实际记录重复: %s %s" % key)
        seen.add(key)
        if not isinstance(week, int) or week < 1:
            problems.append("主项实际记录周次非法: %s W%s" % (name, week))
        if not isinstance(row.get("value"), (int, float)) or isinstance(row.get("value"), bool):
            problems.append("主项实际记录重量非法: %s W%s" % (name, week))
        expected_day = plan_mapping.get(name)
        if not expected_day:
            problems.append("当前计划无法确定主项职责映射: %s；请在 plan.main_lift_day_map 显式声明" % name)
            continue
        actual_days = sessions.get(date, set())
        if not date or not actual_days:
            problems.append("主项实际记录缺少对应训练场次: %s W%s %s" % (name, week, date or "无日期"))
        else:
            try:
                if dt.date.fromisoformat(date) > dt.date.today():
                    problems.append("主项实际记录来自未来日期: %s W%s %s" % (name, week, date))
            except ValueError:
                problems.append("主项实际记录日期非法: %s W%s %s" % (name, week, date))
        if actual_days and not any(day_labels_match(expected_day, actual_day) for actual_day in actual_days):
            problems.append(
                "主项实际记录职责不匹配: %s W%s %s 属于%s，不是计划映射%s"
                % (name, week, date, "/".join(sorted(actual_days)), expected_day)
            )
    return problems


def relative_path(path, project_root):
    """Store project-local paths without binding the workbench to one machine."""
    return os.path.relpath(os.path.abspath(path), os.path.abspath(project_root)).replace("\\", "/")


def browser_href(path):
    """Create a browser-safe relative href for a local standalone file."""
    return quote(str(path).replace("\\", "/"), safe="/-._~")


def resolve_project_href(project_root, href):
    """Resolve a relative workbench href and reject schemes or directory traversal."""
    parsed = urlparse(str(href or ""))
    if parsed.scheme or parsed.netloc:
        return None
    decoded = unquote(parsed.path).replace("/", os.sep)
    if not decoded or os.path.isabs(decoded):
        return None
    root = os.path.abspath(project_root)
    candidate = os.path.abspath(os.path.join(root, decoded))
    try:
        if os.path.commonpath([root, candidate]) != root:
            return None
    except ValueError:
        return None
    return candidate


def build_links(project_root, previous=None, notion=None):
    """Keep Markdown targets relative; the view creates optional Obsidian links at runtime."""
    links = dict(previous or {})
    targets = {
        "review_index": os.path.join(project_root, "训练复盘与状态", "训练复盘", "INDEX.md"),
        "status_index": os.path.join(project_root, "训练复盘与状态", "状态档案", "INDEX.md"),
    }
    for key, path in targets.items():
        for suffix in ("_path", "_href", "_file"):
            links.pop(key + suffix, None)
        if os.path.isfile(path):
            links[key + "_file"] = relative_path(path, project_root)
    notion_url = (notion or {}).get("notion_url") or links.get("notion_url")
    if isinstance(notion_url, str) and notion_url.startswith(("https://", "http://")):
        links["notion_url"] = notion_url
    else:
        links.pop("notion_url", None)
    return links


def read_portable_document(path):
    """Read a local Markdown source for the workbench's built-in reader."""
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8-sig") as fh:
        return fh.read()


def build_portable_documents(project_root):
    """Embed primary Markdown indexes so reading never depends on Obsidian."""
    targets = {
        "review_index": ("训练复盘索引", os.path.join(project_root, "训练复盘与状态", "训练复盘", "INDEX.md")),
        "status_index": ("状态档案", os.path.join(project_root, "训练复盘与状态", "状态档案", "INDEX.md")),
    }
    documents = {}
    for key, (title, path) in targets.items():
        content = read_portable_document(path)
        if content is None:
            continue
        documents[key] = {
            "title": title,
            "file_path": relative_path(path, project_root),
            "content_markdown": content,
        }
    return documents


def build_meta(plan_json, plan_file_name, current_week, baseline, project_root):
    plan = plan_json.get("plan", {})
    plan_rel = "训练与周期/当前周期/" + plan_file_name.replace(".json", ".html")
    plan_abs = os.path.join(project_root, plan_rel.replace("/", os.sep))
    return {
        "title": plan.get("title", "健身计划"),
        "source_version": "v" + re.search(r"-v(\d+)\.json$", plan_file_name).group(1),
        "updated_at": dt.date.today().isoformat(),
        "current_week": current_week,
        "total_weeks": plan.get("weeks", 8),
        "test_week": plan.get("weeks", 8),
        "phase": phase_for_week(plan_json.get("phases", []), current_week),
        "plan_start": baseline.get("week_start") or baseline.get("period_start"),
        "plan_end": baseline.get("period_end"),
        "plan_file": plan_rel,
        "plan_href": browser_href(plan_rel),
        "baseline_file": baseline.get("file"),
        "baseline_version": baseline.get("source_version"),
        "week_note": (plan.get("baseline") or plan.get("constraints") or "")[:180],
        "goal": plan.get("goal"),
        "objective_mode": plan.get("objective_mode", "general_fitness"),
    }


def build_onboarding(plan_json, baseline, review_rows):
    """新系统只能显示待建档；现有真实计划可显示已建档但保留来源边界。"""
    plan = plan_json.get("plan", {})
    title = str(plan.get("title") or "")
    demo = any(token in title for token in ("示例", "匿名", "待建档"))
    missing = []
    for key, label in (("athlete", "使用者"), ("goal", "目标"), ("frequency", "训练频率")):
        if not plan.get(key):
            missing.append(label)
    if not baseline.get("source_version"):
        missing.append("执行基准")
    if demo:
        missing.append("已确认的真实训练计划")
    calibration_needed = any(
        exercise.get("load_status") == "calibration_required"
        for item in plan_json.get("schedule", [])
        for exercise in item.get("exercises", [])
    )
    if calibration_needed:
        missing.append("动作重量校准")
    return {
        "completed": not missing,
        "mode": "ready" if not missing else ("needs_calibration" if calibration_needed and set(missing) == {"动作重量校准"} else "needs_intake"),
        "missing": list(dict.fromkeys(missing)),
        "message": "已完成建档，可按当前计划执行。" if not missing else ("待校准：按训练日中的逐步引导确定未知动作重量。" if calibration_needed else "待建档：补齐必要信息前不显示正式训练重量。"),
        "review_count": len(review_rows),
    }


def runtime_suite_version():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from workbench_ui import suite_version
    return suite_version()


def build_system_info():
    return {
        "suite_version": runtime_suite_version(),
        "workbench_schema": SCHEMA_VERSION,
        "ui_contract": "v1",
        "last_health_check": None,
        "health": "unknown",
    }


def read_frontmatter(path):
    """读取简单 YAML frontmatter；只消费本系统约定的标量字段。"""
    try:
        with open(path, encoding="utf-8-sig") as fh:
            text = fh.read()
    except OSError:
        return {}, ""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    fields = {}
    for raw in parts[1].splitlines():
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\\s*(.*)$", raw.rstrip())
        if match:
            fields[match.group(1)] = match.group(2).strip().strip("'\\\"")
    return fields, parts[2]


def find_knowledge_root(project_root):
    """先找可迁移系统内的知识包，再兼容当前 vault 的共享知识库。"""
    candidates = [
        os.path.join(project_root, "健身知识库"),
        os.path.abspath(os.path.join(project_root, "..", "健身知识库")),
    ]
    return next((path for path in candidates if os.path.isdir(path)), None)


def build_knowledge_info(project_root):
    knowledge_root = find_knowledge_root(project_root)
    private_root = os.path.join(knowledge_root, "私人知识包") if knowledge_root else ""
    count = len([name for name in os.listdir(private_root) if os.path.isdir(os.path.join(private_root, name))]) if os.path.isdir(private_root) else 0
    manifest_candidates = [
        os.path.join(knowledge_root, "knowledge-pack-manifest.json") if knowledge_root else "",
        os.path.join(knowledge_root, "Skill", "knowledge-pack-manifest.json") if knowledge_root else "",
    ]
    public_pack = {"schema": 1, "status": "unregistered", "source": None}
    for path in manifest_candidates:
        if not path or not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8-sig") as fh:
                manifest = json.load(fh)
            if isinstance(manifest, dict) and manifest.get("schema") == 1 and manifest.get("scope") == "public":
                public_pack = {
                    "schema": 1,
                    "status": "available",
                    "source": relative_path(path, project_root),
                    "version": manifest.get("version"),
                    "reviewed_at": manifest.get("reviewed_at"),
                }
                break
        except (OSError, ValueError, json.JSONDecodeError):
            public_pack = {"schema": 1, "status": "invalid", "source": relative_path(path, project_root)}
            break
    return {
        "public_pack": public_pack,
        "private_pack": {"status": "available" if count else "not_loaded", "count": count, "excluded_from_public_export": True},
    }


def find_latest_status_artifact(project_root):
    """只读取最新状态快照或接回卡，让接回状态优先于旧处方。"""
    root = os.path.join(project_root, "训练复盘与状态", "状态档案")
    if not os.path.isdir(root):
        return None
    candidates = []
    for name in os.listdir(root):
        if name == "INDEX.md" or not name.lower().endswith((".md", ".json")):
            continue
        path = os.path.join(root, name)
        if os.path.isfile(path):
            candidates.append(path)
    if not candidates:
        return None
    path = max(candidates, key=os.path.getmtime)
    if path.lower().endswith(".json"):
        try:
            with open(path, encoding="utf-8-sig") as fh:
                fields = json.load(fh)
            body = ""
        except (OSError, ValueError, json.JSONDecodeError):
            return {"path": path, "file_path": relative_path(path, project_root), "file": os.path.basename(path), "invalid": True}
    else:
        fields, body = read_frontmatter(path)
    return {"path": os.path.abspath(path), "file_path": relative_path(path, project_root), "file": os.path.basename(path), "fields": fields if isinstance(fields, dict) else {}, "body": body}


def status_from_artifact(artifact):
    if not artifact:
        return None
    if artifact.get("invalid"):
        return {"state": "stale", "reason": "最新状态档案无法解析；不要把旧处方当作今日训练。", "source": artifact.get("file")}
    fields, body = artifact.get("fields", {}), artifact.get("body", "")
    permission = str(fields.get("return_permission") or fields.get("status") or "").strip().lower()
    is_return = "接回" in artifact.get("file", "") or permission in {"normal_return", "degraded_return", "minimum_return", "hold_and_refer"}
    if not is_return:
        return None
    until = fields.get("effective_until") or fields.get("valid_until") or fields.get("expires_at")
    if until:
        until = str(until)[:10]
    hold = permission == "hold_and_refer" or "hold_and_refer" in body
    expired = False
    if until:
        try:
            expired = dt.date.today() > dt.date.fromisoformat(until)
        except ValueError:
            until = None
    if hold or expired:
        return {
            "state": "stale",
            "effective_until": until,
            "reason": "接回状态要求暂缓训练" if hold else "接回方案已过有效期；请先重新确认当前状态。",
            "source": artifact.get("file"),
            "source_file": artifact.get("file_path"),
        }
    return {
        "state": "return",
        "effective_until": until,
        "reason": "当前处于接回阶段；按接回卡的正常／降级／最低方案执行，不套用停训前加重。",
        "source": artifact.get("file"),
        "source_file": artifact.get("file_path"),
    }


def build_status_info(baseline, meta, onboarding, artifact=None):
    if not onboarding.get("completed"):
        return {"state": "onboarding", "effective_until": None, "reason": onboarding.get("message"), "source": "onboarding"}
    artifact_state = status_from_artifact(artifact)
    if artifact_state:
        return artifact_state
    if not baseline.get("period_end"):
        return {"state": "unknown", "effective_until": None, "reason": "执行基准缺少有效期", "source": baseline.get("file")}
    state = "active" if dt.date.today().isoformat() <= baseline["period_end"] else "stale"
    return {
        "state": state,
        "effective_until": baseline["period_end"],
        "reason": None if state == "active" else "当前执行基准已超过有效期；不要把旧处方当作今日训练。",
        "source": baseline.get("file"),
    }


def build_provenance(plan_path, baseline, review_rows, sync, project_root):
    checked = dt.datetime.now().astimezone().isoformat(timespec="minutes")
    source_state = sync.get("source_state")
    notion_trust = sync.get("status")
    if source_state == "queried" and sync.get("status") == "ok":
        notion_trust = "verified"
    elif source_state == "cached":
        notion_trust = "cached"
    elif source_state == "restored":
        notion_trust = "restored"
    return {
        "plan": {"source": relative_path(plan_path, project_root), "verified_at": checked, "trust": "local_verified"},
        "baseline": {"source": relative_path(baseline.get("path"), project_root), "verified_at": checked, "trust": "local_verified"},
        "reviews": {"source": "训练复盘与状态/训练复盘/INDEX.md", "verified_at": checked, "trust": "local_verified", "count": len(review_rows)},
        "notion": {"source": "optional_notion_export", "verified_at": sync.get("source_queried_at"), "trust": notion_trust},
    }


def phase_for_week(phases, week):
    for p in phases:
        if p.get("start_week") <= week <= p.get("end_week"):
            return p.get("label", "")
    return ""


def build_days(plan_json, current_week, plan_start, notion=None):
    """结合 schedule 框架与 cycles 当前周主项处方。"""
    schedule = plan_json.get("schedule", [])
    cycles = plan_json.get("cycles", [])
    cyc_by_name = {}
    for c in cycles:
        title = c.get("title", "")
        for key in ("负重引体", "卧推", "深蹲", "硬拉"):
            if title.startswith(key):
                cyc_by_name[key] = c
                break

    def cell_for(name, day_key):
        """按「当日职责列」取主项当前周处方：headers 里包含 day_key 的那一列。"""
        c = cyc_by_name.get(name)
        if not c:
            return None
        headers = c.get("headers", [])
        row = None
        for r in c.get("rows", []):
            if r and r[0] and re.search(r"W%d\b" % current_week, str(r[0])):
                row = r
                break
        if not row:
            return None
        norm = day_key.replace(" ", "")
        idx = None
        for i, h in enumerate(headers):
            if i == 0:
                continue
            if norm in str(h).replace(" ", ""):
                idx = i
                break
        if idx is None:
            idx = 1
        return str(row[idx]) if idx < len(row) else str(row[1])

    latest = (notion or {}).get("latest_by_exercise", {})
    aliases = {
        "坐姿或俯卧腿弯举": "器械腿弯举（腘绳肌）",
        "侧平举": "Y字侧平举",
        "单腿下蹲": "叶问蹲",
        "提踵": "负重提踵",
        "反手划船（替代反手下拉）": "北理划船",
    }
    canonical = {
        "杠铃卧推": "卧推",
        "杠铃卧推（容量）": "卧推",
        "杠铃深蹲": "深蹲",
        "停顿深蹲": "深蹲",
        "负重引体": "负重引体",
        "硬拉": "硬拉",
    }

    def conditional_main(ex_name, sets, day_key):
        """解析“W3/W5/W7 主项”一类条件主项，并过滤非当前周分支。"""
        if "主项" not in ex_name:
            return None, None, False
        weeks = [int(x) for x in re.findall(r"W(\d+)", ex_name)]
        if weeks and current_week not in weeks:
            return None, None, True
        if day_key == "腿B":
            key = "硬拉" if "硬拉" in sets else "深蹲"
            display = re.split(r"[，,]", sets or "", maxsplit=1)[0].strip() or key
            return key, display, False
        return None, None, False

    days = {}
    timeline = []

    def session_is_done(date, day_key):
        for session in (notion or {}).get("sessions", []):
            session_date = normalized_full_date(session.get("date"))
            if session_date == date and day_key in str(session.get("day", "")):
                return True
        return False

    for s in schedule:
        if "exercises" not in s:
            continue
        theme = s.get("theme", "")
        normalized = theme.replace(" ", "")
        day_key = None
        for k in DEFAULT_WEEKDAY:
            if k in normalized:
                day_key = k
                break
        if not day_key:
            day_key = str(s.get("day_key") or s.get("title") or s.get("theme") or "训练日")
        role = s.get("role", "")
        exercises = []
        for e in s.get("exercises", []):
            ex_name = e.get("name", "")
            sets = e.get("sets", "")
            target = e.get("target", "")
            conditional_key, display_name, inactive = conditional_main(ex_name, sets, day_key)
            if inactive:
                continue
            main_key = conditional_key or canonical.get(ex_name, ex_name)
            main = main_key in cyc_by_name or e.get("priority") in ("main", "key")
            w, d, rpe = None, None, None
            if main:
                if str(sets).startswith("实际："):
                    w = extract_peak_w(sets)
                    d = sets
                else:
                    cell = cell_for(main_key, day_key)
                    if cell:
                        w = extract_w(cell)
                        d = cell
                    else:
                        w = extract_w(sets)
                        d = sets or None
                rpe = target if target else None
            else:
                w = extract_w(sets)
                d = sets if sets else None
                rpe = target if target else None
            if "自重" in str(sets):
                w = "自重"
                d = sets
            observed = latest.get(ex_name) or latest.get(aliases.get(ex_name, "")) or {}
            weight_source = e.get("load_source")
            if w is None and observed.get("weight") is not None:
                suffix = "/手" if observed.get("per_hand") else ""
                w = ("%g" % observed["weight"]) + "kg" + suffix
                weight_source = observed.get("source")
            exercises.append({
                "name": display_name or ex_name,
                "w": w,
                "d": d,
                "rpe": rpe,
                "main": main,
                "muscle_groups": e.get("muscle_groups", []),
                "planned_sets": e.get("planned_sets"),
                "weight_source": weight_source,
            })
        item = {"role": role, "exercises": exercises, "date": parse_schedule_date(s.get("day", ""), plan_start), "label": s.get("label"), "title": s.get("title")}
        days[day_key] = item
        if item["date"]:
            completed = "已完成" in s.get("day", "") or session_is_done(item["date"], day_key)
            timeline.append({"date": item["date"], "type": "training", "day": day_key, "status": "done" if completed else "planned"})
    for s in schedule:
        if "exercises" in s:
            continue
        date = parse_schedule_date(s.get("day", ""), plan_start)
        if date:
            timeline.append({"date": date, "type": "recovery", "title": s.get("theme", "恢复／轻活动"), "role": s.get("role", "")})
    if not days:
        fail("schedule 中没有可识别的训练日")
    timeline.sort(key=lambda x: x["date"])
    return days, timeline


def parse_schedule_date(text, plan_start):
    m = re.search(r"(\d{2})-(\d{2})", text or "")
    if not m:
        return None
    start = dt.date.fromisoformat(plan_start)
    value = dt.date(start.year, int(m.group(1)), int(m.group(2)))
    if value < start - dt.timedelta(days=30):
        value = dt.date(start.year + 1, value.month, value.day)
    elif value > start + dt.timedelta(days=330):
        value = dt.date(start.year - 1, value.month, value.day)
    return value.isoformat()


def validate_week_transition_contract(data, plan_json, today=None):
    """阻断旧排程、漏训练日、错误今日处方与自重覆盖。"""
    problems = []
    today = today or dt.date.today()
    meta = data.get("meta", {})
    plan_start = meta.get("plan_start")
    if not plan_start:
        return ["周切换校验缺少 plan_start"]
    snapshot = schedule_contract_snapshot(plan_json, plan_start, today)
    status = data.get("status", {}).get("state")
    active = status in ("active", "return")

    if active and not snapshot["covers_today"]:
        problems.append(
            "当前排程未覆盖今天（%s；排程 %s 至 %s），必须先更新当前周 schedule 再刷新工作台"
            % (today.isoformat(), snapshot["first_date"] or "无日期", snapshot["last_date"] or "无日期")
        )
        return problems
    if not snapshot["covers_today"]:
        return problems

    if snapshot["missing_week_labels"]:
        problems.append("当前排程训练日缺少统一 Wn 标签: " + "、".join(snapshot["missing_week_labels"]))
    if len(snapshot["weeks"]) != 1:
        problems.append("当前排程训练日周次不唯一: %s" % sorted(snapshot["weeks"]))
        expected_week = None
    else:
        expected_week = next(iter(snapshot["weeks"]))

    training = snapshot["training"]
    valid_training = [item for item in training if item.get("date") and item.get("day")]
    declared_frequency = declared_training_frequency(plan_json)
    if declared_frequency is not None and len(training) != declared_frequency:
        problems.append("当前排程训练日数量与 plan.frequency 不一致: 计划 %d 练，实际 %d 个" % (declared_frequency, len(training)))
    if len(valid_training) != len(training):
        problems.append("当前排程存在无法识别日期或训练日名称的条目")
    dates = [item.get("date") for item in valid_training]
    day_keys = [item.get("day") for item in valid_training]
    if len(set(dates)) != len(dates):
        problems.append("当前排程训练日期重复")
    if len(set(day_keys)) != len(day_keys):
        problems.append("当前排程训练日标识重复")

    current_week = int(meta.get("current_week") or 0)
    if expected_week is not None and current_week != expected_week:
        problems.append("工作台 current_week=W%d 与当前排程 W%d 不一致" % (current_week, expected_week))
    if expected_week is not None:
        expected_phase = phase_for_week(plan_json.get("phases", []), expected_week)
        if meta.get("phase") != expected_phase:
            problems.append("工作台阶段与当前排程周次不一致: %s / %s" % (meta.get("phase"), expected_phase))

    expected_events = {
        (item.get("date"), item.get("type"), None)
        for item in snapshot["events"]
        if item.get("date") and item.get("type") == "recovery"
    }
    expected_events.update((item.get("date"), "training", item.get("day")) for item in valid_training)
    actual_events = {
        (item.get("date"), item.get("type"), item.get("day") if item.get("type") == "training" else None)
        for item in data.get("timeline", [])
        if item.get("date") and item.get("type") in ("training", "recovery")
    }
    if actual_events != expected_events:
        problems.append("timeline 未逐日复现当前 schedule")

    days = data.get("days", {})
    for source in valid_training:
        target = days.get(source["day"])
        if not target or target.get("date") != source["date"]:
            problems.append("训练卡未同步当前排程: %s %s" % (source["date"], source["day"]))
            continue
        selfweight_count = sum(1 for exercise in source["exercises"] if "自重" in str(exercise.get("sets") or ""))
        if selfweight_count:
            resolved = [exercise for exercise in target.get("exercises", []) if exercise.get("w") == "自重" and not exercise.get("weight_source")]
            if len(resolved) < selfweight_count:
                problems.append("处方明确为自重却被历史负重覆盖: %s" % source["day"])

    today_iso = today.isoformat()
    today_training = next((item for item in valid_training if item.get("date") == today_iso), None)
    if today_training and not any(
        item.get("date") == today_iso and item.get("type") == "training" and item.get("day") == today_training.get("day")
        for item in data.get("timeline", [])
    ):
        problems.append("今天是计划训练日但今日处方缺失: %s" % today_training.get("day"))
    return problems


def extract_w(text):
    """提取第一个 kg 重量（含 + 前缀与 /手），找不到返回 None。"""
    if not text:
        return None
    m = re.search(r"[+\-]?\d+(?:\.\d+)?kg(?:/手)?", text)
    return m.group(0) if m else None


def extract_peak_w(text):
    """已执行主项可能记录多次尝试；显示其中最高有效重量，完整顺序仍保留在详情中。"""
    values = re.findall(r"[+\-]?\d+(?:\.\d+)?kg(?:/手)?", text or "")
    if not values:
        return None
    return max(values, key=lambda x: float(re.search(r"[+\-]?\d+(?:\.\d+)?", x).group(0)))


def build_week(plan_json, current_week):
    out = []
    cycles = plan_json.get("cycles", [])
    for c in cycles:
        title = c.get("title", "")
        for key in ("负重引体", "卧推", "深蹲", "硬拉"):
            if title.startswith(key):
                headers = c.get("headers", [])
                row = None
                for r in c.get("rows", []):
                    if r and r[0] and re.search(r"W%d\b" % current_week, str(r[0])):
                        row = r
                        break
                if row:
                    parts = []
                    for i, h in enumerate(headers):
                        if i == 0 or i >= len(row):
                            continue
                        cell = str(row[i]).strip() if row[i] else ""
                        if not cell:
                            continue
                        label = str(h).split("：")[0].split(":")[0].strip()
                        parts.append(label + " " + cell)
                    text = "；".join(parts)
                    if len(text) > 150:
                        text = text[:150] + "…"
                    out.append({"k": key, "v": text})
                break
    return out


def review_candidates_for_chart_point(point, review_rows, plan_mapping):
    """Resolve one actual chart point to one session review by date and duty."""
    date = normalized_full_date(point.get("date"))
    if not date:
        return []
    candidates = [r for r in (review_rows or []) if r.get("full_date") == date]
    if not candidates:
        return []
    expected_day = plan_mapping.get(canonical_main_lift_name(point.get("name")))
    if expected_day:
        duty_matches = [r for r in candidates if day_labels_match(expected_day, r.get("day", ""))]
        if duty_matches:
            candidates = duty_matches
    non_weekly = [r for r in candidates if r.get("day") != "周训练阶段"]
    return non_weekly or candidates


def attach_chart_review(point, review_rows, plan_mapping):
    """Add a portable review reference without copying review content into chart points."""
    enriched = dict(point)
    candidates = review_candidates_for_chart_point(point, review_rows, plan_mapping)
    if len(candidates) > 1:
        labels = ", ".join(str(r.get("file") or r.get("day") or "未知") for r in candidates)
        fail("曲线实际点无法唯一关联复盘: %s %s (%s)" % (point.get("name"), point.get("date"), labels))
    if candidates:
        review = candidates[0]
        # The current formal reader resolves review_title against D.reviews.
        # Keep review_href as a compatibility field for older templates.
        enriched["review_title"] = review.get("workbench_title") or review.get("file")
        enriched["review_href"] = review.get("file")
        enriched["review_file"] = review.get("file")
    return enriched


def build_charts(plan_json, notion=None, review_rows=None):
    charts = {}
    plan_mapping = build_main_lift_day_map(plan_json)
    for c in plan_json.get("cycles", []):
        title = c.get("title", "")
        key = None
        for k in ("负重引体", "卧推", "深蹲", "硬拉"):
            if title.startswith(k):
                key = k
                break
        if not key or "chart" not in c:
            continue
        ch = c["chart"]
        strength = [{"week": p.get("week"), "v": p.get("value")} for p in ch.get("strength", [])]
        actual = [
            attach_chart_review(p, review_rows, plan_mapping)
            for p in (notion or {}).get("main_lifts", [])
            if p.get("name") == key
        ]
        charts[key] = {"cap": ch.get("strength_label", "强度"), "strength": strength, "actual": actual}
    return charts


def exercise_set_count(exercise):
    """Best-effort extraction of planned working sets; never turns it into completed volume."""
    match = re.match(r"\s*(\d+)", str(exercise.get("planned_sets") or exercise.get("d") or ""))
    return int(match.group(1)) if match else 0


def safe_nonnegative_number(value):
    """Return a finite non-negative number, or None for an unverified input."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def current_week_dates(timeline):
    dates = []
    for item in timeline:
        try:
            dates.append(dt.date.fromisoformat(item.get("date", "")))
        except (TypeError, ValueError):
            continue
    if not dates:
        return None, None
    start = min(dates)
    return start - dt.timedelta(days=start.weekday()), start - dt.timedelta(days=start.weekday()) + dt.timedelta(days=6)


def activity_rows_for_week(notion, timeline):
    start, end = current_week_dates(timeline)
    rows = []
    for item in (notion or {}).get("activity", []):
        if not isinstance(item, dict):
            continue
        try:
            date = dt.date.fromisoformat(str(item.get("date", ""))[:10])
        except (TypeError, ValueError):
            continue
        if start and end and not (start <= date <= end):
            continue
        rows.append(item)
    return rows


def build_goal_metrics(plan_json, days, timeline, notion):
    """Build goal-specific cards without inventing personal activity or body-composition facts."""
    plan = plan_json.get("plan", {})
    mode = plan.get("objective_mode", "general_fitness")
    targets = plan.get("tracking_targets") if isinstance(plan.get("tracking_targets"), list) else []
    by_id = {item.get("id"): item for item in targets if isinstance(item, dict) and item.get("id")}
    training_events = [item for item in timeline if item.get("type") == "training"]
    done = len([item for item in training_events if item.get("status") == "done"])
    metrics = [{
        "id": "training_completion",
        "label": by_id.get("training_completion", {}).get("label", "本周训练完成"),
        "value": "%d/%d 次" % (done, len(training_events)),
        "detail": "来自当前训练日时间线",
        "state": "current",
        "source": "timeline",
        "next_action": by_id.get("training_completion", {}).get("next_action", "完成训练后写入复盘。"),
    }]

    if mode == "hypertrophy":
        group_sets = {}
        for day in days.values():
            for exercise in day.get("exercises", []):
                if not exercise.get("main"):
                    continue
                groups = exercise.get("muscle_groups") or []
                if not groups:
                    groups = ["重点动作"]
                for group in groups:
                    group_sets[group] = group_sets.get(group, 0) + exercise_set_count(exercise)
        if group_sets:
            summary = " · ".join("%s %d 组" % item for item in list(group_sets.items())[:4])
            metrics.append({
                "id": "planned_sets",
                "label": by_id.get("planned_sets", {}).get("label", "重点肌群计划组数"),
                "value": summary,
                "detail": "这是计划量，不等于已完成训练量",
                "state": "planned",
                "source": "plan",
                "next_action": by_id.get("planned_sets", {}).get("next_action", "完成训练后记录实际组数、重量、次数与余力。"),
            })
        metrics.append({
            "id": "progression_log",
            "label": by_id.get("progression_log", {}).get("label", "双重渐进记录"),
            "value": "重量 · 次数 · 余力",
            "detail": "由每次训练实际记录驱动，不用主观猜测替代",
            "state": "needs_data",
            "source": "training_review",
            "next_action": by_id.get("progression_log", {}).get("next_action", "训练后把每个动作的实际重量、次数和 RIR 告诉 AI。"),
        })

    if mode == "fat_loss":
        raw_weights = (notion or {}).get("bodyweight", [])
        raw_weights = raw_weights if isinstance(raw_weights, list) else []
        weights = []
        for item in raw_weights:
            if not isinstance(item, dict):
                continue
            kg = safe_nonnegative_number(item.get("kg"))
            if kg is not None:
                weights.append({**item, "kg": kg})
        latest_raw_weight = raw_weights[-1] if raw_weights else None
        latest_is_verified = isinstance(latest_raw_weight, dict) and safe_nonnegative_number(latest_raw_weight.get("kg")) is not None
        if weights and latest_is_verified:
            latest = weights[-1]
            change = ""
            if len(weights) >= 2:
                delta = float(latest["kg"]) - float(weights[0]["kg"])
                change = " · 较首条 %+.1f kg" % delta
            metrics.append({
                "id": "bodyweight_trend",
                "label": by_id.get("bodyweight_trend", {}).get("label", "体重趋势"),
                "value": "%.1f kg" % float(latest["kg"]),
                "detail": (str(latest.get("date", "")) + change).strip(),
                "state": "current",
                "source": "notion.bodyweight",
                "next_action": by_id.get("bodyweight_trend", {}).get("next_action", "按固定条件继续记录体重，再结合趋势调整。"),
            })
        else:
            metrics.append({
                "id": "bodyweight_trend",
                "label": by_id.get("bodyweight_trend", {}).get("label", "体重趋势"),
                "value": "待记录",
                "detail": "没有可核验的体重数据",
                "state": "needs_data",
                "source": "notion.bodyweight",
                "next_action": by_id.get("bodyweight_trend", {}).get("next_action", "先连续记录 3—7 天晨起体重，建立趋势基线。"),
            })
        activity = activity_rows_for_week(notion, timeline)
        step_values = [value for item in activity if (value := safe_nonnegative_number(item.get("steps"))) is not None]
        cardio_values = [value for item in activity if (value := safe_nonnegative_number(item.get("cardio_minutes"))) is not None]
        metrics.extend([
            {
                "id": "daily_steps",
                "label": by_id.get("daily_steps", {}).get("label", "日均步数"),
                "value": ("%d 步" % round(sum(step_values) / len(step_values))) if step_values else "待记录",
                "detail": "本周 %d 天活动记录" % len(step_values) if step_values else "尚未接入活动记录",
                "state": "current" if step_values else "needs_data",
                "source": "notion.activity.steps",
                "next_action": by_id.get("daily_steps", {}).get("next_action", "记录每日步数；目标由 AI 根据你的当前基线确认。"),
            },
            {
                "id": "cardio_minutes",
                "label": by_id.get("cardio_minutes", {}).get("label", "本周有氧"),
                "value": ("%d 分钟" % round(sum(cardio_values))) if cardio_values else "待记录",
                "detail": "本周已记录的低冲击有氧" if cardio_values else "尚未接入有氧记录",
                "state": "current" if cardio_values else "needs_data",
                "source": "notion.activity.cardio_minutes",
                "next_action": by_id.get("cardio_minutes", {}).get("next_action", "记录有氧时长和主观恢复，不做惩罚性加量。"),
            },
        ])
    return metrics


def build_reviews(review_rows, project_root):
    review_dir = os.path.join("训练复盘与状态", "训练复盘")
    out = []
    # The review index is the authoritative display set. Do not impose a UI or
    # builder-side item cap: every indexed review must remain available in the
    # workbench, in the same order as the index.
    for r in review_rows:
        item = dict(r)
        if r.get("file"):
            absolute = os.path.abspath(os.path.join(project_root, review_dir, r["file"] + ".md"))
            if not os.path.isfile(absolute):
                fail("复盘索引目标不存在: " + absolute)
            item["file_path"] = relative_path(absolute, project_root)
            item["content_markdown"] = read_portable_document(absolute) or ""
            item.update(read_workbench_summary(absolute))
        else:
            fail("复盘索引缺少可打开的文件链接: %s %s" % (r.get("full_date"), r.get("day")))
        out.append(item)
    return out


def read_workbench_summary(path):
    """读取复盘 frontmatter 中的工作台摘要字段，不引入第三方 YAML 依赖。"""
    fields = {"workbench_title", "workbench_lead", "workbench_points", "workbench_decision"}
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8-sig") as fh:
        text = fh.read()
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    out = {}
    active_list = None
    for raw in parts[1].splitlines():
        line = raw.rstrip()
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
        if match:
            key, value = match.group(1), match.group(2).strip()
            active_list = None
            if key not in fields:
                continue
            if key == "workbench_points":
                out[key] = []
                active_list = key
                if value.startswith("[") and value.endswith("]"):
                    out[key] = [x.strip().strip("'\"") for x in value[1:-1].split(",") if x.strip()][:3]
            elif value:
                out[key] = value.strip("'\"")
            continue
        if active_list and re.match(r"^\s*-\s+", line):
            value = re.sub(r"^\s*-\s+", "", line).strip().strip("'\"")
            if value and len(out[active_list]) < 3:
                out[active_list].append(value)
    return {k: v for k, v in out.items() if v}


def load_notion(notion_file):
    if not notion_file or not os.path.isfile(notion_file):
        return None
    try:
        with open(notion_file, encoding="utf-8-sig") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise ValueError("根节点必须是对象")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "last_sync": None, "source_queried_at": None, "snapshot_generated_at": None,
            "latest_training_record_date": None, "latest_bodyweight_record_date": None,
            "bodyweight": [], "baseline_kg": None,
            "baseline_note": None, "sessions": [], "note": "Notion 数据文件解析失败。",
            "latest_by_exercise": {}, "main_lifts": [], "activity": [], "notion_url": None, "_load_error": str(exc),
        }
    return normalize_notion_payload({
        "sync_mode": data.get("sync_mode"),
        "source_queried_at": data.get("source_queried_at"),
        "latest_training_record_date": data.get("latest_training_record_date"),
        "latest_bodyweight_record_date": data.get("latest_bodyweight_record_date"),
        "snapshot_generated_at": data.get("snapshot_generated_at"),
        "last_sync": data.get("last_sync"),
        "bodyweight": data.get("bodyweight", []),
        "baseline_kg": data.get("baseline_kg"),
        "baseline_note": data.get("baseline_note"),
        "sessions": data.get("sessions", []),
        "note": data.get("note"),
        "latest_by_exercise": data.get("latest_by_exercise", {}),
        "main_lifts": data.get("main_lifts", []),
        "activity": data.get("activity", []),
        "notion_url": data.get("notion_url"),
    })


def load_notion_from_workbench(html_file):
    """从本地工作台备份恢复已核验的 Notion 导出，不恢复计划或复盘等其他字段。"""
    try:
        with open(html_file, encoding="utf-8") as fh:
            html = fh.read()
        match = re.search(r'<script id="workbench-data" type="application/json">([\s\S]*?)</script>', html)
        if not match:
            raise ValueError("未找到 workbench-data")
        data = json.loads(match.group(1))
        notion = data.get("notion")
        if not isinstance(notion, dict):
            raise ValueError("备份中没有 Notion 数据")
        return normalize_notion_payload(notion)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        fail("无法从备份恢复 Notion 数据：%s" % exc)


def parse_sync_date(value):
    parsed = _comparable_time(value)
    return parsed.date() if parsed else None


def notion_sync_state(notion, objective_mode="general_fitness"):
    if not notion:
        return "stale", "Notion 数据文件缺失，使用本地复盘与计划数据", ["notion.bodyweight", "notion.sessions"]
    if notion.get("_load_error"):
        return "failed", "Notion 数据文件无法解析", ["notion.source_queried_at", "notion.sessions", "notion.main_lifts"]
    stale = []
    sync_date = parse_sync_date(notion.get("source_queried_at") or notion.get("last_sync"))
    if sync_date is None:
        stale.append("notion.source_queried_at")
    elif (dt.date.today() - sync_date).days > MAX_NOTION_AGE_DAYS:
        stale.append("notion.source_queried_at")
    if not isinstance(notion.get("sessions"), list) or not notion.get("sessions"):
        stale.append("notion.sessions")
    if objective_mode == "strength":
        if not isinstance(notion.get("main_lifts"), list) or not notion.get("main_lifts"):
            stale.append("notion.main_lifts")
    elif objective_mode == "hypertrophy":
        if not isinstance(notion.get("latest_by_exercise"), dict) or not notion.get("latest_by_exercise"):
            stale.append("notion.latest_by_exercise")
    elif objective_mode == "fat_loss":
        if not isinstance(notion.get("bodyweight"), list) or not notion.get("bodyweight"):
            stale.append("notion.bodyweight")
    if stale:
        return "stale", "Notion 数据不完整或已过期", stale
    return "ok", None, []


def build_sync_metadata(notion, previous_sync, source_state, merge_mode, objective_mode="general_fitness", attempted_at=None):
    """Separate source-query freshness from a local workbench rebuild."""
    previous_sync = previous_sync if isinstance(previous_sync, dict) else {}
    sync_status, sync_reason, stale_fields = notion_sync_state(notion, objective_mode)
    source_queried_at = (notion or {}).get("source_queried_at") or (notion or {}).get("last_sync")
    cached = source_state == "cached"
    if cached:
        cache_reason = "未提供新 Notion 快照；cached/preserved，保留上次已核验数据。"
        sync_reason = cache_reason + ((" " + sync_reason) if sync_reason else "")
    return {
        "status": sync_status,
        "source_state": source_state,
        "merge_mode": merge_mode,
        "source_queried_at": source_queried_at,
        "snapshot_generated_at": (notion or {}).get("snapshot_generated_at"),
        "latest_training_record_date": (notion or {}).get("latest_training_record_date"),
        "latest_bodyweight_record_date": (notion or {}).get("latest_bodyweight_record_date"),
        "last_success": (
            previous_sync.get("last_success") or source_queried_at
            if cached
            else source_queried_at or previous_sync.get("last_success")
        ),
        "last_attempt": attempted_at if source_state == "queried" else previous_sync.get("last_attempt"),
        "reason": sync_reason,
        "stale_fields": stale_fields,
    }


def build_done(timeline):
    return {
        x["day"]: "已执行 " + x["date"][5:]
        for x in timeline
        if x.get("type") == "training" and x.get("status") == "done" and x.get("day")
    }


def build_today_summary(review_rows, timeline):
    today = dt.date.today().isoformat()
    event = next((x for x in timeline if x.get("date") == today and x.get("type") == "training" and x.get("status") == "done"), None)
    if not event:
        return None
    review = next((r for r in review_rows if r.get("full_date") == today and event.get("day", "") in r.get("day", "")), None)
    if not review:
        return None
    return {"date": today, "day": event.get("day"), "result": review.get("verdict", ""), "next": None}


def build_advice(timeline, _previous_advice=None):
    """Generate schedule-bound guidance; never carry a dated instruction across rebuilds."""
    today = dt.date.today().isoformat()
    event = next((item for item in timeline if item.get("date") == today), None)
    if event and event.get("type") == "training":
        return "按当前计划排程执行今日%s；训练后按复盘索引记录结果。" % (event.get("day") or "训练")
    if event and event.get("type") == "recovery":
        return "今日按当前计划恢复；如训练条件变化，先更新排程再刷新工作台。"
    return "按当前计划排程执行；训练后按复盘索引记录结果。"


def inherit_previous(html_path):
    """从现有 HTML 读取上一版数据块（用于 advice 等人工维护字段的继承）。"""
    try:
        with open(html_path, encoding="utf-8") as fh:
            html = fh.read()
        m = re.search(r'<script id="workbench-data" type="application/json">([\s\S]*?)</script>', html)
        if not m:
            return {}
        return json.loads(m.group(1))
    except Exception:
        return {}


def validate(data, plan_json, project_root):
    """校验数据块与主源一致性。返回 (ok, [问题])。"""
    problems = []
    unresolved = sorted(set(re.findall(r"__[A-Z0-9_]+__", json.dumps(data, ensure_ascii=False))))
    if unresolved:
        problems.append("数据仍含未替换占位符: " + ", ".join(unresolved))
    # 唯一数据块与 JSON 可解析在替换时由调用方检查
    meta = data.get("meta", {})
    if not re.match(r"^v\d+$", meta.get("source_version", "")):
        problems.append("source_version 缺失或非法")
    if meta.get("baseline_version") != meta.get("source_version"):
        problems.append("执行基准版本与当前计划不一致")
    if not meta.get("plan_start") or not meta.get("plan_end"):
        problems.append("执行基准缺少周期起止日期")
    else:
        try:
            start = dt.date.fromisoformat(meta["plan_start"])
            expected_end = start + dt.timedelta(days=int(meta.get("total_weeks", 0)) * 7)
            end = dt.date.fromisoformat(meta["plan_end"])
            if abs((end - expected_end).days) > 2:
                problems.append("执行基准周期长度与计划周数不一致")
        except (TypeError, ValueError):
            problems.append("执行基准周期日期非法")
    plan_target = resolve_project_href(project_root, meta.get("plan_href"))
    if not plan_target or not os.path.isfile(plan_target):
        problems.append("完整计划入口不存在")
    # 曲线与 cycles 逐点一致
    for name, chart in data.get("charts", {}).items():
        src = None
        for c in plan_json.get("cycles", []):
            if c.get("title", "").startswith(name) and "chart" in c:
                src = c["chart"]["strength"]
                break
        if src is None:
            problems.append("图表缺少主源: " + name)
            continue
        dst = [(p.get("week"), p.get("v")) for p in chart.get("strength", [])]
        s2 = [(p.get("week"), p.get("value")) for p in src]
        if dst != s2:
            problems.append("图表数据与主源不一致: " + name)
    # 周次与复盘索引一致
    if data.get("meta", {}).get("current_week") is None:
        problems.append("current_week 缺失")
    expected_done = build_done(data.get("timeline", []))
    if data.get("done") != expected_done:
        problems.append("完成状态未按当前时间线生成")
    for day, item in data.get("days", {}).items():
        active_main = [x for x in item.get("exercises", []) if x.get("main")]
        if not active_main:
            problems.append("训练日未识别到主项: " + day)
        for exercise in active_main:
            if data.get("onboarding", {}).get("completed") is False:
                continue
            if not exercise.get("w") or not exercise.get("d"):
                problems.append("主项缺少精确处方: %s/%s" % (day, exercise.get("name")))
    for review in data.get("reviews", []):
        review_target = resolve_project_href(project_root, browser_href(review.get("file_path", "")))
        if not review_target or not os.path.isfile(review_target):
            problems.append("复盘链接目标不存在: " + str(review.get("file")))
    summary = data.get("today_summary")
    if summary:
        if not any(x.get("date") == summary.get("date") and x.get("day") == summary.get("day") and x.get("status") == "done" for x in data.get("timeline", [])):
            problems.append("今日复盘与今日时间线不一致")
    # 必填字段
    for f in ("days", "reviews", "rules", "onboarding", "system", "knowledge", "status", "provenance", "goal_metrics"):
        if f not in data:
            problems.append("缺少必填字段: " + f)
    if data.get("schema") != SCHEMA_VERSION:
        problems.append("工作台 schema 非当前版本: %s" % data.get("schema"))
    onboarding = data.get("onboarding", {})
    if onboarding.get("completed") is False and any(item.get("w") for day in data.get("days", {}).values() for item in day.get("exercises", [])):
        problems.append("待建档状态不得显示正式训练重量")
    state = data.get("status", {})
    if state.get("state") not in ("active", "stale", "onboarding", "unknown", "return"):
        problems.append("训练状态非法")
    problems.extend(validate_week_transition_contract(data, plan_json))
    return problems


def apply_data(html_path, data, backup_dir):
    """原子替换 HTML 的唯一 workbench-data 数据块。
    流程：读 HTML → 生成新内容 → 写临时文件 → 校验 → os.replace。
    失败时保留原文件，并把上一版备份到 backup_dir。"""
    with open(html_path, encoding="utf-8") as fh:
        html = fh.read()
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    replacement = '<script id="workbench-data" type="application/json">' + payload + '</script>'
    new_html, n = re.subn(
        r'<script id="workbench-data" type="application/json">[\s\S]*?</script>',
        lambda _match: replacement,
        html, count=1)
    if n != 1:
        fail("HTML 中未找到唯一的 workbench-data 数据块，拒绝替换")
    tmp_path = html_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        fh.write(new_html)
    # 校验临时文件
    with open(tmp_path, encoding="utf-8") as fh:
        check_html = fh.read()
    blocks = re.findall(r'<script id="workbench-data" type="application/json">([\s\S]*?)</script>', check_html)
    if len(blocks) != 1:
        os.remove(tmp_path)
        fail("替换后数据块数量异常（%d 个），已回滚" % len(blocks))
    try:
        json.loads(blocks[0])
    except Exception as e:
        os.remove(tmp_path)
        fail("替换后数据块 JSON 无法解析：%s，已回滚" % e)
    # 备份上一版
    if backup_dir and os.path.isfile(html_path):
        os.makedirs(backup_dir, exist_ok=True)
        backup = os.path.join(backup_dir, "pre-apply-workbench.html")
        with open(backup, "w", encoding="utf-8") as fh:
            fh.write(html)
    os.replace(tmp_path, html_path)
    print("workbench-data applied: " + html_path)
    if backup_dir:
        print("previous version backed up to: " + os.path.join(backup_dir, "pre-apply-workbench.html"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--notion")
    ap.add_argument(
        "--notion-mode",
        choices=sorted(NOTION_SYNC_MODES),
        help="Notion 输入语义：incremental 按稳定键增量合并；full 声明为完整历史快照",
    )
    ap.add_argument("--restore-notion-from-html", help="仅从已知本地备份恢复 Notion 动态数据")
    ap.add_argument(
        "--replace-main-lift-history",
        action="store_true",
        help="仅与 full Notion 输入一起使用：人工核验后权威替换整份主项实际历史",
    )
    ap.add_argument("--check-only", action="store_true")
    ap.add_argument("--apply", action="store_true", help="校验通过后替换正式 HTML 数据块")
    ap.add_argument("--backup-dir", help="替换前上一版备份目录（建议 tmp 临时层）")
    ap.add_argument("--out")
    ap.add_argument("--integration-config", help="可选公开客户端配置 JSON；缺省时保留已有配置或保持 local")
    args = ap.parse_args()
    if args.notion and args.restore_notion_from_html:
        fail("--notion 与 --restore-notion-from-html 不能同时使用")
    if args.notion_mode and not args.notion:
        fail("--notion-mode 只能与 --notion 一起使用")
    if args.replace_main_lift_history and not args.notion:
        fail("--replace-main-lift-history 只能与 --notion 一起使用")

    project = os.path.abspath(args.project)
    plan_path, plan_name = find_active_plan_json(project)
    with open(plan_path, encoding="utf-8") as fh:
        plan_json = json.load(fh)
    source_version = "v" + re.search(r"-v(\d+)\.json$", plan_name).group(1)
    baseline = find_execution_baseline(project, source_version)

    review_rows = parse_review_index(project)
    current_week = None
    for r in review_rows:  # INDEX 首行最新
        w = parse_week(r["week"])
        if w:
            current_week = w
            break
    if current_week is None:
        fail("无法从复盘索引确定当前周次")
    scheduled_week = current_week_from_schedule(
        plan_json,
        baseline.get("week_start") or baseline["period_start"],
        dt.date.today(),
    )
    if scheduled_week is not None:
        current_week = scheduled_week

    html_path = os.path.join(project, "健身工作台.html")
    prev = inherit_previous(html_path)
    # 没有新导出时保留正式页已有的最近一次已核验 Notion 数据，再由新鲜度检查决定是否过期；
    # 绝不能因一次本地复盘刷新就把用户动态事实静默清空。
    # 仅保留带有成功同步时间的旧动态数据。匿名初始化页中的空占位对象
    # 不是可继承事实，否则第二次检查会把“未提供”误判为“不完整导出”。
    prior_notion = prev.get("notion") if isinstance(prev.get("notion"), dict) else None
    try:
        retained_notion = normalize_notion_payload(prior_notion)
        retained_notion = retained_notion if retained_notion and (
            retained_notion.get("source_queried_at") or retained_notion.get("last_sync")
        ) else None
        if args.notion:
            incoming_notion = load_notion(args.notion)
            notion_mode, explicit_mode = resolve_notion_mode(args.notion_mode, incoming_notion)
            if not explicit_mode:
                warn("旧 Notion 输入未声明 sync_mode；为兼容按 incremental 处理")
            notion = merge_notion_history(
                retained_notion,
                incoming_notion,
                mode=notion_mode,
                replace_main_lifts=args.replace_main_lift_history,
            )
            notion_source_state = "queried"
            notion_merge_mode = notion_mode
            attempted_at = dt.datetime.now().astimezone().isoformat(timespec="minutes")
        elif args.restore_notion_from_html:
            notion = load_notion_from_workbench(args.restore_notion_from_html)
            notion_source_state = "restored"
            notion_merge_mode = "preserved"
            attempted_at = None
        else:
            notion = retained_notion
            notion_source_state = "cached" if notion else "missing"
            notion_merge_mode = "preserved"
            attempted_at = None
    except NotionSyncConflict as exc:
        fail(str(exc))
    history_problems = validate_main_lift_history(notion, current_week, plan_json)
    if history_problems:
        fail("；".join(history_problems))
    sync = build_sync_metadata(
        notion,
        prev.get("sync", {}),
        notion_source_state,
        notion_merge_mode,
        plan_json.get("plan", {}).get("objective_mode", "general_fitness"),
        attempted_at,
    )

    days, timeline = build_days(plan_json, current_week, baseline.get("week_start") or baseline["period_start"], notion)
    meta = build_meta(plan_json, plan_name, current_week, baseline, project)
    onboarding = build_onboarding(plan_json, baseline, review_rows)
    review_documents = build_reviews(review_rows, project)
    nutrition_contract = None
    nutrition_root = Path(project) / "工作台与工具" / "饮食工作台"
    nutrition_candidates = sorted(nutrition_root.glob("nutrition-contract-v*.json")) if nutrition_root.is_dir() else []
    if nutrition_candidates:
        try:
            nutrition_contract = json.loads(nutrition_candidates[-1].read_text(encoding="utf-8-sig"))
        except Exception as exc:
            fail("nutrition contract 无法读取: " + str(exc))
        if not isinstance(nutrition_contract, dict) or nutrition_contract.get("schema_version") != 2:
            fail("nutrition contract 必须是 schema_version=2 的对象")
    elif isinstance(prev.get("nutrition_contract"), dict):
        nutrition_contract = prev.get("nutrition_contract")
    integration_config = prev.get("integrations") if isinstance(prev.get("integrations"), dict) else {"cloudbase": {"enabled": False, "env_id": "", "publishable_key": "", "sdk": None, "region": "", "bucket_name": ""}}
    if args.integration_config:
        try:
            integration_config = json.loads(Path(args.integration_config).read_text(encoding="utf-8"))
        except Exception as exc:
            fail("integration config 无法读取: " + str(exc))
    cloud_config = integration_config.get("cloudbase", {}) if isinstance(integration_config, dict) else {}
    if not isinstance(cloud_config, dict):
        fail("integration config.cloudbase 必须是对象")
    if cloud_config.get("enabled") is not True:
        integration_config = {"cloudbase": {"enabled": False, "env_id": "", "publishable_key": "", "sdk": None, "region": "", "bucket_name": ""}}
    data = {
        "schema": SCHEMA_VERSION,
        "meta": meta,
        "onboarding": onboarding,
        "system": dict(build_system_info(), instance_id=(prev.get("system", {}).get("instance_id") if isinstance(prev.get("system"), dict) else None) or str(uuid.uuid4())),
        "knowledge": build_knowledge_info(project),
        "status": build_status_info(baseline, meta, onboarding, find_latest_status_artifact(project)),
        "calendar": DEFAULT_CALENDAR,
        "weekday": DEFAULT_WEEKDAY,
        "done": build_done(timeline),
        "rest_days": "周三、周五、周日休息或轻活动（步行）",
        "days": days,
        "timeline": timeline,
        "week": build_week(plan_json, current_week),
        "phases": plan_json.get("phases", []),
        "charts": build_charts(plan_json, notion, review_documents),
        "goal_metrics": build_goal_metrics(plan_json, days, timeline, notion),
        "reviews": review_documents,
        "rules": ["%s：%s" % (r.get("title"), r.get("body")) for r in plan_json.get("rules", [])],
        "advice": build_advice(timeline, prev.get("advice")),
        "today_summary": build_today_summary(review_rows, timeline),
        "links": build_links(project, prev.get("links", {}), notion),
        "documents": build_portable_documents(project),
        "notion": notion or {
            "sync_mode": None,
            "source_queried_at": None,
            "latest_training_record_date": None,
            "latest_bodyweight_record_date": None,
            "snapshot_generated_at": None,
            "last_sync": None,
            "bodyweight": [],
            "baseline_kg": None,
            "baseline_note": None,
            "sessions": [],
            "activity": [],
            "note": "Notion 数据未提供；页面将显示待同步状态。",
        },
        "sync": sync,
        "nutrition_contract": nutrition_contract,
        "integrations": integration_config,
        "provenance": build_provenance(plan_path, baseline, review_rows, sync, project),
    }
    if not onboarding["completed"]:
        for day in data["days"].values():
            for exercise in day.get("exercises", []):
                exercise["w"] = None
                exercise["weight_source"] = (
                    "待校准：首练试组后确认工作重量"
                    if onboarding["mode"] == "needs_calibration"
                    else "待建档：示例重量不可作为处方"
                )
    problems = validate(data, plan_json, project)
    if problems:
        fail("；".join(problems))

    if args.out:
        if args.out == "-":
            print(json.dumps(data, ensure_ascii=True))
        else:
            with open(args.out, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            print("workbench-data written: " + args.out)
    if args.apply:
        apply_data(html_path, data, args.backup_dir)
        print("FITNESS_WORKBENCH_DATA: PASS (applied, schema %d, source %s, week W%d)" %
              (data["schema"], data["meta"]["source_version"], current_week))
    if args.check_only:
        print("FITNESS_WORKBENCH_DATA: PASS (schema %d, source %s, week W%d, reviews %d)" %
              (data["schema"], data["meta"]["source_version"], current_week, len(data["reviews"])))
        sys.exit(0)


if __name__ == "__main__":
    main()
