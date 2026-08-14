#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Adapt the universal lzheng-fitness-plan plan_contract for the workbench builder."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any


ALLOWED_GOAL_MODES = {"strength", "hypertrophy", "fat_loss", "general_fitness"}


def is_plan_contract(value: Any) -> bool:
    return isinstance(value, dict) and isinstance(value.get("plan_meta"), dict) and isinstance(value.get("training_days"), list)


def load_text(exercise: dict[str, Any]) -> tuple[str, str]:
    prescription = exercise.get("prescription", {})
    load = exercise.get("load", {})
    sets = f"{prescription.get('sets', '')}×{prescription.get('reps', '')}".strip("×")
    if load.get("status") == "verified":
        value = f"{load.get('working_weight', '')}{load.get('unit', '')}".strip()
        return f"{value} {sets}".strip(), "verified"
    if load.get("status") == "calibration_required":
        return "待校准：" + str(load.get("starting_instruction", "先按校准引导确定工作重量")), "calibration_required"
    return sets, "not_weight_based"


def adapt(contract: dict[str, Any], start_date: str | None = None) -> dict[str, Any]:
    if not is_plan_contract(contract):
        raise ValueError("input is not a plan_contract")
    meta = contract["plan_meta"]
    goals = contract.get("goals", {})
    selected = dt.date.fromisoformat(start_date) if start_date else dt.date.fromisoformat(str(meta.get("generated_at", dt.date.today().isoformat()))[:10])
    monday = selected - dt.timedelta(days=selected.weekday())
    by_id = {item.get("id"): item for item in contract.get("training_days", [])}
    schedule: list[dict[str, Any]] = []
    for item in contract.get("weekly_schedule", []):
        index = int(item.get("day_index", 1))
        current = monday + dt.timedelta(days=max(0, index - 1))
        day = by_id.get(item.get("day_id"))
        if not day:
            schedule.append({"day": current.strftime("%m-%d"), "theme": item.get("theme", "恢复／轻活动"), "role": "恢复与轻活动"})
            continue
        exercises = []
        for exercise in day.get("exercises", []):
            sets, load_status = load_text(exercise)
            prescription = exercise.get("prescription", {})
            exercises.append({
                "name": exercise.get("name"),
                "sets": sets,
                "planned_sets": prescription.get("sets"),
                "target": f"{prescription.get('intensity', '')}；休息 {prescription.get('rest', '')}".strip("；"),
                "priority": exercise.get("priority", "optional"),
                "load_status": load_status,
                "load_source": exercise.get("load", {}).get("source"),
                "muscle_groups": exercise.get("muscle_groups", []),
            })
        schedule.append({
            "day": current.strftime("%m-%d"),
            "day_key": day.get("title") or item.get("theme"),
            "theme": item.get("theme") or day.get("theme"),
            "role": day.get("role", ""),
            "label": "W1 " + str(day.get("title", "训练日")),
            "title": day.get("title"),
            "exercises": exercises,
        })
    mode = str(meta.get("goal_mode") or "general_fitness")
    if mode not in ALLOWED_GOAL_MODES:
        raise ValueError("plan_meta.goal_mode must be strength, hypertrophy, fat_loss, or general_fitness")
    rules = [{"title": item.get("scope", "渐进规则"), "body": item.get("action", "按动作质量与目标次数推进")} for item in contract.get("progression_rules", [])]
    rules.append({"title": "负荷校准", "body": "待校准动作按页面引导确定重量；完成后写入实际重量、次数、余力和动作质量。"})
    return {
        "plan": {
            "title": meta.get("title", "个人训练计划"),
            "subtitle": meta.get("subtitle", meta.get("phase_goal", "")),
            "weeks": meta.get("weeks", 4),
            "athlete": meta.get("subject_id", "使用者"),
            "goal": goals.get("primary", meta.get("phase_goal", "")),
            "frequency": meta.get("frequency", "待确认"),
            "constraints": "由 plan_contract 自动适配；未知重量必须先完成校准。",
            "baseline": "计划事实来自已确认的状态快照和动作负荷记录。",
            "objective_mode": mode,
            "tracking_targets": contract.get("tracking_targets", []),
            "metrics": [{"value": meta.get("frequency", ""), "label": "训练频率"}, {"value": f"{meta.get('weeks', 4)} 周", "label": "当前计划"}],
        },
        "phases": [{"label": "执行", "start_week": 1, "end_week": meta.get("weeks", 4)}],
        "schedule": schedule,
        "cycles": [],
        "rules": rules,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan_contract", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--start-date")
    args = parser.parse_args()
    if args.output.exists():
        print("ERROR: refusing to overwrite existing file: " + str(args.output))
        return 2
    value = json.loads(args.plan_contract.read_text(encoding="utf-8-sig"))
    adapted = adapt(value, args.start_date)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(adapted, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("OK: adapted plan_contract to workbench plan: " + str(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
