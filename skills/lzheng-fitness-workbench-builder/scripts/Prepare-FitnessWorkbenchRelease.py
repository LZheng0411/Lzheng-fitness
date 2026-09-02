#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a fresh, manifest-backed workbench release directory."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlparse


DATA_BLOCK = re.compile(r'(<script id="workbench-data" type="application/json">)([\s\S]*?)(</script>)')
WINDOWS_PATH = re.compile(r"^[A-Za-z]:[\\/]")
WINDOWS_PATH_IN_TEXT = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]")
LOCAL_EDIT_EXPRESSION = re.compile(
    r'''(["'])obsidian://open\?path=\1\s*\+\s*encodeURIComponent\(absolute\)''',
    re.I,
)
RELEASE_MODES = ("private-portable", "public-anonymized")
MANIFEST_NAME = "release-manifest.json"
MANIFEST_SCHEMA = 2
MANIFEST_KIND = "lzheng-fitness-workbench-release"
MANIFEST_PRODUCER = "Prepare-FitnessWorkbenchRelease.py"
PUBLIC_SHELL_ID = "fitness-public-anonymous-v1"
PUBLIC_DAY_NAMES = ("上肢A", "腿B", "上肢B", "腿A")
PUBLIC_SHELL_TEMPLATE = """<!doctype html>
<html lang="zh-CN" data-release-shell="fitness-public-anonymous-v1">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>公开健身工作台</title>
  <style>
    :root{color-scheme:light dark;font-family:system-ui,"Microsoft YaHei",sans-serif}
    *{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;background:#f4f4f1;color:#171717}
    main{width:min(720px,calc(100% - 32px));padding:40px;border:1px solid #d8d8d2;border-radius:24px;background:#fff;box-shadow:0 18px 60px rgba(0,0,0,.08)}
    .kicker{margin:0 0 10px;color:#666;font-size:12px;letter-spacing:.14em}.lead{line-height:1.75;color:#454545}
    h1{margin:0;font-size:clamp(28px,6vw,48px)}section{margin-top:30px;padding:22px;border-radius:16px;background:#f1f1ee}
    dl{display:grid;grid-template-columns:auto 1fr;gap:10px 18px;margin:0}dt{color:#666}dd{margin:0;font-weight:650}
    @media(max-width:560px){main{padding:26px}dl{grid-template-columns:1fr;gap:4px}dd{margin-bottom:10px}}
    @media(prefers-color-scheme:dark){body{background:#111;color:#f5f5f2}main{background:#1b1b1b;border-color:#333}.lead,dt{color:#bbb}section{background:#252525}}
  </style>
</head>
<body>
  <main>
    <p class="kicker">PUBLIC FITNESS WORKBENCH</p>
    <h1>公开健身工作台</h1>
    <p class="lead">这是不含个人身份、训练事实和本地媒体的静态展示壳。私人计划、复盘与动态记录均未进入此副本。</p>
    <section aria-label="公开副本状态">
      <dl>
        <dt>发布模式</dt><dd id="releaseMode">正在校验</dd>
        <dt>个人训练数据</dt><dd id="personalData">未包含</dd>
        <dt>本地媒体</dt><dd>未包含</dd>
      </dl>
    </section>
  </main>
  <script id="workbench-data" type="application/json">__WORKBENCH_DATA__</script>
  <script>
  (function(){
    "use strict";
    var data=JSON.parse(document.getElementById("workbench-data").textContent);
    var release=data.release||{};
    document.getElementById("releaseMode").textContent=release.mode||"未知";
    document.getElementById("personalData").textContent=release.contains_personal_data?"包含（拒绝公开）":"未包含";
  })();
  </script>
</body>
</html>
"""


def fail(message: str) -> None:
    raise SystemExit("FITNESS_WORKBENCH_RELEASE: FAIL\n- " + message)


def scrub(value):
    """Remove machine-local routing while preserving private portable content."""
    if isinstance(value, dict):
        cleaned = {}
        for key, child in value.items():
            if key.endswith("_path"):
                continue
            if key.endswith("_href") and isinstance(child, str) and child.lower().startswith("obsidian://"):
                continue
            cleaned[key] = scrub(child)
        return cleaned
    if isinstance(value, list):
        return [scrub(item) for item in value]
    if isinstance(value, str):
        if value.lower().startswith(("obsidian://", "file://")) or WINDOWS_PATH.match(value):
            return "本地来源已在发布副本隐藏"
    return value


def public_anonymized_data(source: dict, released_at: str) -> dict:
    """Return a safe public shell; do not attempt heuristic redaction of free text."""
    release_date = released_at[:10]
    return {
        "schema": 6,
        "meta": {
            "title": "公开匿名健身工作台",
            "source_version": "public-anonymized",
            "updated_at": release_date,
            "current_week": 1,
            "total_weeks": 1,
            "test_week": 1,
            "phase": "公开示例",
            "plan_start": release_date,
            "plan_end": release_date,
            "plan_file": "",
            "plan_href": "",
            "baseline_file": "",
            "baseline_version": "public-anonymized",
            "week_note": "公开匿名版不包含个人训练事实、处方或复盘。",
            "goal": "此页面仅展示工作台界面，不提供个人训练建议。",
            "objective_mode": "general_fitness",
        },
        "onboarding": {
            "completed": False,
            "message": "公开匿名版不包含个人建档与训练处方。",
        },
        "system": {"workbench_schema": 6, "release_mode": "public-anonymized", "instance_id": "public-anonymous-shell"},
        "knowledge": {"status": "not-shared"},
        "status": {"state": "public-anonymized", "reason": "个人训练数据未进入公开副本"},
        "calendar": {},
        "weekday": {name: "未排期" for name in PUBLIC_DAY_NAMES},
        "done": {},
        "rest_days": "公开匿名版不包含个人休息日安排。",
        "days": {
            name: {
                "date": "",
                "title": "公开匿名占位",
                "role": "无个人训练处方",
                "exercises": [],
            }
            for name in PUBLIC_DAY_NAMES
        },
        "timeline": [],
        "week": [],
        "phases": [],
        "charts": {},
        "goal_metrics": [],
        "reviews": [],
        "rules": [],
        "advice": "公开匿名版不包含个人训练处方。",
        "today_summary": None,
        "links": {},
        "documents": {},
        "notion": {
            "sync_mode": None,
            "source_queried_at": None,
            "latest_training_record_date": None,
            "latest_bodyweight_record_date": None,
            "snapshot_generated_at": None,
            "last_sync": None,
            "bodyweight": [],
            "baseline_kg": None,
            "baseline_note": "个人数据未公开",
            "sessions": [],
            "activity": [],
            "note": "",
            "latest_by_exercise": {},
            "main_lifts": [],
            "notion_url": None,
        },
        "sync": {
            "status": "stale",
            "last_attempt": None,
            "last_success": None,
            "reason": "公开匿名版不连接个人动态数据",
            "stale_fields": [],
        },
        "provenance": {
            "release": {"source_type": "public-anonymized-shell", "verified_at": released_at}
        },
        "release": {
            "mode": "public-anonymized",
            "anonymized": True,
            "contains_personal_data": False,
        },
    }


def disable_local_edit_capability(html: str) -> str:
    """Published copies never create Obsidian deep links, even when opened locally."""
    return LOCAL_EDIT_EXPRESSION.sub("''", html)


def encode_workbench_data(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


def public_shell_html(data: dict) -> str:
    return PUBLIC_SHELL_TEMPLATE.replace("__WORKBENCH_DATA__", encode_workbench_data(data))


def release_view_hash(html: str) -> str:
    view = DATA_BLOCK.sub(r"\1{}\3", html, count=1)
    return hashlib.sha256(view.encode("utf-8")).hexdigest()


def sanitize_html(source: str, mode: str, released_at: str) -> tuple[str, dict]:
    matches = DATA_BLOCK.findall(source)
    if len(matches) != 1:
        fail("正式工作台 workbench-data 数量不是 1")
    match = DATA_BLOCK.search(source)
    try:
        source_data = json.loads(match.group(2))
    except json.JSONDecodeError as exc:
        fail("workbench-data 不是合法 JSON: %s" % exc)

    if mode == "public-anonymized":
        cleaned = public_anonymized_data(source_data, released_at)
        output = public_shell_html(cleaned)
    else:
        cleaned = scrub(source_data)
        cleaned["release"] = {
            "mode": "private-portable",
            "anonymized": False,
            "contains_personal_data": True,
        }
        payload = encode_workbench_data(cleaned)
        output = source[:match.start()] + match.group(1) + payload + match.group(3) + source[match.end():]
        output = disable_local_edit_capability(output)
    if WINDOWS_PATH_IN_TEXT.search(output) or re.search(r"(?:obsidian|file)://", output, re.I):
        fail("发布副本仍包含本机路径、file URI 或 Obsidian 深链")
    if re.search(r"__[A-Z0-9_]+__", output):
        fail("发布副本仍包含未替换占位符")
    return output, cleaned


def project_file(root: Path, relative) -> Path | None:
    parsed = urlparse(str(relative or ""))
    if parsed.scheme or parsed.netloc:
        return None
    value = unquote(parsed.path).replace("/", os.sep)
    if not value or os.path.isabs(value):
        return None
    target = (root / value).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return None
    return target


def extract_asset_paths(html: str) -> list[str]:
    candidates = re.findall(r'url\(["\']?([^"\')]+)', html)
    candidates += re.findall(r'''(?:src|poster)\s*=\s*["']([^"']+)["']''', html, re.I)
    paths = []
    for raw in candidates:
        value = raw.strip()
        if not value or value.startswith(("data:", "http://", "https://", "#", "blob:")):
            continue
        parsed = urlparse(value)
        if parsed.scheme or parsed.netloc or not parsed.path:
            continue
        relative = unquote(parsed.path).replace("\\", "/").lstrip("/")
        if relative not in paths:
            paths.append(relative)
    return paths


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
    """Inspect the lexical path before resolve or mutation."""
    absolute = path.expanduser().absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if os.path.lexists(current) and is_link_like(current):
            return current
    return None


def safe_manifest_relative(value) -> str | None:
    if not isinstance(value, str) or not value or "\\" in value:
        return None
    relative = PurePosixPath(value)
    if relative.is_absolute() or any(part in ("", ".", "..") for part in relative.parts):
        return None
    return relative.as_posix()


def expected_parent_directories(files: set[str]) -> set[str]:
    expected = set()
    for relative in files:
        parent = PurePosixPath(relative).parent
        while str(parent) not in ("", "."):
            expected.add(parent.as_posix())
            parent = parent.parent
    return expected


def release_tree(root: Path) -> tuple[dict[str, Path], set[str]]:
    files = {}
    directories = set()
    for current, subdirs, names in os.walk(root, followlinks=False):
        current_path = Path(current)
        for name in list(subdirs):
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            if is_link_like(path):
                subdirs.remove(name)
                fail("已存在发布目录包含符号链接、junction 或 reparse 目录: " + relative)
            directories.add(relative)
        for name in names:
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            if is_link_like(path):
                fail("已存在发布目录包含符号链接或 reparse 文件: " + relative)
            files[relative] = path
    return files, directories


def validate_existing_release(deploy: Path) -> None:
    """Allow replacement only when the existing tree proves producer ownership and integrity."""
    if not os.path.lexists(deploy):
        return
    if is_link_like(deploy) or not deploy.is_dir():
        fail("已存在的发布目标不是受管普通目录，拒绝替换")

    actual_files, actual_directories = release_tree(deploy)
    manifest_path = actual_files.get(MANIFEST_NAME)
    if not manifest_path:
        fail("已存在目录缺少受管 release-manifest.json，拒绝替换且不会清理原目录")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        fail("已存在目录的 release-manifest.json 无法解析，拒绝替换: " + str(exc))
    if not isinstance(manifest, dict):
        fail("已存在目录的 release-manifest.json 顶层不是对象，拒绝替换")

    mode = manifest.get("release_mode")
    if (
        manifest.get("schema") != MANIFEST_SCHEMA
        or manifest.get("kind") != MANIFEST_KIND
        or manifest.get("producer") != MANIFEST_PRODUCER
        or manifest.get("fresh_staging") is not True
        or manifest.get("entrypoint") != "index.html"
        or mode not in RELEASE_MODES
        or not isinstance(manifest.get("allowed_files"), list)
        or not isinstance(manifest.get("files"), list)
    ):
        fail("已存在目录不具备本发布器的所有权标记，拒绝替换")

    private = mode == "private-portable"
    expected_flags = {
        "anonymized": not private,
        "contains_personal_data": private,
        "required_access": "private-authenticated" if private else "public",
    }
    if any(manifest.get(key) != value for key, value in expected_flags.items()):
        fail("已存在目录的发布清单隐私标记不完整，拒绝替换")

    allowed = [safe_manifest_relative(value) for value in manifest["allowed_files"]]
    if any(value is None for value in allowed) or len(allowed) != len(set(allowed)):
        fail("已存在目录的发布允许列表包含非法或重复路径，拒绝替换")
    allowed_set = set(allowed)
    if "index.html" not in allowed_set or MANIFEST_NAME not in allowed_set:
        fail("已存在目录的发布允许列表缺少固定入口，拒绝替换")
    if set(actual_files) != allowed_set:
        fail("已存在目录的实际文件与精确允许列表不一致，拒绝替换")
    if actual_directories != expected_parent_directories(allowed_set):
        fail("已存在目录含未受管目录或缺少清单目录，拒绝替换")

    entry_map = {}
    for entry in manifest["files"]:
        if not isinstance(entry, dict):
            fail("已存在目录的发布哈希条目无效，拒绝替换")
        relative = safe_manifest_relative(entry.get("path"))
        if not relative or relative in entry_map:
            fail("已存在目录的发布哈希路径非法或重复，拒绝替换")
        entry_map[relative] = entry
    expected_artifacts = allowed_set - {MANIFEST_NAME}
    if set(entry_map) != expected_artifacts:
        fail("已存在目录的发布哈希列表与允许列表不一致，拒绝替换")
    for relative, entry in entry_map.items():
        path = actual_files[relative]
        if entry.get("bytes") != path.stat().st_size or entry.get("sha256") != file_sha256(path):
            fail("已存在发布文件与清单哈希不一致，拒绝替换: " + relative)


def ensure_non_overlapping_paths(project: Path, deploy: Path) -> None:
    if not deploy.name or deploy == Path(deploy.anchor):
        fail("发布目录不能是磁盘根目录")
    try:
        deploy.relative_to(project)
        fail("发布目录不能位于个人训练系统内部")
    except ValueError:
        pass
    try:
        project.relative_to(deploy)
        fail("发布目录不能包含个人训练系统")
    except ValueError:
        pass
    if deploy.is_symlink():
        fail("发布目录不能是符号链接")
    if deploy.exists() and not deploy.is_dir():
        fail("发布目标已存在且不是目录")


def copy_relative_file(project: Path, staging: Path, relative: str) -> None:
    source = project_file(project, relative)
    target = project_file(staging, relative)
    if not source or not source.is_file() or not target:
        fail("发布所需文件不存在或路径不可迁移: " + relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(staging: Path, mode: str, released_at: str) -> None:
    artifacts = sorted(
        (path for path in staging.rglob("*") if path.is_file() and path.name != MANIFEST_NAME),
        key=lambda path: path.relative_to(staging).as_posix(),
    )
    file_entries = [
        {
            "path": path.relative_to(staging).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": file_sha256(path),
        }
        for path in artifacts
    ]
    allowed_files = [entry["path"] for entry in file_entries] + [MANIFEST_NAME]
    private = mode == "private-portable"
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "kind": MANIFEST_KIND,
        "producer": MANIFEST_PRODUCER,
        "release_mode": mode,
        "generated_at": released_at,
        "entrypoint": "index.html",
        "anonymized": not private,
        "contains_personal_data": private,
        "required_access": "private-authenticated" if private else "public",
        "fresh_staging": True,
        "allowed_files": sorted(allowed_files),
        "files": file_entries,
    }
    if mode == "public-anonymized":
        public_index = (staging / "index.html").read_text(encoding="utf-8")
        manifest["public_shell"] = PUBLIC_SHELL_ID
        manifest["public_shell_view_sha256"] = release_view_hash(public_index)
    (staging / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def path_identity(path: Path) -> tuple[int, int]:
    info = os.lstat(path)
    return info.st_dev, info.st_ino


def reserve_sibling_path(parent: Path, prefix: str) -> Path:
    reserved = Path(tempfile.mkdtemp(prefix=prefix, dir=str(parent)))
    reserved.rmdir()
    return reserved


def replace_deploy_tree(staging: Path, deploy: Path) -> None:
    """Promote a candidate, validate it in place, then commit or roll back."""
    link_component = first_link_component(deploy)
    if link_component:
        fail("发布目录路径不能经过符号链接、junction 或 reparse point: " + str(link_component))
    validate_existing_release(staging)
    candidate_identity = path_identity(staging)
    validate_existing_release(deploy)
    previous = None
    if os.path.lexists(deploy):
        previous = reserve_sibling_path(deploy.parent, deploy.name + "-previous-")
        os.replace(deploy, previous)
    try:
        os.replace(staging, deploy)
    except BaseException:
        if previous and previous.exists() and not deploy.exists():
            os.replace(previous, deploy)
        raise

    try:
        if is_link_like(deploy) or path_identity(deploy) != candidate_identity:
            raise RuntimeError("post-swap 发布目录身份与本次候选不一致")
        validate_existing_release(deploy)
    except BaseException as validation_error:
        quarantine = None
        try:
            if not os.path.lexists(deploy):
                raise RuntimeError("post-swap 失败后本次候选发布目录已经消失")
            if is_link_like(deploy) or path_identity(deploy) != candidate_identity:
                raise RuntimeError("post-swap 失败后目标已不是本次候选，拒绝移动未知目录")
            quarantine = reserve_sibling_path(deploy.parent, deploy.name + "-failed-")
            os.replace(deploy, quarantine)
            if previous:
                os.replace(previous, deploy)
                previous = None
        except BaseException as rollback_error:
            previous_hint = str(previous) if previous and os.path.lexists(previous) else "无"
            quarantine_hint = str(quarantine) if quarantine and os.path.lexists(quarantine) else "无"
            raise RuntimeError(
                "post-swap 终验失败且自动回滚未完成；旧受管副本=%s；失败候选隔离=%s"
                % (previous_hint, quarantine_hint)
            ) from rollback_error
        raise validation_error

    if previous and previous.exists():
        shutil.rmtree(previous)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--deploy", required=True)
    parser.add_argument("--mode", choices=RELEASE_MODES, default="private-portable")
    args = parser.parse_args()

    project = Path(args.project).resolve()
    deploy_input = Path(args.deploy).expanduser().absolute()
    link_component = first_link_component(deploy_input)
    if link_component:
        fail("发布目录路径不能经过符号链接、junction 或 reparse point: " + str(link_component))
    deploy = deploy_input.resolve()
    ensure_non_overlapping_paths(project, deploy)
    validate_existing_release(deploy)
    source_path = project / "健身工作台.html"
    if not source_path.is_file():
        fail("正式工作台不存在: " + str(source_path))
    deploy.parent.mkdir(parents=True, exist_ok=True)
    link_component = first_link_component(deploy)
    if link_component:
        fail("发布目录路径不能经过符号链接、junction 或 reparse point: " + str(link_component))

    released_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    sanitized, cleaned_data = sanitize_html(source_path.read_text(encoding="utf-8"), args.mode, released_at)
    staging = Path(tempfile.mkdtemp(prefix=deploy.name + "-staging-", dir=str(deploy.parent))).resolve()
    try:
        (staging / "index.html").write_text(sanitized, encoding="utf-8")
        if args.mode == "private-portable":
            for relative in extract_asset_paths(sanitized):
                copy_relative_file(project, staging, relative)
            plan_relative = cleaned_data.get("meta", {}).get("plan_file")
            if not plan_relative:
                fail("private-portable 发布缺少完整计划 HTML")
            copy_relative_file(project, staging, str(plan_relative).replace("\\", "/"))
        write_manifest(staging, args.mode, released_at)
        replace_deploy_tree(staging, deploy)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise

    print("FITNESS_WORKBENCH_RELEASE: PASS")
    print("mode: " + args.mode)
    print("index: " + str(deploy / "index.html"))
    print("manifest: " + str(deploy / MANIFEST_NAME))
    if args.mode == "private-portable":
        print("privacy: CONTAINS_PERSONAL_DATA; PRIVATE_AUTHENTICATED_ACCESS_REQUIRED")
    else:
        print("privacy: PUBLIC_ANONYMIZED; PERSONAL_TRAINING_DATA_REMOVED")


if __name__ == "__main__":
    main()
