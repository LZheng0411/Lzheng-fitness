#!/usr/bin/env python3
"""Validate a portable nutrition_contract without external dependencies."""

from __future__ import annotations

import json
import sys
from pathlib import Path


REQUIRED = ("meta", "profile", "calculation", "day_type_rules", "tracking", "review_rules", "sources")
DAY_TYPES = ("heavy_training", "normal_training", "rest", "needs_confirmation")
GOALS = ("fat_loss", "maintenance", "muscle_gain")


def validate(value: dict) -> list[str]:
    errors: list[str] = []
    if value.get("schema_version") != 2:
        errors.append("schema_version 必须为 2")
    for key in REQUIRED:
        if key not in value:
            errors.append("缺少字段: " + key)
    if errors:
        return errors

    meta = value["meta"]
    profile = value["profile"]
    calculation = value["calculation"]
    review = value["review_rules"]
    if meta.get("goal") not in GOALS:
        errors.append("meta.goal 必须是 fat_loss / maintenance / muscle_gain")
    if meta.get("status") not in ("awaiting_profile", "active", "needs_review"):
        errors.append("meta.status 不受支持")

    age = profile.get("age")
    if age is not None and not (18 <= age <= 100):
        errors.append("age 必须为 18–100 或 null")
    sex = profile.get("sex")
    if sex is not None and sex not in ("male", "female"):
        errors.append("sex 必须为 male / female 或 null")
    for key, low, high in (("height_cm", 120, 230), ("current_weight_kg", 35, 300)):
        number = profile.get(key)
        if number is not None and not (low <= number <= high):
            errors.append(f"{key} 超出可接受范围")

    if meta.get("status") == "active":
        for key in ("age", "sex", "height_cm", "current_weight_kg"):
            if profile.get(key) is None:
                errors.append("active 协议缺少 profile." + key)
        for key in ("activity_factor", "protein_g_per_kg", "fat_g_per_kg"):
            if calculation.get(key) is None:
                errors.append("active 协议缺少 calculation." + key)
    if calculation.get("minimum_observation_days", 0) < 14:
        errors.append("minimum_observation_days 不得少于 14")
    if abs(float(calculation.get("energy_adjustment_percent") or 0)) > 0.3:
        errors.append("energy_adjustment_percent 绝对值不得超过 0.30")

    rules = value["day_type_rules"]
    for day_type in DAY_TYPES:
        if day_type not in rules or not isinstance(rules[day_type].get("match"), list):
            errors.append("缺少日型规则: " + day_type)
    if review.get("minimum_days", 0) < 14:
        errors.append("review_rules.minimum_days 不得少于 14")
    if review.get("minimum_adherence_days_per_week", 0) < 5:
        errors.append("执行不足 5/7 天时不得自动调热量")
    if review.get("max_single_adjustment_kcal", 999) > 150:
        errors.append("单次调整不得超过 150 kcal")
    if value["tracking"].get("confirmed_meals_only") is not True:
        errors.append("日合计必须只读取 confirmed_nutrition")
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: validate_nutrition_contract.py <contract.json>", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    value = json.loads(path.read_text(encoding="utf-8"))
    errors = validate(value)
    if errors:
        print("NUTRITION_CONTRACT: FAIL")
        for error in errors:
            print("- " + error)
        return 1
    print("NUTRITION_CONTRACT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
