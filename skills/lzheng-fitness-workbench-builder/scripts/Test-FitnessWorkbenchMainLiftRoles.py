"""Regression: main-lift roles, single exposure selection, and source boundaries."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("curve_builder", Path(__file__).with_name("Build-FitnessWorkbenchData.py"))
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

class CurveFactsTest(unittest.TestCase):
    def fixture(self):
        session = {"id": "session", "owner_id": "owner", "training_date": "2026-10-07",
                   "training_day": "上肢A", "status": "draft", "client_revision": 54, "week_number": 1}
        exercises = [{"id": "top", "session_id": "session", "actual_name": "杠铃卧推｜顶组"},
                     {"id": "backoff", "session_id": "session", "actual_name": "杠铃卧推｜回退"}]
        def row(id, exercise, weight, reps, rpe, kind="work", done=True):
            return {"id": id, "exercise_id": exercise, "set_number": 1, "weight": weight,
                    "reps": reps, "rpe": rpe, "is_completed": done,
                    "note": json.dumps({"set_type": kind}, ensure_ascii=False)}
        sets = [row("warmup", "top", 90, 1, None, "warmup"), row("work", "top", 77.5, 3, 8),
                row("back", "backoff", 70, 6, 8), row("unfilled", "backoff", 100, None, None, done=False)]
        return {"source": "CloudBase PostgreSQL", "queried_at": "2026-10-07T10:00:00Z",
                "sessions": [session], "exercises": exercises, "sets": sets}
    def build(self, raw):
        plan = {"plan": {"main_lift_day_map": {"卧推": "上肢A", "硬拉": "腿B", "负重引体": "上肢B"}},
                "schedule": [], "cycles": []}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"snapshot.json"
            path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
            return builder.actual_training_from_snapshot(path, plan)
    def test_role_aliases_and_accessory_variants(self):
        for name, expected in [("杠铃卧推｜顶组", "卧推"), ("杠铃深蹲 | 回退", "深蹲"),
                               ("传统硬拉｜顶组", "硬拉"), ("负重引体｜容量", "负重引体")]:
            self.assertEqual(builder.canonical_main_lift_name(name), expected)
        for name in ["上斜哑铃卧推", "停顿深蹲｜回退", "罗马尼亚硬拉", "杠铃卧推｜暂停", "硬拉｜技术变式"]:
            self.assertNotIn(builder.canonical_main_lift_name(name), builder.MAIN_LIFT_NAMES)
    def test_one_point_uses_top_not_warmup_or_unfilled_row(self):
        result = self.build(self.fixture())
        self.assertEqual(len(result["main_lifts"]), 1)
        point = result["main_lifts"][0]
        self.assertEqual((point["value"],point["detail"]), (77.5,"77.5kg×3 @8"))
        self.assertEqual(point["session_status"], "draft")
        self.assertEqual(result["sessions"][0]["recorded_sets"], 3) # includes valid warmup
    def test_explicit_top_priority_over_heavier_backoff(self):
        raw = self.fixture()
        raw["sets"][2]["weight"] = 80
        self.assertEqual(self.build(raw)["main_lifts"][0]["value"], 77.5)
    def test_replacement_uses_actual_name(self):
        raw = self.fixture()
        for exercise in raw["exercises"]:
            exercise["planned_name"] = exercise["actual_name"]
            exercise["actual_name"] = "上斜哑铃卧推"
        self.assertEqual(self.build(raw)["main_lifts"], [])
    def test_capacity_day_does_not_become_strength_exposure(self):
        raw = self.fixture()
        for exercise in raw["exercises"]:
            exercise["actual_name"] = "负重引体｜容量"
        self.assertEqual(self.build(raw)["main_lifts"], [])
    def test_conventional_deadlift_and_raw_data_unchanged(self):
        raw = self.fixture()
        raw["sessions"][0]["training_day"] = "腿B"
        for e in raw["exercises"]:
            e["actual_name"] = "传统硬拉｜"+("顶组" if e["id"]=="top" else "回退")
        before = json.dumps(raw, sort_keys=True)
        self.assertEqual(self.build(raw)["main_lifts"][0]["name"], "硬拉")
        self.assertEqual(json.dumps(raw, sort_keys=True), before)

if __name__ == "__main__":
    unittest.main()

