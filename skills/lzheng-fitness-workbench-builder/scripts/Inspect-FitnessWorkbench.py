#!/usr/bin/env python3
"""Emit a compact, read-only workbench summary for AI agents.

The formal workbench is a large single-file application. Routine planning and
review tasks should inspect this summary instead of loading the full HTML into
model context.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote


DATA_BLOCK = re.compile(
    r'<script id="workbench-data" type="application/json">([\s\S]*?)</script>'
)
TEMPLATE_MARKER = 'data-ui-template="lzheng-fitness-workbench-v3"'
NAV_LABELS = ("训练", "计划", "负荷", "复盘", "指南")
SECTION_IDS = ("m-today", "m-week", "m-trend", "m-record", "m-settings")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


class InspectError(RuntimeError):
    pass


def load_workbench(project: Path) -> tuple[str, dict]:
    html_path = project / "健身工作台.html"
    if not html_path.is_file():
        raise InspectError("缺少健身工作台.html")
    html = html_path.read_text(encoding="utf-8")
    blocks = DATA_BLOCK.findall(html)
    if len(blocks) != 1:
        raise InspectError(f"workbench-data 数量异常：{len(blocks)}")
    try:
        data = json.loads(blocks[0])
    except json.JSONDecodeError as exc:
        raise InspectError(f"workbench-data 无法解析：{exc}") from exc
    if not isinstance(data, dict):
        raise InspectError("workbench-data 顶层必须是对象")
    return html, data


def shell_summary(html: str) -> dict:
    from workbench_ui import nav_items, NAV, identity
    labels = [label for _, label in nav_items(html)]
    checks = {
        "template_marker": TEMPLATE_MARKER in html,
        "nav_container": len(NAV.findall(html)) == 1,
        "nav_labels": tuple(labels) == NAV_LABELS,
        "nav_initializer": '<script id="workbench-shell">' in html,
        "sections": all(re.search(rf'id=["\']{re.escape(section)}["\']', html) for section in SECTION_IDS),
    }
    required = ("template_marker", "nav_container", "nav_labels", "nav_initializer", "sections")
    return {"ok": all(checks[name] for name in required), "checks": checks, **identity(html)}


def compact_exercises(day: object) -> list[dict]:
    if not isinstance(day, dict):
        return []
    result = []
    for exercise in day.get("exercises", []):
        if not isinstance(exercise, dict):
            continue
        result.append(
            {
                "name": exercise.get("name"),
                "weight": exercise.get("w"),
                "prescription": exercise.get("d"),
                "effort": exercise.get("rpe"),
                "main": bool(exercise.get("main")),
            }
        )
    return result


def select_training(data: dict) -> tuple[dict | None, dict | None]:
    today = dt.date.today().isoformat()
    timeline = [item for item in data.get("timeline", []) if isinstance(item, dict)]
    current = next((item for item in timeline if item.get("date") == today), None)
    upcoming_start = today if not current or current.get("type") != "training" else "9999-12-31"
    future_timeline = timeline if upcoming_start == today else [item for item in timeline if str(item.get("date") or "") > today]
    upcoming = next(
        (
            item
            for item in future_timeline
            if item.get("type") == "training"
            and str(item.get("date") or "") >= today
            and item.get("status") != "done"
        ),
        None,
    )
    return current, upcoming


def training_summary(item: dict | None, days: object) -> dict | None:
    if not item:
        return None
    day_name = item.get("day")
    day = days.get(day_name, {}) if isinstance(days, dict) else {}
    return {
        "date": item.get("date"),
        "type": item.get("type"),
        "status": item.get("status"),
        "day": day_name,
        "title": item.get("title") or (day.get("title") if isinstance(day, dict) else None),
        "exercises": compact_exercises(day),
    }


def safe_source(value: object) -> str | None:
    text = unquote(str(value or "")).replace("\\", "/")
    if not text or re.match(r"^[A-Za-z]:/", text) or text.startswith(("/", "//", "../")):
        return None
    return text


def compact_review(review: dict | None) -> dict | None:
    if not review:
        return None
    return {
        key: review.get(key)
        for key in ("date", "full_date", "week", "day", "verdict", "status", "file_path")
        if review.get(key) is not None
    }


def build_summary(project: Path) -> dict:
    html, data = load_workbench(project)
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    status = data.get("status") if isinstance(data.get("status"), dict) else {}
    onboarding = data.get("onboarding") if isinstance(data.get("onboarding"), dict) else {}
    sync = data.get("sync") if isinstance(data.get("sync"), dict) else {}
    provenance = data.get("provenance") if isinstance(data.get("provenance"), dict) else {}
    reviews = [item for item in data.get("reviews", []) if isinstance(item, dict)]
    current, upcoming = select_training(data)

    sources = {}
    for key in ("plan", "baseline", "reviews"):
        entry = provenance.get(key) if isinstance(provenance.get(key), dict) else {}
        source = safe_source(entry.get("source"))
        if source:
            sources[key] = source

    return {
        "kind": "lzheng_fitness_workbench_compact_summary",
        "schema": 1,
        "html_bytes": len(html.encode("utf-8")),
        "shell": shell_summary(html),
        "plan": {
            "title": meta.get("title"),
            "version": meta.get("source_version"),
            "objective_mode": meta.get("objective_mode"),
            "current_week": meta.get("current_week"),
            "total_weeks": meta.get("total_weeks"),
            "phase": meta.get("phase"),
            "start": meta.get("plan_start"),
            "end": meta.get("plan_end"),
        },
        "execution": {
            "state": status.get("state"),
            "effective_until": status.get("effective_until"),
            "onboarding_completed": onboarding.get("completed"),
        },
        "today": training_summary(current, data.get("days")),
        "next_training": training_summary(upcoming, data.get("days")),
        "reviews": {
            "count": len(reviews),
            "latest": compact_review(reviews[0] if reviews else None),
        },
        "sync": {
            "status": sync.get("status"),
            "source_state": sync.get("source_state"),
            "last_success": sync.get("last_success"),
            "stale_fields": sync.get("stale_fields", []),
        },
        "authoritative_sources": sources,
        "agent_read_rule": "仅按 authoritative_sources 读取本次需要的主源；日常任务不要读取整份健身工作台.html。",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    try:
        summary = build_summary(Path(args.project).resolve())
    except InspectError as exc:
        print("FITNESS_WORKBENCH_INSPECT: FAIL")
        print("- " + str(exc))
        return 1
    if args.pretty:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
