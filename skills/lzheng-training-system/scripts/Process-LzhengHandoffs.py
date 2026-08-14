#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""消费已确认的 LZHENG_HANDOFF，并安全刷新工作台。

该脚本不生成处方、不合并专项周期；需要先合并的交接会明确保留为待处理。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent.parent
BUILDER = SKILL_ROOT / "lzheng-fitness-workbench-builder" / "scripts" / "Build-FitnessWorkbenchData.py"
VALID_SOURCES = {
    "lzheng-fitness-plan",
    "lzheng-strength-cycle-planner",
    "lzheng-strength-training-review",
    "lzheng-training-return",
}


def fail(message: str) -> None:
    raise SystemExit("LZHENG_HANDOFF: FAIL\n- " + message)


def load_record(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        fail(f"交接文件无法读取：{path}（{exc}）")
    if not isinstance(data, dict):
        fail(f"交接文件根节点必须是对象：{path}")
    return data


def validate(record: dict, path: Path, project: Path) -> list[str]:
    errors: list[str] = []
    if record.get("schema") != 1:
        errors.append("schema 必须为 1")
    if record.get("source_skill") not in VALID_SOURCES:
        errors.append("source_skill 非允许专业 Skill")
    if not isinstance(record.get("event_type"), str) or not record["event_type"].strip():
        errors.append("缺少 event_type")
    requires = record.get("requires")
    if not isinstance(requires, dict):
        errors.append("requires 必须是对象")
    artifacts = record.get("artifacts")
    if not isinstance(artifacts, list):
        errors.append("artifacts 必须是数组")
    else:
        for item in artifacts:
            if not isinstance(item, dict) or not item.get("path"):
                errors.append("artifacts 含缺少 path 的项目")
                continue
            target = (project / str(item["path"])).resolve()
            if project not in target.parents and target != project:
                errors.append("artifact 路径越出项目范围")
            elif not target.exists():
                errors.append("artifact 不存在：" + str(item["path"]))
    return errors


def delivery(record: dict, outcome: str, detail: str) -> dict:
    record["delivery"] = {
        "status": outcome,
        "processed_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "detail": detail,
    }
    return record


def save_record(path: Path, record: dict) -> None:
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def refresh(project: Path, notion: str | None, backup_dir: Path) -> tuple[bool, str]:
    backup_dir.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(BUILDER), "--project", str(project), "--apply", "--backup-dir", str(backup_dir)]
    if notion:
        command += ["--notion", notion]
    result = subprocess.run(command, text=True, encoding="utf-8", errors="replace", capture_output=True)
    detail = (result.stdout + result.stderr).strip()
    # Build 脚本在 --apply 成功时以退出码 0 和 applied 行确认；--check-only 才打印 PASS。
    return result.returncode == 0 and "workbench-data applied:" in result.stdout, detail


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--notion")
    parser.add_argument("--backup-dir")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    project = Path(args.project).resolve()
    if not (project / "健身工作台.html").is_file():
        fail("项目根目录缺少正式健身工作台.html")
    if not BUILDER.is_file():
        fail("缺少工作台构建器：" + str(BUILDER))
    records = project / "工作台与工具" / "交接记录"
    if not records.is_dir():
        print("LZHENG_HANDOFF: PASS\nprocessed: 0\nmessage: 没有待处理交接记录")
        return
    pending = []
    for path in sorted(records.glob("*.json")):
        record = load_record(path)
        if record.get("delivery", {}).get("status") in {"refreshed", "awaiting_merge"}:
            continue
        pending.append((path, record))
    if not pending:
        print("LZHENG_HANDOFF: PASS\nprocessed: 0\nmessage: 没有待处理交接记录")
        return
    backup_dir = Path(args.backup_dir).resolve() if args.backup_dir else project.parent / (project.name + "-workbench-backups")
    processed = 0
    refresh_needed = False
    for path, record in pending:
        errors = validate(record, path, project)
        if errors:
            if not args.dry_run:
                save_record(path, delivery(record, "failed", "；".join(errors)))
            fail(path.name + " 无法消费：" + "；".join(errors))
        requires = record["requires"]
        if requires.get("merge_into_current_plan"):
            if not args.dry_run:
                save_record(path, delivery(record, "awaiting_merge", "需先由完整计划 Skill 合并并生成新的当前计划主源。"))
            print("awaiting_merge: " + path.name)
            processed += 1
            continue
        if requires.get("refresh_workbench"):
            refresh_needed = True
    if refresh_needed and not args.dry_run:
        ok, detail = refresh(project, args.notion, backup_dir)
        if not ok:
            for path, record in pending:
                if record.get("requires", {}).get("refresh_workbench") and not record.get("requires", {}).get("merge_into_current_plan"):
                    save_record(path, delivery(record, "failed", "工作台刷新失败：" + detail[-800:]))
            fail("工作台刷新失败；交接记录已保留失败原因。")
        for path, record in pending:
            if record.get("requires", {}).get("refresh_workbench") and not record.get("requires", {}).get("merge_into_current_plan"):
                save_record(path, delivery(record, "refreshed", "工作台已按当前计划、执行基准、复盘与状态档案重新构建。"))
                print("refreshed: " + path.name)
                processed += 1
    elif refresh_needed:
        print("dry-run: 将刷新工作台")
    print("LZHENG_HANDOFF: PASS\nprocessed: " + str(processed))


if __name__ == "__main__":
    main()
