#!/usr/bin/env python3
"""Select the minimum source modules for explicit training variables."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "references" / "expert-registry.json"

ROUTES = {
    "nutrition": ("alan-aragon-flexible-dieting",),
    "nutrition_limited_hypertrophy": (
        "alan-aragon-flexible-dieting",
        "brad-schoenfeld-hypertrophy",
        "eric-helms-training-pyramid",
    ),
    "hypertrophy_measurement": ("brad-schoenfeld-hypertrophy",),
    "hypertrophy_programming": ("brad-schoenfeld-hypertrophy", "eric-helms-training-pyramid"),
    "general_program_structure": ("eric-helms-training-pyramid",),
    "strength_stall": ("greg-nuckols-strength-periodization", "eric-helms-training-pyramid"),
    "goal_conflict_or_repeated_interruption": ("dan-john-intervention-easy-strength",),
    "medically_cleared_return": ("brukner-khan-return-to-sport",),
}

SAFETY_BLOCKED = {
    "unassessed_pain",
    "acute_trauma",
    "post_surgery_without_clearance",
    "chest_discomfort",
    "syncope",
    "progressive_neurological_symptoms",
}


def select(variable: str) -> dict:
    if variable in SAFETY_BLOCKED:
        return {"variable": variable, "blocked": True, "experts": [], "reason": "safety_triage_first"}
    if variable not in ROUTES:
        return {"variable": variable, "blocked": False, "experts": [], "reason": "no_registered_route"}
    return {"variable": variable, "blocked": False, "experts": list(ROUTES[variable]), "reason": "minimum_relevant_sources"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Select Lzheng source-limited expert modules.")
    parser.add_argument("variable", choices=tuple(sorted(set(ROUTES) | SAFETY_BLOCKED)))
    args = parser.parse_args()

    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    available = {item["id"] for item in registry["experts"]}
    result = select(args.variable)
    missing = set(result["experts"]) - available
    if missing:
        raise SystemExit(f"Registry is missing routed experts: {sorted(missing)}")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
