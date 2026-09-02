#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prepare a self-contained, explicitly public personal workbench release."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote
from pathlib import PurePosixPath

HERE = Path(__file__).resolve().parent
PRIVATE_PREPARE = HERE / "Prepare-FitnessWorkbenchEncryptedRelease.py"
SCRIPT_VERSION = "1.1.0"
KIND = "lzheng-fitness-workbench-public-personal-release"
PRODUCER = "Prepare-FitnessWorkbenchPublicPersonalRelease.py"
REQUIRED_FILES = {"index.html", "release-manifest.json"}
PLAN_LINK_MARKER = "linkBox.appendChild(linkCard('完整训练计划', m.plan_href, '直接打开 ' + m.source_version, true));"
PLAN_LINK_REPLACEMENT = r'''function openPublishedPlan(url){
    if(typeof url!=='string'||!url||url.indexOf('data:')===0){return;}
    docOverlay.querySelector('.doc-dialog').classList.add('plan-reader-dialog');
    docTitle.textContent='完整训练计划';
    if(typeof docEyebrow!=='undefined'&&docEyebrow)docEyebrow.textContent='FULL TRAINING PLAN / 完整训练计划';
    docObsidian.hidden=true;docObsidian.href='#';docBody.replaceChildren();
    var frame=document.createElement('iframe');frame.className='doc-plan-frame';frame.title='完整训练计划';frame.setAttribute('sandbox','allow-scripts');frame.style.cssText='display:block;width:100%;height:min(76vh,840px);border:0;background:#fff';frame.src=url;docBody.appendChild(frame);
    docPreviousFocus=document.activeElement;document.body.classList.add('doc-reader-open');docOverlay.hidden=false;document.body.style.overflow='hidden';document.getElementById('docClose').focus();
  }
  var planAction=typeof m.plan_href==='string'&&m.plan_href.indexOf('data:')!==0?function(){openPublishedPlan(m.plan_href);}:null;
  linkBox.appendChild(planAction?linkCard('完整训练计划','', '在工作台内阅读 ' + m.source_version,false,planAction):linkCard('完整训练计划',m.plan_href,'直接打开 '+m.source_version,true));'''


class PublicReleaseError(RuntimeError):
    pass


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载私人发布验证模块")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


private_module = load(PRIVATE_PREPARE, "lzheng_private_source_for_public")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name("." + path.name + ".tmp")
    staging.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(staging, path)


def promote(staging: Path, output: Path) -> None:
    if output.exists():
        try:
            old = json.loads((output / "release-manifest.json").read_text(encoding="utf-8-sig"))
        except Exception as exc:
            raise PublicReleaseError("拒绝覆盖未受管的公开个人发布目录") from exc
        if old.get("kind") != KIND:
            raise PublicReleaseError("拒绝覆盖非公开个人版发布目录")
        retired = output.with_name("." + output.name + ".retired")
        if retired.exists():
            raise PublicReleaseError("公开个人版 retired 目录已存在")
        os.replace(output, retired)
        os.replace(staging, output)
        shutil.rmtree(retired)
    else:
        os.replace(staging, output)


def normalize_relative(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    candidate = unquote(value).replace("\\", "/")
    path = PurePosixPath(candidate)
    if path.is_absolute() or ".." in path.parts:
        raise PublicReleaseError("公开个人版资源路径不安全")
    return path.as_posix()


def resource_map(source: Path, manifest: dict[str, Any], data: dict[str, Any]) -> dict[str, str]:
    allowed = set(manifest.get("allowed_files", [])) - REQUIRED_FILES
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    plan = normalize_relative(meta.get("plan_file"))
    if plan is not None and plan not in allowed:
        raise PublicReleaseError("完整计划不在受管私人副本内")
    mapping: dict[str, str] = {}
    for rel in sorted(allowed):
        source_file = source / PurePosixPath(rel)
        if not source_file.is_file():
            raise PublicReleaseError("受管私人副本缺少资源: " + rel)
        if rel == plan:
            mapping[rel] = "plans/current-plan.html"
            continue
        suffix = PurePosixPath(rel).suffix.lower()
        mapping[rel] = "assets/" + sha256(source_file)[:16] + suffix
    return mapping


def rewrite_references(html: str, mapping: dict[str, str]) -> str:
    for source_rel, target_rel in mapping.items():
        for reference in tuple(dict.fromkeys((source_rel, quote(source_rel, safe="/")))):
            html = html.replace(reference, target_rel)
    return html


def make_public_html(source: Path) -> tuple[bytes, dict[str, str]]:
    manifest = private_module.validate_source(source)
    html = (source / "index.html").read_text(encoding="utf-8-sig")
    pattern = re.compile(r'(<script id="workbench-data" type="application/json">)(.*?)(</script>)', re.S)
    match = pattern.search(html)
    if not match:
        raise PublicReleaseError("工作台缺少唯一 workbench-data")
    try:
        data = json.loads(match.group(2))
    except json.JSONDecodeError as exc:
        raise PublicReleaseError("workbench-data 无法解析") from exc
    if not isinstance(data, dict):
        raise PublicReleaseError("workbench-data 必须是对象")
    mapping = resource_map(source, manifest, data)
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else None
    plan = normalize_relative(meta.get("plan_file")) if meta is not None else None
    if meta is not None and plan in mapping:
        meta["plan_file"] = mapping[plan]
        meta["plan_href"] = mapping[plan]
    data["release"] = {
        "mode": "public-personal-authorized",
        "contains_personal_data": True,
        "user_authorized_public": True,
        "required_access": "public",
        "generated_by": PRODUCER,
    }
    replacement = match.group(1) + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + match.group(3)
    html = html[: match.start()] + replacement + html[match.end() :]
    html = rewrite_references(html, mapping)
    if PLAN_LINK_MARKER in html:
        html = html.replace(PLAN_LINK_MARKER, PLAN_LINK_REPLACEMENT, 1)
    if html.count('<script id="workbench-data" type="application/json">') != 1:
        raise PublicReleaseError("公开个人版 workbench-data 数量异常")
    if "private-payload.json" in html or "请输入解密密码" in html:
        raise PublicReleaseError("公开个人版仍包含密码启动器")
    return html.encode("utf-8"), mapping


def build(source: Path, output: Path) -> dict[str, Any]:
    source = source.expanduser().resolve()
    output = output.expanduser().absolute().resolve()
    html, mapping = make_public_html(source)
    staging = output.with_name("." + output.name + ".candidate")
    if staging.exists():
        raise PublicReleaseError("公开个人版候选目录已存在")
    staging.mkdir(parents=True)
    try:
        (staging / "index.html").write_bytes(html)
        for source_rel, target_rel in mapping.items():
            target = staging / PurePosixPath(target_rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / PurePosixPath(source_rel), target)
        allowed_files = sorted(REQUIRED_FILES | set(mapping.values()))
        files = []
        for rel in allowed_files:
            if rel == "release-manifest.json":
                continue
            path = staging / PurePosixPath(rel)
            files.append({"path": rel, "bytes": path.stat().st_size, "sha256": sha256(path)})
        manifest = {
            "schema": 1,
            "kind": KIND,
            "producer": PRODUCER,
            "producer_version": SCRIPT_VERSION,
            "release_mode": "public-personal-authorized",
            "contains_personal_data": True,
            "user_authorized_public": True,
            "required_access": "public",
            "entrypoint": "index.html",
            "allowed_files": allowed_files,
            "source_release": {
                "mode": "private-portable",
                "manifest_sha256": sha256(source / "release-manifest.json"),
            },
            "files": files,
        }
        atomic_json(staging / "release-manifest.json", manifest)
        promote(staging, output)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return {
        "status": "PASS",
        "release_dir": str(output),
        "mode": "public-personal-authorized",
        "files": sorted(REQUIRED_FILES | set(mapping.values())),
        "index_sha256": sha256(output / "index.html"),
        "manifest_sha256": sha256(output / "release-manifest.json"),
        "plaintext_bytes": len(html),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare an explicitly authorized public personal workbench")
    parser.add_argument("--private-release", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--receipt")
    parser.add_argument("--confirm-public-personal-data", action="store_true")
    args = parser.parse_args(argv)
    receipt = Path(args.receipt).expanduser().absolute() if args.receipt else None
    try:
        if not args.confirm_public_personal_data:
            raise PublicReleaseError("必须显式确认个人计划、体重、复盘和来源将公开")
        result = build(Path(args.private_release), Path(args.out))
        if receipt:
            atomic_json(receipt, {"schema": 1, "kind": "lzheng_fitness_workbench_public_personal_release_receipt", "claims": {"formal_refreshed": False, "release_prepared": True, "deployed": False, "online_verified": False}, "result": result})
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (PublicReleaseError, private_module.ReleaseError, OSError, ValueError) as exc:
        result = {"status": "FAIL", "error": str(exc)}
        if receipt:
            atomic_json(receipt, {"schema": 1, "kind": "lzheng_fitness_workbench_public_personal_release_receipt", "claims": {"formal_refreshed": False, "release_prepared": False, "deployed": False, "online_verified": False}, "result": result})
        print(json.dumps(result, ensure_ascii=False), file=__import__("sys").stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
