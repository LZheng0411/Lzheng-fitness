#!/usr/bin/env python3
"""Safely migrate a workbench-data JSON object from schema 5 to schema 6."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from workbench_ui import suite_version


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8-sig"))
    if data.get("schema") not in (5, 6):
        raise SystemExit("只支持 schema 5 或 6")
    if data.get("schema") == 5:
        data.update({
            "schema": 6,
            "onboarding": {"completed": True, "mode": "migrated", "missing": [], "message": "由 schema 5 迁移；请在下一次构建时重新核验。", "review_count": len(data.get("reviews", []))},
            "system": {"suite_version": suite_version(), "workbench_schema": 6, "ui_contract": "v1", "last_health_check": None, "health": "unknown"},
            "knowledge": {"public_pack": {"schema": 1, "status": "unregistered", "source": None}, "private_pack": {"status": "not_loaded", "count": 0, "excluded_from_public_export": True}},
            "status": {"state": "unknown", "effective_until": data.get("meta", {}).get("plan_end"), "reason": "迁移后需重新构建核验。", "source": None},
            "provenance": {"plan": {"source": None, "verified_at": None, "trust": "migrated"}, "baseline": {"source": None, "verified_at": None, "trust": "migrated"}, "reviews": {"source": None, "verified_at": None, "trust": "migrated", "count": len(data.get("reviews", []))}, "notion": {"source": "optional_notion_export", "verified_at": None, "trust": "unknown"}},
        })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("FITNESS_WORKBENCH_SCHEMA_MIGRATION: PASS (schema 6)")


if __name__ == "__main__":
    main()
