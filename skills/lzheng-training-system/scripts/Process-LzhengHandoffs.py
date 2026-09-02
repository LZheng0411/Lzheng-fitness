#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""消费已确认的 LZHENG_HANDOFF，并安全刷新工作台。

该脚本不生成处方、不合并专项周期；需要先合并的交接会明确保留为待处理。
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent.parent
REFRESH = SKILL_ROOT / "lzheng-fitness-workbench-builder" / "scripts" / "Refresh-FitnessWorkbench.py"
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


def delivery(record: dict, outcome: str, detail: str, evidence: dict | None = None) -> dict:
    record["delivery"] = {
        "status": outcome,
        "processed_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "detail": detail,
    }
    if evidence:
        record["delivery"]["evidence"] = evidence
    return record


def save_record(path: Path, record: dict) -> None:
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def default_backup_root(project: Path) -> Path:
    project_key = hashlib.sha256(str(project.resolve()).casefold().encode("utf-8")).hexdigest()[:16]
    return Path(tempfile.gettempdir()).resolve() / "lzheng-fitness-workbench" / project_key


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def refresh(
    project: Path,
    notion: str | None,
    notion_mode: str | None,
    backup_dir: Path,
    receipt_path: Path,
) -> tuple[bool, str, dict | None]:
    backup_dir.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(REFRESH),
        "--project",
        str(project),
        "--backup-dir",
        str(backup_dir),
        "--receipt",
        str(receipt_path),
    ]
    if notion:
        command += ["--notion", notion]
    if notion_mode:
        command += ["--notion-mode", notion_mode]
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    result = subprocess.run(command, text=True, encoding="utf-8", errors="replace", capture_output=True, env=env)
    detail = (result.stdout + result.stderr).strip()
    receipt = None
    if receipt_path.is_file():
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError, json.JSONDecodeError):
            receipt = None
    formal_phase = next(
        (item for item in (receipt or {}).get("phases", []) if item.get("name") == "formal_checker"),
        {},
    )
    proved = (
        result.returncode == 0
        and "FITNESS_WORKBENCH_REFRESH: PASS" in result.stdout
        and isinstance(receipt, dict)
        and receipt.get("result", {}).get("status") == "PASS"
        and receipt.get("claims", {}).get("formal_refreshed") is True
        and receipt.get("evidence", {}).get("formal_checker_pass") is True
        and formal_phase.get("passed") is True
        and formal_phase.get("marker_found") is True
    )
    return proved, detail, receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--notion")
    parser.add_argument("--notion-mode", choices=("incremental", "full"))
    parser.add_argument("--backup-dir")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    project = Path(args.project).resolve()
    if not (project / "健身工作台.html").is_file():
        fail("项目根目录缺少正式健身工作台.html")
    if not REFRESH.is_file():
        fail("缺少工作台刷新闭环：" + str(REFRESH))
    if args.notion_mode and not args.notion:
        fail("--notion-mode 只能与 --notion 一起使用")
    records = project / "工作台与工具" / "交接记录"
    if not records.is_dir():
        print("LZHENG_HANDOFF: PASS\nprocessed: 0\nmessage: 没有待处理交接记录")
        return
    pending = []
    for path in sorted(records.glob("*.json")):
        record = load_record(path)
        # refreshed 是 schema 1 旧状态，继续跳过以避免升级后重复消费。
        if record.get("delivery", {}).get("status") in {"formal_refreshed", "refreshed", "awaiting_merge"}:
            continue
        pending.append((path, record))
    if not pending:
        print("LZHENG_HANDOFF: PASS\nprocessed: 0\nmessage: 没有待处理交接记录")
        return
    backup_dir = Path(args.backup_dir).resolve() if args.backup_dir else default_backup_root(project)
    if is_within(backup_dir, project):
        fail("备份与刷新回执目录不能位于个人训练系统内部")
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
        receipt_root = backup_dir / "handoff-receipts"
        stamp = dt.datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")
        receipt_path = receipt_root / (stamp + "-workbench-refresh.json")
        ok, _detail, receipt = refresh(project, args.notion, args.notion_mode, backup_dir, receipt_path)
        if not ok:
            for path, record in pending:
                if record.get("requires", {}).get("refresh_workbench") and not record.get("requires", {}).get("merge_into_current_plan"):
                    evidence = None
                    if receipt_path.is_file():
                        evidence = {
                            "receipt_scope": "external-local",
                            "receipt_file": receipt_path.name,
                            "receipt_sha256": file_sha256(receipt_path),
                            "formal_checker": "FAIL",
                        }
                    failure_detail = (
                        "工作台刷新未通过单命令闸门；请按 receipt_file 与 receipt_sha256 检查项目外本地回执。"
                        if evidence
                        else "工作台刷新未通过单命令闸门，且未生成可验证回执。"
                    )
                    save_record(path, delivery(record, "failed", failure_detail, evidence))
            fail("工作台刷新失败；交接记录已保留失败原因。")
        formal = (receipt or {}).get("artifacts", {}).get("formal", {})
        evidence = {
            "receipt_scope": "external-local",
            "receipt_file": receipt_path.name,
            "receipt_sha256": file_sha256(receipt_path),
            "formal_sha256": formal.get("sha256_after"),
            "formal_data_sha256": formal.get("data_sha256_after"),
            "formal_checker": "PASS",
        }
        for path, record in pending:
            if record.get("requires", {}).get("refresh_workbench") and not record.get("requires", {}).get("merge_into_current_plan"):
                save_record(path, delivery(record, "formal_refreshed", "正式工作台已重新构建且通过 checker；未准备发布副本、未部署、未验证线上。", evidence))
                print("formal_refreshed: " + path.name)
                processed += 1
    elif refresh_needed:
        print("dry-run: 将刷新工作台")
    print("LZHENG_HANDOFF: PASS\nprocessed: " + str(processed))


if __name__ == "__main__":
    main()
