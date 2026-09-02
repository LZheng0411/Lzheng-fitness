#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Focused regression gate for safe Notion snapshot merging."""
import copy
import importlib.util
import sys
from pathlib import Path

sys.dont_write_bytecode = True
BUILDER_PATH = Path(__file__).with_name("Build-FitnessWorkbenchData.py")
SPEC = importlib.util.spec_from_file_location("fitness_workbench_builder", BUILDER_PATH)
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


def previous_payload():
    return {
        "sync_mode": "incremental",
        "source_queried_at": "2026-08-22T10:00:00+08:00",
        "latest_training_record_date": "2026-08-08",
        "latest_bodyweight_record_date": "2026-08-08",
        "snapshot_generated_at": "2026-08-22T10:01:00+08:00",
        "bodyweight": [{"date": "2026-08-08", "kg": 66.8, "note": "晨起"}],
        "sessions": [{"date": "08-08", "day": "推A", "result": "完成"}],
        "latest_by_exercise": {"杠铃卧推": {"weight": "60kg"}},
        "main_lifts": [{"name": "杠铃卧推", "week": 1, "value": 60, "date": "08-08"}],
        "activity": [{"date": "2026-08-08", "steps": 8000, "cardio_minutes": 20}],
    }


def incremental_payload():
    return {
        "sync_mode": "incremental",
        "source_queried_at": "2026-08-23T10:00:00+08:00",
        "latest_training_record_date": "2026-08-15",
        "latest_bodyweight_record_date": "2026-08-15",
        "snapshot_generated_at": "2026-08-23T10:01:00+08:00",
        "bodyweight": [{"date": "2026-08-15", "kg": 67.0, "note": "晨起"}],
        "sessions": [{"date": "2026-08-15", "day": "推A", "result": "完成"}],
        "latest_by_exercise": {"卧推": {"weight": "62.5kg"}},
        "main_lifts": [{"name": "卧推", "week": 2, "value": 62.5, "date": "08-15"}],
        "activity": [{"date": "2026-08-15", "steps": 9000, "cardio_minutes": 25}],
    }


def require_conflict(callable_, marker):
    try:
        callable_()
    except BUILDER.NotionSyncConflict as exc:
        if marker not in str(exc):
            raise AssertionError("expected conflict containing %r; got %r" % (marker, str(exc)))
        return
    raise AssertionError("expected NotionSyncConflict containing %r" % marker)


def test_incremental_merge_and_metadata():
    merged = BUILDER.merge_notion_history(previous_payload(), incremental_payload(), mode="incremental")
    assert merged["source_queried_at"] == "2026-08-23T10:00:00+08:00"
    assert merged["last_sync"] == merged["source_queried_at"]
    assert merged["snapshot_generated_at"] == "2026-08-23T10:01:00+08:00"
    assert merged["latest_training_record_date"] == "2026-08-15"
    assert len(merged["bodyweight"]) == 2
    assert len(merged["sessions"]) == 2
    assert len(merged["activity"]) == 2
    assert [(row["name"], row["week"]) for row in merged["main_lifts"]] == [("卧推", 1), ("卧推", 2)]
    assert [row["date"] for row in merged["sessions"]] == ["2026-08-08", "2026-08-15"]
    assert [row["date"] for row in merged["main_lifts"]] == ["2026-08-08", "2026-08-15"]
    assert merged["latest_by_exercise"] == {"卧推": {"weight": "62.5kg"}}
    assert BUILDER.parse_sync_date("2026/8/23 14:21:14") == BUILDER.dt.date(2026, 8, 23)


def test_stable_key_conflicts_are_rejected():
    activity_conflict = incremental_payload()
    activity_conflict["activity"] = [{"date": "2026-08-08", "steps": 8100, "cardio_minutes": 20}]
    require_conflict(
        lambda: BUILDER.merge_notion_history(previous_payload(), activity_conflict, mode="incremental"),
        "activity 历史发生冲突",
    )

    lift_conflict = incremental_payload()
    lift_conflict["main_lifts"] = [{"name": "卧推", "week": 1, "value": 62.5, "date": "08-08"}]
    require_conflict(
        lambda: BUILDER.merge_notion_history(previous_payload(), lift_conflict, mode="incremental"),
        "--replace-main-lift-history",
    )

    session_conflict = incremental_payload()
    session_conflict["sessions"] = [{"date": "2026-08-08", "day": "推A", "result": "未完成"}]
    require_conflict(
        lambda: BUILDER.merge_notion_history(previous_payload(), session_conflict, mode="incremental"),
        "sessions 历史发生冲突",
    )


def test_full_snapshot_cannot_silently_shrink_history():
    incomplete = incremental_payload()
    incomplete["sync_mode"] = "full"
    require_conflict(
        lambda: BUILDER.merge_notion_history(previous_payload(), incomplete, mode="full"),
        "full 输入缺少既有 bodyweight 稳定键",
    )


def test_authoritative_main_lift_replacement_requires_full():
    require_conflict(
        lambda: BUILDER.merge_notion_history(
            previous_payload(), incremental_payload(), mode="incremental", replace_main_lifts=True
        ),
        "只允许用于 full",
    )

    complete = copy.deepcopy(previous_payload())
    complete.update({
        "sync_mode": "full",
        "source_queried_at": "2026-08-23T10:00:00+08:00",
        "snapshot_generated_at": "2026-08-23T10:01:00+08:00",
        "main_lifts": [{"name": "卧推", "week": 1, "value": 61.25, "date": "08-08", "detail": "人工核验纠错"}],
    })
    replaced = BUILDER.merge_notion_history(
        previous_payload(), complete, mode="full", replace_main_lifts=True
    )
    assert replaced["main_lifts"] == [
        {"name": "卧推", "week": 1, "value": 61.25, "date": "2026-08-08", "detail": "人工核验纠错"}
    ]


def test_cross_year_sessions_and_repeated_week_numbers_remain_distinct():
    payload = {
        "sync_mode": "incremental",
        "source_queried_at": "2026-08-23T10:00:00+08:00",
        "latest_training_record_date": "2026-08-15",
        "snapshot_generated_at": "2026-08-23T10:01:00+08:00",
        "sessions": [
            {"date": "2025-08-15", "day": "推A"},
            {"date": "2026-08-15", "day": "推A"},
        ],
        "main_lifts": [
            {"name": "卧推", "week": 1, "value": 55, "date": "2025-08-15"},
            {"name": "杠铃卧推", "week": 1, "value": 65, "date": "2026-08-15"},
        ],
    }
    normalized = BUILDER.normalize_notion_payload(payload)
    assert len(normalized["sessions"]) == 2
    assert len(normalized["main_lifts"]) == 2
    assert [row["date"] for row in normalized["sessions"]] == ["2025-08-15", "2026-08-15"]
    assert [row["date"] for row in normalized["main_lifts"]] == ["2025-08-15", "2026-08-15"]


def test_legacy_month_day_deduplicates_with_same_year_full_date():
    previous = {
        "source_queried_at": "2026-08-22T10:00:00+08:00",
        "latest_training_record_date": "2026-08-15",
        "sessions": [{"date": "08-15", "day": "推A", "result": "完成"}],
        "main_lifts": [{"name": "杠铃卧推", "week": 3, "value": 65, "date": "08-15"}],
    }
    incoming = {
        "sync_mode": "incremental",
        "source_queried_at": "2026-08-23T10:00:00+08:00",
        "latest_training_record_date": "2026-08-15",
        "sessions": [{"date": "2026-08-15", "day": "推A", "result": "完成"}],
        "main_lifts": [{"name": "卧推", "week": 3, "value": 65, "date": "2026-08-15"}],
    }
    merged = BUILDER.merge_notion_history(previous, incoming, mode="incremental")
    assert merged["sessions"] == [{"date": "2026-08-15", "day": "推A", "result": "完成"}]
    assert merged["main_lifts"] == [{"name": "卧推", "week": 3, "value": 65, "date": "2026-08-15"}]


def test_v10_shaped_incremental_merge_is_lossless_and_idempotent():
    session_dates = [
        "2026-07-27", "2026-07-28", "2026-07-30", "2026-08-01", "2026-08-03", "2026-08-04",
        "2026-08-06", "2026-08-08", "2026-08-11", "2026-08-12", "2026-08-14", "2026-08-15",
    ]
    days = ["上肢A", "腿B", "上肢B", "腿A"]
    main_rows = [
        ("卧推", 1, 65, "2026-07-27"), ("硬拉", 1, 120, "2026-07-28"),
        ("负重引体", 1, 22.5, "2026-07-30"), ("深蹲", 1, 75, "2026-08-01"),
        ("卧推", 2, 65, "2026-08-03"), ("负重引体", 2, 23.5, "2026-08-06"),
        ("深蹲", 2, 77.5, "2026-08-08"), ("卧推", 3, 75, "2026-08-12"),
        ("深蹲", 3, 85, "2026-08-14"), ("负重引体", 3, 26.5, "2026-08-15"),
    ]
    previous = {
        "source_queried_at": "2026-08-22T10:00:00+08:00",
        "latest_training_record_date": "2026-08-15",
        "sessions": [{"date": date, "day": days[index % len(days)]} for index, date in enumerate(session_dates)],
        "main_lifts": [
            {"name": name, "week": week, "value": value, "date": date}
            for name, week, value, date in main_rows
        ],
    }
    incoming = {
        "sync_mode": "incremental",
        "source_queried_at": "2026-08-23T10:00:00+08:00",
        "latest_training_record_date": "2026-08-15",
        "sessions": copy.deepcopy(previous["sessions"][1:]),
        "main_lifts": copy.deepcopy(previous["main_lifts"][-3:]),
    }
    merged = BUILDER.merge_notion_history(previous, incoming, mode="incremental")
    assert len(merged["sessions"]) == 12
    assert len(merged["main_lifts"]) == 10
    assert BUILDER.merge_notion_history(merged, incoming, mode="incremental") == merged


def test_modes_must_be_consistent():
    assert BUILDER.resolve_notion_mode(None, {"sync_mode": "incremental"}) == ("incremental", True)
    assert BUILDER.resolve_notion_mode(None, {"last_sync": "2026-08-22"}) == ("incremental", False)
    require_conflict(
        lambda: BUILDER.resolve_notion_mode("full", {"sync_mode": "incremental"}),
        "不一致",
    )


def test_cached_rebuild_preserves_query_success_times():
    notion = BUILDER.normalize_notion_payload(previous_payload())
    previous_sync = {
        "last_success": "2026-08-22T10:00:00+08:00",
        "last_attempt": "2026-08-22T10:02:00+08:00",
    }
    sync = BUILDER.build_sync_metadata(
        notion, previous_sync, "cached", "preserved", objective_mode="strength", attempted_at="2099-01-01T00:00:00+08:00"
    )
    assert sync["source_state"] == "cached"
    assert sync["merge_mode"] == "preserved"
    assert sync["source_queried_at"] == "2026-08-22T10:00:00+08:00"
    assert sync["last_success"] == previous_sync["last_success"]
    assert sync["last_attempt"] == previous_sync["last_attempt"]
    assert "cached/preserved" in sync["reason"]


def test_strength_truth_uses_plan_mapping():
    plan = {"plan": {"main_lift_day_map": {"杠铃卧推": "推A"}}}
    notion = {
        "sessions": [{"date": "2026-08-08", "day": "推A"}],
        "main_lifts": [{"name": "卧推", "week": 1, "value": 60, "date": "2026-08-08"}],
    }
    assert BUILDER.validate_main_lift_history(notion, 1, plan) == []
    wrong = copy.deepcopy(notion)
    wrong["sessions"][0]["day"] = "上肢A"
    problems = BUILDER.validate_main_lift_history(wrong, 1, plan)
    assert any("计划映射推A" in problem for problem in problems), problems


def test_non_strength_modes_do_not_apply_strength_truth_contract():
    plan = {
        "plan": {
            "objective_mode": "hypertrophy",
            "main_lift_day_map": {"杠铃卧推": "推A"},
        }
    }
    historical = {
        "sessions": [{"date": "08-08", "day": "其他训练日"}],
        "main_lifts": [{"name": "卧推", "week": 1, "value": 60, "date": "08-08"}],
    }
    assert BUILDER.strength_history_validation_enabled(plan) is False
    assert BUILDER.validate_main_lift_history(historical, 1, plan) == []


def test_dated_advice_is_not_inherited_across_schedule_changes():
    timeline = [{"date": BUILDER.dt.date.today().isoformat(), "type": "training", "day": "腿A"}]
    advice = BUILDER.build_advice(timeline, "今日 08-22 周六 W5 腿A，按旧处方执行。")
    assert "08-22" not in advice
    assert "腿A" in advice


def main():
    tests = [
        test_incremental_merge_and_metadata,
        test_stable_key_conflicts_are_rejected,
        test_full_snapshot_cannot_silently_shrink_history,
        test_authoritative_main_lift_replacement_requires_full,
        test_cross_year_sessions_and_repeated_week_numbers_remain_distinct,
        test_legacy_month_day_deduplicates_with_same_year_full_date,
        test_v10_shaped_incremental_merge_is_lossless_and_idempotent,
        test_modes_must_be_consistent,
        test_cached_rebuild_preserves_query_success_times,
        test_strength_truth_uses_plan_mapping,
        test_non_strength_modes_do_not_apply_strength_truth_contract,
        test_dated_advice_is_not_inherited_across_schedule_changes,
    ]
    for test in tests:
        test()
    print("FITNESS_WORKBENCH_NOTION_SYNC: PASS (%d cases)" % len(tests))


if __name__ == "__main__":
    main()
