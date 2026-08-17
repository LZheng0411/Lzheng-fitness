#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Public regression gate for schedule-to-workbench week transitions."""
import copy
import datetime as dt
import importlib.util
import sys
from pathlib import Path

sys.dont_write_bytecode = True
BUILDER_PATH = Path(__file__).with_name("Build-FitnessWorkbenchData.py")
SPEC = importlib.util.spec_from_file_location("fitness_workbench_builder", BUILDER_PATH)
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


def sample_plan():
    return {
        "plan": {"frequency": "每周 4 练"},
        "phases": [{"start_week": 4, "end_week": 4, "label": "减量"}],
        "schedule": [
            {"day": "08-17 周一", "label": "W4", "theme": "推A", "day_key": "推A", "exercises": [
                {"name": "卧推", "sets": "60kg 3×4"},
                {"name": "引体向上", "sets": "自重 3×5"},
            ]},
            {"day": "08-18 周二", "label": "W4", "theme": "下肢A", "day_key": "下肢A", "exercises": [{"name": "深蹲", "sets": "90kg 3×3"}]},
            {"day": "08-19 周三", "theme": "恢复"},
            {"day": "08-20 周四", "label": "W4", "theme": "拉A", "day_key": "拉A", "exercises": [{"name": "划船", "sets": "50kg 3×6"}]},
            {"day": "08-21 周五", "theme": "恢复"},
            {"day": "08-22 周六", "label": "W4", "theme": "下肢B", "day_key": "下肢B", "exercises": [{"name": "硬拉", "sets": "110kg 3×3"}]},
            {"day": "08-23 周日", "theme": "恢复"},
        ],
    }


def sample_data():
    return {
        "meta": {"plan_start": "2026-08-10", "current_week": 4, "phase": "减量"},
        "status": {"state": "active"},
        "timeline": [
            {"date": "2026-08-17", "type": "training", "day": "推A", "status": "planned"},
            {"date": "2026-08-18", "type": "training", "day": "下肢A", "status": "planned"},
            {"date": "2026-08-19", "type": "recovery"},
            {"date": "2026-08-20", "type": "training", "day": "拉A", "status": "planned"},
            {"date": "2026-08-21", "type": "recovery"},
            {"date": "2026-08-22", "type": "training", "day": "下肢B", "status": "planned"},
            {"date": "2026-08-23", "type": "recovery"},
        ],
        "days": {
            "推A": {"date": "2026-08-17", "exercises": [{"name": "卧推", "w": "60kg"}, {"name": "引体向上", "w": "自重", "weight_source": None}]},
            "下肢A": {"date": "2026-08-18", "exercises": [{"name": "深蹲", "w": "90kg"}]},
            "拉A": {"date": "2026-08-20", "exercises": [{"name": "划船", "w": "50kg"}]},
            "下肢B": {"date": "2026-08-22", "exercises": [{"name": "硬拉", "w": "110kg"}]},
        },
    }


def require_problem(problems, marker):
    if not any(marker in problem for problem in problems):
        raise AssertionError("missing expected rejection %r; got %r" % (marker, problems))


def main():
    today = dt.date(2026, 8, 17)
    plan = sample_plan()
    data = sample_data()
    assert BUILDER.validate_week_transition_contract(data, plan, today) == []
    assert BUILDER.current_week_from_schedule(plan, "2026-08-10", dt.date(2026, 8, 23)) == 4

    stale = copy.deepcopy(plan)
    for item, old_date in zip(stale["schedule"], ["08-10", "08-11", "08-12", "08-13", "08-14", "08-15", "08-16"]):
        item["day"] = old_date + item["day"][5:]
    require_problem(BUILDER.validate_week_transition_contract(data, stale, today), "当前排程未覆盖今天")

    mixed = copy.deepcopy(plan)
    mixed["schedule"][1]["label"] = "W3"
    require_problem(BUILDER.validate_week_transition_contract(data, mixed, today), "周次不唯一")

    wrong_frequency = copy.deepcopy(plan)
    wrong_frequency["schedule"].pop(5)
    require_problem(BUILDER.validate_week_transition_contract(data, wrong_frequency, today), "plan.frequency 不一致")

    missing_today = copy.deepcopy(data)
    missing_today["timeline"] = [item for item in missing_today["timeline"] if item.get("date") != "2026-08-17"]
    require_problem(BUILDER.validate_week_transition_contract(missing_today, plan, today), "今天是计划训练日但今日处方缺失")

    overwritten = copy.deepcopy(data)
    overwritten["days"]["推A"]["exercises"][1] = {"name": "引体向上", "w": "+10kg", "weight_source": "recent history"}
    require_problem(BUILDER.validate_week_transition_contract(overwritten, plan, today), "处方明确为自重却被历史负重覆盖")

    print("FITNESS_WORKBENCH_WEEK_TRANSITION: PASS")


if __name__ == "__main__":
    main()
