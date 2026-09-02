#!/usr/bin/env python3
"""Portable nutrition calculations and contract negative fixtures."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
validator_spec = importlib.util.spec_from_file_location("nutrition_validator", Path(__file__).with_name("validate_nutrition_contract.py"))
validator = importlib.util.module_from_spec(validator_spec)
assert validator_spec.loader
validator_spec.loader.exec_module(validator)


def bmr(weight: float, height: float, age: int, sex: str) -> float:
    offset = 5 if sex == "male" else -161
    return 10 * weight + 6.25 * height - 5 * age + offset


def main() -> None:
    example = json.loads((ROOT / "assets/examples/nutrition-contract.example.json").read_text(encoding="utf-8"))
    assert validator.validate(example) == []
    assert round(bmr(80, 180, 30, "male")) == 1780
    assert round(bmr(60, 165, 30, "female")) == 1320

    broken = copy.deepcopy(example)
    broken["tracking"]["confirmed_meals_only"] = False
    assert any("confirmed_nutrition" in item for item in validator.validate(broken))
    broken = copy.deepcopy(example)
    broken["review_rules"]["max_single_adjustment_kcal"] = 300
    assert any("150" in item for item in validator.validate(broken))
    print("NUTRITION_SYSTEM_TEST: PASS")


if __name__ == "__main__":
    main()
