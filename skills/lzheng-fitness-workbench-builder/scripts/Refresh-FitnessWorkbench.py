#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Refresh and verify the formal workbench, then optionally prepare a release.

This command is intentionally local-only.  It can prove that a formal HTML file
was refreshed and that a local release directory passed the deploy checker.  It
does not upload files and therefore never claims deployment or online
verification.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path, PurePosixPath


PIPELINE_VERSION = "1.0.1"
HERE = Path(__file__).resolve().parent
BUILDER = HERE / "Build-FitnessWorkbenchData.py"
CHECKER = HERE / "Check-FitnessWorkbench.py"
RELEASER = HERE / "Prepare-FitnessWorkbenchRelease.py"
RELEASE_MODES = ("private-portable", "public-anonymized")
DATA_BLOCK = re.compile(
    r'<script id="workbench-data" type="application/json">([\s\S]*?)</script>'
)


class PipelineFailure(RuntimeError):
    """A controlled pipeline failure that must be written to the receipt."""


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def data_block_hash(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    match = DATA_BLOCK.search(text)
    return sha256_bytes(match.group(1).encode("utf-8")) if match else None


def path_for_receipt(path: Path | None, project: Path) -> str | None:
    if path is None:
        return None
    resolved = path.resolve()
    try:
        return resolved.relative_to(project).as_posix()
    except ValueError:
        return str(resolved)


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def paths_overlap(left: Path, right: Path) -> bool:
    return is_within(left, right) or is_within(right, left)


def is_link_like(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    if path.is_symlink() or bool(is_junction and is_junction()):
        return True
    try:
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def first_link_component(path: Path) -> Path | None:
    """Inspect the lexical path before resolve; reject link/junction parents too."""
    absolute = path.expanduser().absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if os.path.lexists(current) and is_link_like(current):
            return current
    return None


def default_backup_root(project: Path) -> Path:
    project_key = sha256_bytes(str(project.resolve()).casefold().encode("utf-8"))[:16]
    return Path(tempfile.gettempdir()).resolve() / "lzheng-fitness-workbench" / project_key


def script_evidence(path: Path) -> dict:
    raw = path.read_bytes()
    content = raw.decode("utf-8-sig")
    digest = sha256_bytes(raw)
    version_match = re.search(
        r'^(?:PIPELINE_VERSION|SCRIPT_VERSION|SUITE_VERSION|__version__)\s*=\s*["\']([^"\']+)',
        content,
        re.MULTILINE,
    )
    return {
        "path": str(path),
        "sha256": digest,
        "version": version_match.group(1) if version_match else "sha256:" + digest[:12],
    }


def tree_evidence(root: Path) -> dict:
    files = []
    for path in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda p: p.as_posix()):
        files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    canonical = json.dumps(files, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return {"file_count": len(files), "tree_sha256": sha256_bytes(canonical), "files": files}


def safe_manifest_relative(value: object) -> str | None:
    if not isinstance(value, str) or not value or "\\" in value:
        return None
    relative = PurePosixPath(value)
    if relative.is_absolute() or any(part in ("", ".", "..") for part in relative.parts):
        return None
    return relative.as_posix()


def expected_directories(files: set[str]) -> set[str]:
    result: set[str] = set()
    for relative in files:
        parent = PurePosixPath(relative).parent
        while str(parent) not in ("", "."):
            result.add(parent.as_posix())
            parent = parent.parent
    return result


def existing_release_mode(deploy: Path) -> str | None:
    """Validate only ownership/integrity, independent of current source facts."""
    if not deploy.exists():
        return None
    if not deploy.is_dir():
        raise PipelineFailure("已存在的发布目标不是目录，拒绝替换：" + str(deploy))
    manifest_path = deploy / "release-manifest.json"
    if not manifest_path.is_file():
        raise PipelineFailure("已存在目录缺少 release-manifest.json，无法证明由发布器管理，拒绝替换")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise PipelineFailure("已存在目录的 release-manifest.json 无法解析，拒绝替换：" + str(exc)) from exc
    if not isinstance(manifest, dict):
        raise PipelineFailure("已存在目录的 release-manifest.json 根节点不是对象，拒绝替换")
    mode = manifest.get("release_mode")
    if (
        manifest.get("schema") != 2
        or manifest.get("kind") != "lzheng-fitness-workbench-release"
        or manifest.get("producer") != "Prepare-FitnessWorkbenchRelease.py"
        or manifest.get("fresh_staging") is not True
        or manifest.get("entrypoint") != "index.html"
        or mode not in RELEASE_MODES
        or not isinstance(manifest.get("allowed_files"), list)
        or not isinstance(manifest.get("files"), list)
    ):
        raise PipelineFailure("已存在目录不具备受管发布清单，拒绝替换")

    private = mode == "private-portable"
    expected_flags = {
        "anonymized": not private,
        "contains_personal_data": private,
        "required_access": "private-authenticated" if private else "public",
    }
    if any(manifest.get(key) != value for key, value in expected_flags.items()):
        raise PipelineFailure("已存在目录的发布清单隐私标记不完整，拒绝替换")

    allowed_raw = manifest["allowed_files"]
    allowed = [safe_manifest_relative(value) for value in allowed_raw]
    if any(value is None for value in allowed) or len(allowed) != len(set(allowed)):
        raise PipelineFailure("已存在目录的发布允许列表含非法或重复路径，拒绝替换")
    allowed_set = set(allowed)
    if "index.html" not in allowed_set or "release-manifest.json" not in allowed_set:
        raise PipelineFailure("已存在目录的发布允许列表缺少固定入口，拒绝替换")

    actual_files: dict[str, Path] = {}
    actual_directories: set[str] = set()
    for current, subdirs, names in os.walk(deploy, followlinks=False):
        current_path = Path(current)
        for name in list(subdirs):
            path = current_path / name
            relative = path.relative_to(deploy).as_posix()
            if is_link_like(path):
                raise PipelineFailure("已存在发布目录包含符号链接、junction 或 reparse 目录：" + relative)
            actual_directories.add(relative)
        for name in names:
            path = current_path / name
            relative = path.relative_to(deploy).as_posix()
            if is_link_like(path):
                raise PipelineFailure("已存在发布目录包含符号链接或 reparse 文件：" + relative)
            actual_files[relative] = path
    if set(actual_files) != allowed_set:
        raise PipelineFailure("已存在发布目录的实际文件与精确允许列表不一致，拒绝替换")
    if actual_directories != expected_directories(allowed_set):
        raise PipelineFailure("已存在发布目录含未受管目录或缺少清单目录，拒绝替换")

    entry_map: dict[str, dict] = {}
    for entry in manifest["files"]:
        if not isinstance(entry, dict):
            raise PipelineFailure("已存在目录的发布哈希条目无效，拒绝替换")
        relative = safe_manifest_relative(entry.get("path"))
        if not relative or relative in entry_map:
            raise PipelineFailure("已存在目录的发布哈希路径非法或重复，拒绝替换")
        entry_map[relative] = entry
    expected_artifacts = allowed_set - {"release-manifest.json"}
    if set(entry_map) != expected_artifacts:
        raise PipelineFailure("已存在目录的发布哈希列表与允许列表不一致，拒绝替换")
    for relative, entry in entry_map.items():
        path = actual_files[relative]
        if entry.get("bytes") != path.stat().st_size or entry.get("sha256") != sha256_file(path):
            raise PipelineFailure("已存在发布文件与清单哈希不一致，拒绝替换：" + relative)
    return str(mode)


def atomic_write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def output_tail(value: str, limit: int = 1200) -> str:
    text = value.strip()
    return text if len(text) <= limit else text[-limit:]


def run_phase(receipt: dict, name: str, command: list[str], marker: str) -> None:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    started_at = now_iso()
    result = subprocess.run(
        command,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        env=env,
    )
    passed = result.returncode == 0 and marker in result.stdout
    receipt["phases"].append(
        {
            "name": name,
            "started_at": started_at,
            "finished_at": now_iso(),
            "returncode": result.returncode,
            "required_marker": marker,
            "argv": command,
            "marker_found": marker in result.stdout,
            "passed": passed,
            "stdout_tail": output_tail(result.stdout),
            "stderr_tail": output_tail(result.stderr),
        }
    )
    if not passed:
        detail = output_tail(result.stdout + "\n" + result.stderr)
        raise PipelineFailure(f"{name} 未通过：{detail or '未返回通过标记'}")
    print(name + ": PASS")


def prepare_effective_notion(
    source: Path | None,
    notion_mode: str | None,
    run_dir: Path,
    receipt: dict,
) -> Path | None:
    snapshot = receipt["artifacts"]["snapshot"]
    if source is None:
        if notion_mode:
            raise PipelineFailure("--notion-mode 只能与 --notion 一起使用")
        return None
    if not source.is_file():
        raise PipelineFailure("Notion 快照不存在：" + str(source))
    try:
        source_bytes = source.read_bytes()
        payload = json.loads(source_bytes.decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise PipelineFailure(f"Notion 快照无法读取：{exc}") from exc
    snapshot.update({"provided": True, "path": str(source), "sha256": sha256_bytes(source_bytes)})
    if not isinstance(payload, dict):
        raise PipelineFailure("Notion 快照根节点必须是对象")
    declared_mode = str(payload.get("sync_mode") or "").strip().lower() or None
    if declared_mode and declared_mode not in {"incremental", "full"}:
        raise PipelineFailure("Notion 快照 sync_mode 必须是 incremental 或 full")
    if notion_mode and declared_mode and notion_mode != declared_mode:
        raise PipelineFailure("--notion-mode 与 Notion 快照 sync_mode 不一致")
    resolved_mode = notion_mode or declared_mode or "incremental"
    snapshot["notion_mode"] = resolved_mode
    # Freeze one effective snapshot for every phase.  The source file may be
    # regenerated by another process while this command is running.
    payload["sync_mode"] = resolved_mode
    effective = run_dir / "effective-notion-snapshot.json"
    atomic_write_json(effective, payload)
    snapshot["effective_sha256"] = sha256_file(effective)
    return effective


def file_matches(path: Path, expected_sha256: str, expected_size: int) -> bool:
    try:
        return path.is_file() and path.stat().st_size == expected_size and sha256_file(path) == expected_sha256
    except OSError:
        return False


def create_verified_backup(source: Path, backup: Path, expected_sha256: str, expected_size: int) -> None:
    """Copy through a temporary file and publish only byte-identical backups."""
    if os.path.lexists(backup):
        raise PipelineFailure("流水线备份目标已存在：" + str(backup))
    temporary = backup.with_name(backup.name + ".tmp-" + uuid.uuid4().hex)
    try:
        shutil.copy2(source, temporary)
        if not file_matches(temporary, expected_sha256, expected_size):
            raise PipelineFailure("流水线临时备份与复制前正式工作台不一致")
        if not file_matches(source, expected_sha256, expected_size):
            raise PipelineFailure("正式工作台在流水线备份期间发生变化")
        os.replace(temporary, backup)
        if not file_matches(backup, expected_sha256, expected_size):
            raise PipelineFailure("流水线备份原子落位后校验失败")
    except (OSError, PipelineFailure):
        if os.path.lexists(temporary):
            temporary.unlink()
        if os.path.lexists(backup) and not file_matches(backup, expected_sha256, expected_size):
            backup.unlink()
        raise


def restore_formal(
    backup: Path,
    formal: Path,
    receipt: dict,
    expected_sha256: str,
    expected_size: int,
) -> None:
    rollback = {
        "attempted": True,
        "passed": False,
        "backup": str(backup),
        "expected_sha256": expected_sha256,
        "expected_size": expected_size,
    }
    receipt["evidence"]["formal_rollback"] = rollback
    if not file_matches(backup, expected_sha256, expected_size):
        rollback["error"] = "回滚源缺失或与刷新前正式工作台哈希不一致，拒绝恢复"
        return
    rollback["source_sha256"] = sha256_file(backup)
    rollback["source_size"] = backup.stat().st_size
    temporary = formal.with_name(formal.name + ".rollback-" + uuid.uuid4().hex)
    try:
        shutil.copy2(backup, temporary)
        if not file_matches(temporary, expected_sha256, expected_size):
            raise PipelineFailure("回滚临时文件与已验证备份不一致")
        os.replace(temporary, formal)
        rollback["restored_sha256"] = sha256_file(formal)
        rollback["restored_size"] = formal.stat().st_size
        if not file_matches(formal, expected_sha256, expected_size):
            raise PipelineFailure("正式工作台回滚落位后的哈希校验失败")
        rollback["passed"] = True
    except (OSError, PipelineFailure) as exc:
        rollback["error"] = str(exc)
        if os.path.lexists(temporary):
            temporary.unlink()


def path_identity(path: Path) -> tuple[int, int]:
    info = os.lstat(path)
    return info.st_dev, info.st_ino


def promote_release(
    candidate: Path,
    deploy: Path,
    run_id: str,
    checked_tree: dict,
    receipt: dict,
) -> dict:
    """Promote, verify in place, then commit or restore the previous release."""
    previous = deploy.parent / ("." + deploy.name + ".previous-" + run_id)
    quarantine = deploy.parent / ("." + deploy.name + ".failed-" + run_id)
    if os.path.lexists(previous) or os.path.lexists(quarantine):
        raise PipelineFailure("发布替换临时目录已存在：" + str(previous))
    candidate_identity = path_identity(candidate)
    had_previous = os.path.lexists(deploy)
    previous_tree = tree_evidence(deploy) if had_previous else None
    if had_previous:
        os.replace(deploy, previous)
    try:
        os.replace(candidate, deploy)
    except OSError as exc:
        if had_previous and previous.exists() and not os.path.lexists(deploy):
            os.replace(previous, deploy)
        raise PipelineFailure("已校验发布副本无法替换到目标目录：" + str(exc)) from exc

    try:
        if is_link_like(deploy) or path_identity(deploy) != candidate_identity:
            raise PipelineFailure("发布副本换入后目录身份与已校验候选不一致")
        final_tree = tree_evidence(deploy)
        if checked_tree["tree_sha256"] != final_tree["tree_sha256"]:
            raise PipelineFailure("发布副本在换入后终验发生变化")
    except (OSError, PipelineFailure) as validation_error:
        rollback = {
            "attempted": True,
            "passed": False,
            "had_previous": had_previous,
            "previous": str(previous) if had_previous else None,
            "quarantine": str(quarantine),
            "validation_error": str(validation_error),
            "old_release_restored": False,
            "new_target_absent": False,
        }
        receipt["evidence"]["deploy_rollback"] = rollback
        try:
            if not os.path.lexists(deploy):
                raise PipelineFailure("终验失败后本次候选发布目录已经消失")
            if is_link_like(deploy) or path_identity(deploy) != candidate_identity:
                raise PipelineFailure("终验失败后目标已不是本次候选，拒绝移动未知目录")
            os.replace(deploy, quarantine)
            if had_previous:
                if not os.path.lexists(previous) or is_link_like(previous):
                    raise PipelineFailure("旧受管发布副本缺失或身份异常，无法恢复")
                os.replace(previous, deploy)
                restored_tree = tree_evidence(deploy)
                if restored_tree["tree_sha256"] != previous_tree["tree_sha256"]:
                    raise PipelineFailure("恢复后的旧受管发布副本与换入前哈希不一致")
                rollback["old_release_restored"] = True
                rollback["restored_tree_sha256"] = restored_tree["tree_sha256"]
            else:
                rollback["new_target_absent"] = not os.path.lexists(deploy)
                if not rollback["new_target_absent"]:
                    raise PipelineFailure("新发布目标终验失败后仍然存在")
            rollback["passed"] = True
        except (OSError, PipelineFailure) as rollback_error:
            rollback["error"] = str(rollback_error)
            raise PipelineFailure(
                "发布副本终验失败且自动回滚未完成；旧副本="
                + (str(previous) if os.path.lexists(previous) else "无")
                + "；失败候选隔离="
                + (str(quarantine) if os.path.lexists(quarantine) else "无")
            ) from rollback_error
        raise PipelineFailure("发布副本换入后终验失败，已隔离失败候选并恢复原目标：" + str(validation_error)) from validation_error

    if previous.exists():
        shutil.rmtree(previous)
    return final_tree


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--notion")
    parser.add_argument("--notion-mode", choices=("incremental", "full"))
    parser.add_argument("--integration-config", help="可选公开客户端同步配置；缺省保留当前实例配置")
    parser.add_argument("--replace-main-lift-history", action="store_true")
    parser.add_argument(
        "--confirm-replace-main-lift-history",
        action="store_true",
        help="明确确认当前 full Notion 快照已经人工核验，可权威替换整份主项实际历史",
    )
    parser.add_argument("--backup-dir")
    parser.add_argument("--receipt")
    parser.add_argument("--deploy", help="可选：生成并检查本地发布副本目录；不会上传")
    parser.add_argument("--release-mode", choices=RELEASE_MODES)
    parser.add_argument(
        "--confirm-private-portable",
        action="store_true",
        help="明确确认 private-portable 会保留完整个人训练数据，且只可放在有鉴权的私有环境",
    )
    args = parser.parse_args()

    project = Path(args.project).resolve()
    formal = project / "健身工作台.html"
    notion_source = Path(args.notion).resolve() if args.notion else None
    deploy_input = Path(args.deploy).expanduser().absolute() if args.deploy else None
    deploy_link_component = first_link_component(deploy_input) if deploy_input else None
    # Do not resolve through a detected junction/reparse point even for error
    # reporting; the lexical path is enough to fail closed.
    deploy = (deploy_input if deploy_link_component else deploy_input.resolve()) if deploy_input else None
    run_id = dt.datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")
    backup_root = (
        Path(args.backup_dir).resolve()
        if args.backup_dir
        else default_backup_root(project)
    )
    run_dir = backup_root / run_id
    requested_receipt = Path(args.receipt).resolve() if args.receipt else backup_root / "receipts" / ("refresh-" + run_id + ".json")
    path_gate_error = None
    if is_within(backup_root, project) or is_within(run_dir, project):
        path_gate_error = "备份与运行证据目录不能位于个人训练系统内部"
    if is_within(requested_receipt, project):
        path_gate_error = "刷新回执不能写入个人训练系统内部"
    if deploy:
        if deploy_link_component:
            path_gate_error = "发布目录路径不能经过符号链接、junction 或 reparse point：" + str(deploy_link_component)
        elif deploy == Path(deploy.anchor):
            path_gate_error = "发布目录不能是磁盘根目录"
        elif paths_overlap(deploy, project):
            path_gate_error = "发布目录与个人训练系统不能互相包含"
        elif paths_overlap(deploy, backup_root) or paths_overlap(deploy, run_dir):
            path_gate_error = "发布目录不能与备份或运行证据目录重叠"
        elif paths_overlap(requested_receipt, deploy):
            path_gate_error = "回执不能写在会被替换的发布目录内"
    receipt_path: Path | None = requested_receipt
    if path_gate_error:
        receipt_path = default_backup_root(project) / "receipts" / ("rejected-refresh-" + run_id + ".json")
        if deploy and not deploy_link_component and paths_overlap(receipt_path, deploy):
            # A drive-root target contains every writable local receipt path on
            # that drive.  Fail closed without writing into the claimed target.
            receipt_path = None
    receipt = {
        "schema": 1,
        "kind": "lzheng_fitness_workbench_refresh_receipt",
        "pipeline_version": PIPELINE_VERSION,
        "run_id": run_id,
        "started_at": now_iso(),
        "finished_at": None,
        "result": {"status": "running", "error": None},
        "claims": {
            "formal_refreshed": False,
            "release_prepared": False,
            "deployed": False,
            "online_verified": False,
        },
        "artifacts": {
            "snapshot": {
                "provided": False,
                "source_kind": "notion-json" if notion_source else "embedded-workbench-data",
                "path": str(notion_source) if notion_source else "健身工作台.html#workbench-data",
                "sha256": data_block_hash(formal) if not notion_source else None,
                "effective_sha256": data_block_hash(formal) if not notion_source else None,
                "notion_mode": None,
            },
            "formal": {
                "path": path_for_receipt(formal, project),
                "sha256_before": sha256_file(formal) if formal.is_file() else None,
                "data_sha256_before": data_block_hash(formal),
                "sha256_after": None,
                "data_sha256_after": None,
            },
            "deploy": None,
        },
        "evidence": {
            "formal_checker_pass": False,
            "deploy_checker_pass": False,
            "existing_deploy": {"existed": bool(deploy and not deploy_link_component and deploy.exists()), "owned_manifest": False, "tree_hashes_pass": False},
            "remote_deploy_evidence": None,
            "online_verification_evidence": None,
        },
        "runtime": {"python_version": platform.python_version()},
        "operation": {
            "replace_main_lift_history": bool(args.replace_main_lift_history),
            "replace_main_lift_history_confirmed": bool(args.confirm_replace_main_lift_history),
            "private_portable_confirmed": bool(args.confirm_private_portable),
        },
        "requested_receipt": str(requested_receipt),
        "scripts": {},
        "phases": [],
    }

    formal_verified = False
    pipeline_backup: Path | None = None
    formal_before_hash: str | None = None
    formal_before_size: int | None = None
    candidate: Path | None = None
    try:
        if path_gate_error:
            raise PipelineFailure(path_gate_error)
        if not project.is_dir() or not formal.is_file():
            raise PipelineFailure("项目根目录缺少正式健身工作台.html：" + str(project))
        for label, script in (("refresh", Path(__file__).resolve()), ("builder", BUILDER), ("checker", CHECKER), ("releaser", RELEASER)):
            if not script.is_file():
                raise PipelineFailure("缺少核心脚本：" + str(script))
            receipt["scripts"][label] = script_evidence(script)
        if deploy and not args.release_mode:
            raise PipelineFailure("使用 --deploy 时必须显式指定 --release-mode")
        if args.release_mode and not deploy:
            raise PipelineFailure("--release-mode 只能与 --deploy 一起使用")
        if args.confirm_private_portable and args.release_mode != "private-portable":
            raise PipelineFailure("--confirm-private-portable 只能确认 private-portable 发布")
        if args.release_mode == "private-portable" and not args.confirm_private_portable:
            raise PipelineFailure("private-portable 保留完整个人数据；必须显式传入 --confirm-private-portable")
        if args.confirm_replace_main_lift_history and not args.replace_main_lift_history:
            raise PipelineFailure("--confirm-replace-main-lift-history 只能确认主项历史替换")
        if args.replace_main_lift_history:
            if not args.notion or args.notion_mode != "full":
                raise PipelineFailure("--replace-main-lift-history 必须显式搭配 --notion 与 --notion-mode full")
            if not args.confirm_replace_main_lift_history:
                raise PipelineFailure("权威替换整份主项实际历史必须显式传入 --confirm-replace-main-lift-history")
        run_dir.mkdir(parents=True, exist_ok=True)
        effective_notion = prepare_effective_notion(notion_source, args.notion_mode, run_dir, receipt)
        changed_link = first_link_component(deploy_input) if deploy_input else None
        if changed_link:
            raise PipelineFailure("发布目录路径在所有权检查前出现符号链接、junction 或 reparse point：" + str(changed_link))
        existing_mode = existing_release_mode(deploy) if deploy else None
        if existing_mode:
            receipt["evidence"]["existing_deploy"]["owned_manifest"] = True
            receipt["evidence"]["existing_deploy"]["tree_hashes_pass"] = True
        build_base = [sys.executable, str(BUILDER), "--project", str(project)]
        if effective_notion:
            build_base += ["--notion", str(effective_notion)]
        if args.notion_mode:
            build_base += ["--notion-mode", args.notion_mode]
        if args.integration_config:
            build_base += ["--integration-config", args.integration_config]
        if args.replace_main_lift_history:
            build_base += ["--replace-main-lift-history"]

        pipeline_backup = run_dir / "formal-before-pipeline.html"
        formal_before_hash = sha256_file(formal)
        formal_before_size = formal.stat().st_size
        create_verified_backup(formal, pipeline_backup, formal_before_hash, formal_before_size)
        before_check_hash = formal_before_hash
        run_phase(receipt, "builder_check", build_base + ["--check-only"], "FITNESS_WORKBENCH_DATA: PASS")
        if sha256_file(formal) != before_check_hash:
            raise PipelineFailure("builder_check 非预期修改了正式工作台")

        apply_backup_dir = run_dir / "formal-before-apply"
        run_phase(
            receipt,
            "builder_apply",
            build_base + ["--apply", "--backup-dir", str(apply_backup_dir)],
            "FITNESS_WORKBENCH_DATA: PASS",
        )
        check_command = [sys.executable, str(CHECKER), "--project", str(project)]
        if effective_notion:
            check_command += ["--notion", str(effective_notion)]
        if args.notion_mode:
            check_command += ["--notion-mode", args.notion_mode]
        if args.replace_main_lift_history:
            check_command += ["--replace-main-lift-history"]
        run_phase(receipt, "formal_checker", check_command, "FITNESS_WORKBENCH_CHECK: PASS")
        receipt["evidence"]["formal_checker_pass"] = True
        receipt["claims"]["formal_refreshed"] = True
        formal_verified = True
        receipt["artifacts"]["formal"].update(
            {"sha256_after": sha256_file(formal), "data_sha256_after": data_block_hash(formal)}
        )

        if deploy:
            changed_link = first_link_component(deploy_input)
            if changed_link:
                raise PipelineFailure("发布目录路径在执行期间出现符号链接、junction 或 reparse point：" + str(changed_link))
            deploy.parent.mkdir(parents=True, exist_ok=True)
            candidate = deploy.parent / ("." + deploy.name + ".candidate-" + run_id)
            if os.path.lexists(candidate):
                raise PipelineFailure("发布候选目录已存在：" + str(candidate))
            run_phase(
                receipt,
                "release_prepare",
                [sys.executable, str(RELEASER), "--project", str(project), "--deploy", str(candidate), "--mode", args.release_mode],
                "FITNESS_WORKBENCH_RELEASE: PASS",
            )
            deploy_check = [
                sys.executable,
                str(CHECKER),
                "--project",
                str(project),
                "--deploy",
                str(candidate),
                "--expect-release-mode",
                args.release_mode,
            ]
            if effective_notion:
                deploy_check += ["--notion", str(effective_notion)]
            if args.notion_mode:
                deploy_check += ["--notion-mode", args.notion_mode]
            if args.replace_main_lift_history:
                deploy_check += ["--replace-main-lift-history"]
            if args.release_mode == "private-portable":
                deploy_check.append("--allow-private-portable")
            run_phase(receipt, "deploy_checker", deploy_check, "FITNESS_WORKBENCH_CHECK: PASS")
            receipt["evidence"]["deploy_checker_pass"] = True
            checked_tree = tree_evidence(candidate)
            changed_link = first_link_component(deploy_input)
            if changed_link:
                raise PipelineFailure("发布目录路径在替换前出现符号链接、junction 或 reparse point：" + str(changed_link))
            current_existing_mode = existing_release_mode(deploy)
            if current_existing_mode != existing_mode:
                raise PipelineFailure("发布目标在执行期间发生变化，拒绝替换")
            promote_release(candidate, deploy, run_id, checked_tree, receipt)
            candidate = None
            final_tree = tree_evidence(deploy)
            if checked_tree["tree_sha256"] != final_tree["tree_sha256"]:
                raise PipelineFailure("发布副本在校验后发生变化")
            receipt["claims"]["release_prepared"] = True
            receipt["artifacts"]["deploy"] = {
                "path": path_for_receipt(deploy, project),
                "release_mode": args.release_mode,
                **final_tree,
            }

        receipt["result"]["status"] = "PASS"
    except (PipelineFailure, OSError) as exc:
        if (
            not formal_verified
            and pipeline_backup
            and pipeline_backup.is_file()
            and formal_before_hash is not None
            and formal_before_size is not None
        ):
            restore_formal(pipeline_backup, formal, receipt, formal_before_hash, formal_before_size)
        receipt["result"] = {"status": "FAIL", "error": str(exc)}
    finally:
        if candidate and candidate.exists():
            shutil.rmtree(candidate, ignore_errors=True)
        if formal.is_file():
            receipt["artifacts"]["formal"]["sha256_after"] = sha256_file(formal)
            receipt["artifacts"]["formal"]["data_sha256_after"] = data_block_hash(formal)
        receipt["finished_at"] = now_iso()
        if receipt_path:
            atomic_write_json(receipt_path, receipt)

    if receipt["result"]["status"] != "PASS":
        print("FITNESS_WORKBENCH_REFRESH: FAIL", file=sys.stderr)
        print("- " + str(receipt["result"]["error"]), file=sys.stderr)
        print("receipt: " + (str(receipt_path) if receipt_path else "not-written (unsafe target overlap)"), file=sys.stderr)
        raise SystemExit(1)
    print("FITNESS_WORKBENCH_REFRESH: PASS")
    print("receipt: " + str(receipt_path))
    for claim in ("formal_refreshed", "release_prepared", "deployed", "online_verified"):
        print(claim + ": " + str(receipt["claims"][claim]).lower())


if __name__ == "__main__":
    main()
