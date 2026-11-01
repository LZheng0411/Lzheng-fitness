"""Read frozen, owner-authorized training exports; never infer completed sets."""
from __future__ import annotations

import datetime as dt
import json
import math
import re
from pathlib import Path

MEMBER_SOURCE = "fitness_cloud.training_snapshot"
SQL_SOURCE = "CloudBase PostgreSQL"


def number(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("Boolean is not a recorded number")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError("Invalid recorded number")
    return result


def load_snapshot(path, plan_json):
    raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict) or not raw.get("queried_at"):
        raise ValueError("Training snapshot requires its actual query time")
    stamp = dt.datetime.fromisoformat(raw["queried_at"].replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("Training query time requires a timezone")
    if raw.get("source") == SQL_SOURCE:
        return raw
    if raw.get("source") != MEMBER_SOURCE:
        raise ValueError("Unsupported training snapshot source")
    snap = raw.get("snapshot")
    if not isinstance(snap, dict) or not isinstance(snap.get("revision"), int) or not snap.get("hash"):
        raise ValueError("Member snapshot requires revision and hash")
    history, page = snap.get("history"), snap.get("pagination")
    if not isinstance(history, list) or not isinstance(page, dict):
        raise ValueError("Member snapshot requires history and pagination")
    if page.get("offset") != 0 or page.get("hasMore") is not False or page.get("total") != len(history):
        raise ValueError("Read all training history pages before freezing the snapshot")
    source_sessions = history + ([snap["activeSession"]] if snap.get("activeSession") else [])
    result = {"source": MEMBER_SOURCE, "queried_at": raw["queried_at"],
              "revision": snap["revision"], "hash": snap["hash"],
              "sessions": [], "exercises": [], "sets": []}
    seen = set()
    for session in source_sessions:
        sid = str(session.get("id") or "")
        if not sid or sid in seen:
            raise ValueError("Missing or duplicate training session ID")
        seen.add(sid)
        instant = number(session.get("startedAt"))
        if instant is None:
            raise ValueError("Recorded session requires its actual start time")
        date = dt.datetime.fromtimestamp(instant / 1000, dt.timezone(dt.timedelta(hours=8))).date()
        title = str(session.get("title") or "").strip()
        day = re.split(r"[｜|]", title, maxsplit=1)[0].strip()
        if not day:
            raise ValueError("Recorded session requires its training role")
        # Calendar placement and the source's prescription week are distinct.
        plan = plan_json.get("plan", {})
        anchor = plan.get("calendar_anchor") if plan.get("week_policy") == "monday_sunday" else None
        week = (date - dt.date.fromisoformat(anchor)).days // 7 + 1 if anchor else session.get("cycleWeek")
        result["sessions"].append({"id": sid, "training_date": date.isoformat(),
            "training_day": day, "week_number": week, "status": session.get("status"),
            "client_revision": snap["revision"], "source_cycle_week": session.get("cycleWeek")})
        exercise_ids = set()
        for exercise in session.get("exercises", []):
            source_id = str(exercise.get("id") or "")
            if not source_id or source_id in exercise_ids:
                raise ValueError("Missing or duplicate exercise ID in session")
            exercise_ids.add(source_id)
            eid = sid + "/" + source_id
            name = str(exercise.get("actualName") or exercise.get("name") or "").strip()
            if not name:
                raise ValueError("Recorded exercise requires its actual name")
            result["exercises"].append({"id": eid, "session_id": sid,
                "actual_name": name, "planned_name": exercise.get("name"), "weight_unit": "kg"})
            indices = set()
            for record in exercise.get("recordedSets", []):
                index = record.get("setIndex")
                if not isinstance(index, int) or index < 1 or index in indices:
                    raise ValueError("Missing or duplicate recorded set index")
                indices.add(index)
                reps = number(record.get("reps"))
                if reps is not None and not reps.is_integer():
                    raise ValueError("Recorded reps must be whole numbers")
                rpe = number(record.get("rpe"))
                if rpe is not None and rpe > 10:
                    raise ValueError("Recorded RPE exceeds 10")
                kind = record.get("setType") or ("warmup" if "热身" in name else "top" if "顶组" in name else "work")
                result["sets"].append({"id": eid + "/" + str(index), "exercise_id": eid,
                    "set_number": index, "weight": number(record.get("weight")),
                    "reps": int(reps) if reps is not None else None, "rpe": rpe,
                    "is_completed": record.get("completed") is True,
                    "note": json.dumps({"set_type": kind}, ensure_ascii=False)})
    return result
