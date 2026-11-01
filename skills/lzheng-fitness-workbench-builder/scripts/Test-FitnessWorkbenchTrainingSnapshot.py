"""Anonymous regression fixtures for the two training snapshot formats."""
import copy
import importlib.util
import json
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("builder", HERE / "Build-FitnessWorkbenchData.py")
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
from training_snapshot import load_snapshot

plan = {"plan": {"objective_mode": "fat_loss", "week_policy": "monday_sunday",
                  "calendar_anchor": "2026-01-05", "main_lift_day_map": {"卧推": "推A"}},
        "schedule": [], "cycles": []}
raw = {"source": "fitness_cloud.training_snapshot", "queried_at": "2026-01-12T10:00:00+08:00",
       "snapshot": {"revision": 7, "hash": "fixture-revision-hash", "pagination": {
           "offset": 0, "hasMore": False, "total": 1}, "activeSession": None, "history": [{
               "id": "session-1", "title": "推A｜上肢", "status": "draft", "cycleWeek": 1,
               "startedAt": 1768150800000, "exercises": [{"id": "bench", "name": "杠铃卧推｜顶组",
                   "pendingDraft": {"reps": 99}, "recordedSets": [
                       {"setIndex": 1, "weight": 40, "reps": 3, "rpe": 7, "completed": True},
                       {"setIndex": 2, "weight": 40, "reps": 0, "rpe": 10, "completed": True},
                       {"setIndex": 3, "weight": 40, "reps": 3, "completed": False}]}]}]}}

with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp) / "anonymous-snapshot.json"
    def save(value):
        path.write_text(json.dumps(value), encoding="utf-8")
    save(raw)
    rows = load_snapshot(path, plan)
    assert rows["sessions"][0]["training_date"] == "2026-01-12"  # +08 boundary
    assert rows["sessions"][0]["source_cycle_week"] == 1
    assert rows["sessions"][0]["week_number"] == 2
    actual = b.actual_training_from_snapshot(path, plan)
    assert actual["sessions"][0]["recorded_sets"] == 1
    assert actual["sessions"][0]["status"] == "draft"
    assert actual["records"][0]["read_only_snapshot"] is True
    assert len(actual["records"][0]["exercises"][0]["sets"]) == 1
    assert actual["main_lifts"][0]["value"] == 40
    assert actual["source"] == raw["source"] and actual["revision"] == 7
    for edit in ("partial", "duplicate", "negative", "nan", "rpe", "fractional"):
        bad = copy.deepcopy(raw)
        sets = bad["snapshot"]["history"][0]["exercises"][0]["recordedSets"]
        if edit == "partial": bad["snapshot"]["pagination"]["hasMore"] = True
        if edit == "duplicate": bad["snapshot"]["history"].append(bad["snapshot"]["history"][0]); bad["snapshot"]["pagination"]["total"] = 2
        if edit == "negative": sets[0]["reps"] = -1
        if edit == "nan": sets[0]["weight"] = float("nan")
        if edit == "rpe": sets[0]["rpe"] = 11
        if edit == "fractional": sets[0]["reps"] = 2.5
        save(bad)
        try: load_snapshot(path, plan)
        except ValueError: pass
        else: raise AssertionError("Accepted invalid fixture: " + edit)
    # An unfinished active session with an actual warmup is retained, not finalized.
    bad = copy.deepcopy(raw)
    active = copy.deepcopy(bad["snapshot"]["history"][0]); active["id"] = "active"
    active["exercises"][0]["name"] = "杠铃卧推｜热身"
    active["exercises"][0]["recordedSets"] = [{"setIndex": 1, "weight": 20, "reps": 5, "rpe": None, "completed": True}]
    bad["snapshot"]["activeSession"] = active
    save(bad); actual = b.actual_training_from_snapshot(path, plan)
    assert len(actual["sessions"]) == 2 and len(actual["main_lifts"]) == 1
    # Preserve the existing SQL input, including actual replacements.
    sql = {"source": "CloudBase PostgreSQL", "queried_at": raw["queried_at"],
           "sessions": [{"id": "sql", "training_date": "2026-01-12", "training_day": "推A", "week_number": 2, "status": "draft", "client_revision": 3}],
           "exercises": [{"id": "ex", "session_id": "sql", "planned_name": "杠铃卧推", "actual_name": "器械推胸"}],
           "sets": [{"id": "set", "exercise_id": "ex", "set_number": 1, "weight": 20, "reps": 8, "rpe": 7, "is_completed": True}]}
    save(sql); actual = b.actual_training_from_snapshot(path, plan)
    assert actual["sessions"][0]["recorded_sets"] == 1 and not actual["main_lifts"]
    assert actual["records"][0]["exercises"][0]["actual_name"] == "器械推胸"
print("FITNESS_WORKBENCH_TRAINING_SNAPSHOT: PASS")
