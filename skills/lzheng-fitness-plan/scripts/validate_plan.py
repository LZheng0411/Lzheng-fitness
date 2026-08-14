#!/usr/bin/env python3
"""Validate the lzheng-fitness-plan JSON contract using only stdlib."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


REQUIRED_TOP = [
    "plan_meta",
    "profile_snapshot",
    "safety_status",
    "goals",
    "equipment",
    "movement_profile",
    "weekly_schedule",
    "training_days",
    "movement_coverage",
    "progression_rules",
    "minimum_versions",
    "short_interruption_rules",
    "cycle_links",
    "review_checkpoints",
    "knowledge_sources",
    "assumptions",
]


def load_plan(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"plan file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise ValueError("plan root must be an object")
    return value


def nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def find_forbidden_keys(value: Any, forbidden: set[str], path: str = "plan") -> list[str]:
    hits: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in forbidden:
                hits.append(child_path)
            hits.extend(find_forbidden_keys(child, forbidden, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            hits.extend(find_forbidden_keys(child, forbidden, f"{path}[{index}]"))
    return hits


def validate_plan(plan: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    for key in REQUIRED_TOP:
        if key not in plan:
            errors.append(f"missing top-level field: {key}")

    if errors:
        return errors, warnings

    meta = plan["plan_meta"]
    if not isinstance(meta, dict):
        errors.append("plan_meta must be an object")
    else:
        for key in ("plan_id", "title", "generated_at", "timezone", "subject_mode", "subject_id", "phase_goal"):
            if not nonempty_string(meta.get(key)):
                errors.append(f"plan_meta.{key} must be a non-empty string")
        if meta.get("subject_mode") not in {"personal", "client"}:
            errors.append("plan_meta.subject_mode must be personal or client")
        if meta.get("subject_mode") == "client":
            subject_id = str(meta.get("subject_id", ""))
            if not re.fullmatch(r"[A-Za-z0-9_-]{2,40}", subject_id):
                errors.append("client plan_meta.subject_id must be a de-identified code using only letters, digits, _ or -")
            forbidden_client_fields = {"real_name", "full_name", "phone", "email", "contact", "medical_history_raw"}
            leaked = find_forbidden_keys(plan, forbidden_client_fields)
            if leaked:
                errors.append(f"client plan contains forbidden identifying fields: {leaked}")
        if not isinstance(meta.get("weeks"), int) or meta.get("weeks", 0) < 1:
            errors.append("plan_meta.weeks must be a positive integer")

    snapshot = plan["profile_snapshot"]
    if not isinstance(snapshot, dict):
        errors.append("profile_snapshot must be an object")
        overall_stage = None
    else:
        for key in ("snapshot_id", "generated_at", "readiness", "overall_stage"):
            if not nonempty_string(snapshot.get(key)):
                errors.append(f"profile_snapshot.{key} must be a non-empty string")
        if snapshot.get("readiness") not in {"full", "conservative", "blocked"}:
            errors.append("profile_snapshot.readiness must be full, conservative, or blocked")
        if snapshot.get("overall_stage") not in {"P0", "L1", "L2", "L3"}:
            errors.append("profile_snapshot.overall_stage must be P0, L1, L2, or L3")
        overall_stage = snapshot.get("overall_stage")

    safety = plan["safety_status"]
    if not isinstance(safety, dict) or safety.get("status") not in {"clear", "caution", "blocked"}:
        errors.append("safety_status.status must be clear, caution, or blocked")

    tracking_targets = plan.get("tracking_targets")
    if tracking_targets is None:
        warnings.append("tracking_targets is absent; legacy plan will show only generic workbench signals")
    elif not isinstance(tracking_targets, list):
        errors.append("tracking_targets must be an array when provided")
    else:
        seen_tracking_ids: set[str] = set()
        for index, target in enumerate(tracking_targets):
            prefix = f"tracking_targets[{index}]"
            if not isinstance(target, dict):
                errors.append(f"{prefix} must be an object")
                continue
            for key in ("id", "label", "kind", "source", "status", "next_action"):
                if not nonempty_string(target.get(key)):
                    errors.append(f"{prefix}.{key} must be a non-empty string")
            target_id = target.get("id")
            if nonempty_string(target_id):
                if target_id in seen_tracking_ids:
                    errors.append(f"duplicate tracking target id: {target_id}")
                seen_tracking_ids.add(target_id)
            if target.get("status") not in {"confirmed", "needs_baseline"}:
                errors.append(f"{prefix}.status must be confirmed or needs_baseline")

    schedule = plan["weekly_schedule"]
    days = plan["training_days"]
    if not isinstance(schedule, list):
        errors.append("weekly_schedule must be an array")
        schedule = []
    if not isinstance(days, list):
        errors.append("training_days must be an array")
        days = []
    if isinstance(safety, dict) and safety.get("status") == "blocked" and days:
        errors.append("blocked safety status cannot contain normal training-day prescriptions")
    if isinstance(safety, dict) and safety.get("status") != "blocked" and not schedule:
        errors.append("weekly_schedule must be non-empty when safety status is not blocked")

    day_ids: set[str] = set()
    exercise_ids: set[str] = set()
    p0_deadlifts: list[str] = []
    p0_deadlift_evidence_missing: list[str] = []
    has_p0_deadlift = False
    for day_index, day in enumerate(days):
        prefix = f"training_days[{day_index}]"
        if not isinstance(day, dict):
            errors.append(f"{prefix} must be an object")
            continue
        day_id = day.get("id")
        if not nonempty_string(day_id):
            errors.append(f"{prefix}.id must be a non-empty string")
            continue
        if day_id in day_ids:
            errors.append(f"duplicate training day id: {day_id}")
        day_ids.add(day_id)
        for key in ("title", "theme", "duration"):
            if not nonempty_string(day.get(key)):
                errors.append(f"{prefix}.{key} must be a non-empty string")
        if "warmup" in day:
            warmup = day.get("warmup")
            if not isinstance(warmup, list) or not warmup or not all(nonempty_string(item) for item in warmup):
                errors.append(f"{prefix}.warmup must be a non-empty array of strings when provided")
        exercises = day.get("exercises")
        if not isinstance(exercises, list) or not exercises:
            errors.append(f"{prefix}.exercises must be a non-empty array")
            continue
        local_ids: set[str] = set()
        for ex_index, exercise in enumerate(exercises):
            ex_prefix = f"{prefix}.exercises[{ex_index}]"
            if not isinstance(exercise, dict):
                errors.append(f"{ex_prefix} must be an object")
                continue
            for key in ("id", "name", "pattern", "modality", "equipment", "purpose", "priority", "selection_reason"):
                if not nonempty_string(exercise.get(key)):
                    errors.append(f"{ex_prefix}.{key} must be a non-empty string")
            ex_id = exercise.get("id")
            if nonempty_string(ex_id):
                if ex_id in exercise_ids:
                    errors.append(f"duplicate exercise id: {ex_id}")
                exercise_ids.add(ex_id)
                local_ids.add(ex_id)
            if exercise.get("priority") not in {"main", "key", "optional"}:
                errors.append(f"{ex_prefix}.priority must be main, key, or optional")
            prescription = exercise.get("prescription")
            if not isinstance(prescription, dict):
                errors.append(f"{ex_prefix}.prescription must be an object")
            else:
                for key in ("sets", "reps", "intensity", "rest"):
                    if not nonempty_string(prescription.get(key)):
                        errors.append(f"{ex_prefix}.prescription.{key} must be a non-empty string")
            load = exercise.get("load")
            if not isinstance(load, dict):
                errors.append(f"{ex_prefix}.load must be an object; use verified, calibration_required, or not_weight_based")
            else:
                status = load.get("status")
                if status not in {"verified", "calibration_required", "not_weight_based"}:
                    errors.append(f"{ex_prefix}.load.status must be verified, calibration_required, or not_weight_based")
                elif status == "verified":
                    for key in ("working_weight", "unit", "next_rule", "source"):
                        if not nonempty_string(load.get(key)):
                            errors.append(f"{ex_prefix}.load.{key} must be a non-empty string when status is verified")
                elif status == "calibration_required":
                    for key in ("starting_instruction", "decision_rule"):
                        if not nonempty_string(load.get(key)):
                            errors.append(f"{ex_prefix}.load.{key} must be a non-empty string when calibration is required")
                elif status == "not_weight_based" and not nonempty_string(load.get("progression_metric")):
                    errors.append(f"{ex_prefix}.load.progression_metric must be a non-empty string when not weight based")
            name = str(exercise.get("name", ""))
            if overall_stage == "P0" and any(term in name for term in ("传统硬拉", "杠铃硬拉")):
                has_p0_deadlift = True
                if exercise.get("admission_confirmed") is not True:
                    p0_deadlifts.append(ex_prefix)
                evidence = exercise.get("admission_evidence")
                if not isinstance(evidence, list) or not any(nonempty_string(item) for item in evidence):
                    p0_deadlift_evidence_missing.append(ex_prefix)
        versions = day.get("minimum_versions")
        if not isinstance(versions, dict):
            errors.append(f"{prefix}.minimum_versions must be an object")
        else:
            for key in ("minutes_30", "minutes_20", "minutes_10"):
                version = versions.get(key)
                if not isinstance(version, dict):
                    errors.append(f"{prefix}.minimum_versions.{key} must be an object")
                    continue
                ids = version.get("exercise_ids")
                if not isinstance(ids, list):
                    errors.append(f"{prefix}.minimum_versions.{key}.exercise_ids must be an array")
                else:
                    unknown = [item for item in ids if item not in local_ids]
                    if unknown:
                        errors.append(f"{prefix}.minimum_versions.{key} references unknown exercise ids: {unknown}")

    if p0_deadlifts:
        errors.append("P0 plan includes conventional/barbell deadlift without admission_confirmed=true: " + ", ".join(p0_deadlifts))
    if p0_deadlift_evidence_missing:
        errors.append("P0 conventional/barbell deadlift must include non-empty admission_evidence: " + ", ".join(p0_deadlift_evidence_missing))
    if has_p0_deadlift and not any(
        isinstance(item, dict)
        and any(term in str(item.get("movement", "")) for term in ("硬拉", "髋铰链"))
        and item.get("admission_confirmed") is True
        and nonempty_string(item.get("evidence"))
        for item in plan.get("movement_profile", [])
    ):
        errors.append("P0 conventional/barbell deadlift requires a matching movement_profile admission record")

    for index, entry in enumerate(schedule):
        if not isinstance(entry, dict):
            errors.append(f"weekly_schedule[{index}] must be an object")
            continue
        ref = entry.get("day_id")
        if ref is not None and ref not in day_ids:
            errors.append(f"weekly_schedule[{index}].day_id references unknown day: {ref}")

    sources = plan["knowledge_sources"]
    if not isinstance(sources, list) or not sources:
        errors.append("knowledge_sources must be a non-empty array")
    else:
        has_local = False
        for index, source in enumerate(sources):
            prefix = f"knowledge_sources[{index}]"
            if not isinstance(source, dict):
                errors.append(f"{prefix} must be an object")
                continue
            for key in ("source_type", "source_title", "local_path_or_url", "chapter_or_section", "rule_used", "accessed_at", "evidence_role"):
                if not nonempty_string(source.get(key)):
                    errors.append(f"{prefix}.{key} must be a non-empty string")
            if source.get("source_type") in {"local_book", "local_rule", "local_record"}:
                has_local = True
        if not has_local:
            errors.append("knowledge_sources must include at least one actually used local source")

    cycles = plan["cycle_links"]
    if not isinstance(cycles, list):
        errors.append("cycle_links must be an array")
    else:
        for index, cycle in enumerate(cycles):
            if not isinstance(cycle, dict):
                errors.append(f"cycle_links[{index}] must be an object")
                continue
            if cycle.get("status") == "active" and cycle.get("explicit_user_request") is not True:
                errors.append(f"cycle_links[{index}] is active without explicit_user_request=true")
            if cycle.get("status") == "active" and cycle.get("skill") != "lzheng-strength-cycle-planner":
                errors.append(f"cycle_links[{index}].skill must be lzheng-strength-cycle-planner")

    if not isinstance(plan["movement_coverage"], list) or not plan["movement_coverage"]:
        warnings.append("movement_coverage is empty; verify that the plan intentionally omits coverage auditing")
    if not isinstance(plan["review_checkpoints"], list) or not plan["review_checkpoints"]:
        warnings.append("review_checkpoints is empty")
    if not isinstance(plan["assumptions"], list):
        errors.append("assumptions must be an array")

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()
    try:
        plan = load_plan(args.plan)
        errors, warnings = validate_plan(plan)
    except ValueError as exc:
        errors, warnings = [str(exc)], []

    if args.json_output:
        print(json.dumps({"valid": not errors, "errors": errors, "warnings": warnings}, ensure_ascii=False, indent=2))
    else:
        for message in errors:
            print(f"ERROR: {message}")
        for message in warnings:
            print(f"WARNING: {message}")
        if not errors:
            print(f"OK: plan contract valid ({len(warnings)} warning(s))")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
