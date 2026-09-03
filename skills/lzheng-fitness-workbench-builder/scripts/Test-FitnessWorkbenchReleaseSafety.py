#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression tests for release ownership, path safety and public anonymity."""

from __future__ import annotations

import hashlib
import json
import os
import re
import runpy
import subprocess
import sys
import tempfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
DATA_BLOCK = re.compile(r'<script id="workbench-data" type="application/json">([\s\S]*?)</script>')
MANIFEST_KIND = "lzheng-fitness-workbench-release"
MANIFEST_PRODUCER = "Prepare-FitnessWorkbenchRelease.py"


def fail(message: str) -> None:
    raise SystemExit("FITNESS_WORKBENCH_RELEASE_SAFETY: FAIL\n- " + message)


def execute(command: list[str], expect_success: bool = True) -> str:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    completed = subprocess.run(
        command,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    output = completed.stdout + completed.stderr
    if expect_success and completed.returncode:
        fail("命令失败：" + " ".join(command) + "\n" + output.strip())
    if not expect_success and completed.returncode == 0:
        fail("本应被安全闸门拒绝的命令却通过：" + " ".join(command))
    return output


def prepare(
    project: Path,
    release: Path,
    mode: str | None = None,
    expect_success: bool = True,
) -> str:
    command = [
        sys.executable,
        str(HERE / "Prepare-FitnessWorkbenchRelease.py"),
        "--project",
        str(project),
        "--deploy",
        str(release),
    ]
    if mode:
        command += ["--mode", mode]
    return execute(command, expect_success=expect_success)


def check(project: Path, release: Path, *extra: str, expect_success: bool = True) -> str:
    return execute(
        [
            sys.executable,
            str(HERE / "Check-FitnessWorkbench.py"),
            "--project",
            str(project),
            "--deploy",
            str(release),
            *extra,
        ],
        expect_success=expect_success,
    )


def tree_snapshot(root: Path) -> tuple[tuple[str, ...], dict[str, bytes]]:
    directories = tuple(
        sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_dir())
    )
    files = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda p: p.as_posix())
    }
    return directories, files


def assert_tree_unchanged(root: Path, before, label: str) -> None:
    if tree_snapshot(root) != before:
        fail(label + "失败后修改了原目录")


def release_data(release: Path) -> dict:
    blocks = DATA_BLOCK.findall((release / "index.html").read_text(encoding="utf-8"))
    if len(blocks) != 1:
        fail("发布副本 workbench-data 数量异常")
    return json.loads(blocks[0])


def refresh_index_manifest_entry(release: Path) -> None:
    index = release / "index.html"
    manifest_path = release / "release-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest.get("files", []):
        if entry.get("path") == "index.html":
            entry["bytes"] = index.stat().st_size
            entry["sha256"] = hashlib.sha256(index.read_bytes()).hexdigest()
            break
    else:
        fail("manifest 缺少 index.html 条目")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_release_data(release: Path, data: dict) -> None:
    """Tamper a temp release while keeping its file-integrity entry consistent."""
    index = release / "index.html"
    html = index.read_text(encoding="utf-8")
    match = DATA_BLOCK.search(html)
    if not match:
        fail("无法写入测试用 workbench-data")
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    index.write_text(html[:match.start(1)] + payload + html[match.end(1):], encoding="utf-8")
    refresh_index_manifest_entry(release)


def add_private_source_markers(project: Path) -> str:
    relative = "工作台与工具/健身工作台开发/界面素材/family-face-private.png"
    private_asset = project / relative
    private_asset.write_bytes(
        (project / "工作台与工具/健身工作台开发/界面素材/workbench-background.png").read_bytes()
    )
    html_path = project / "健身工作台.html"
    html = html_path.read_text(encoding="utf-8")
    html = re.sub(r"<title>[\s\S]*?</title>", "<title>Lzheng</title>", html, count=1)
    marker = '<div id="privateIdentity">LZ</div><img src="' + relative + '" alt="private family face">'
    html = re.sub(r"(<body\b[^>]*>)", r"\1" + marker, html, count=1)
    html_path.write_text(html, encoding="utf-8")
    return relative


def create_directory_link(link: Path, target: Path) -> None:
    if os.name == "nt":
        completed = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
        )
        if completed.returncode:
            fail("无法创建 junction 回归夹具: " + completed.stderr.decode(errors="replace"))
    else:
        link.symlink_to(target, target_is_directory=True)


def remove_directory_link(link: Path) -> None:
    if link.is_symlink():
        link.unlink()
    elif os.path.lexists(link):
        os.rmdir(link)


def assert_link_guard(project: Path, temp: Path) -> None:
    sentinel = b"junction-target-must-remain-byte-identical"
    for suffix, deploy_child in (("leaf", None), ("parent", "nested-release")):
        target = temp / ("junction-target-" + suffix)
        target.mkdir()
        sentinel_path = target / "sentinel.bin"
        sentinel_path.write_bytes(sentinel)
        before = tree_snapshot(target)
        link = temp / ("junction-link-" + suffix)
        create_directory_link(link, target)
        deploy = link if deploy_child is None else link / deploy_child
        try:
            rejected = prepare(project, deploy, "public-anonymized", expect_success=False)
            if not any(marker in rejected for marker in ("junction", "reparse", "符号链接")):
                fail("Prepare 没有明确拒绝路径链上的 link-like 组件")
            checked = check(
                project,
                deploy,
                "--expect-release-mode",
                "public-anonymized",
                expect_success=False,
            )
            if not any(marker in checked for marker in ("junction", "reparse", "符号链接")):
                fail("Checker 没有明确拒绝路径链上的 link-like 组件")
            assert_tree_unchanged(target, before, "junction/reparse 路径闸门")
            if sentinel_path.read_bytes() != sentinel:
                fail("junction 目标 sentinel 字节发生变化")
            if deploy_child is not None and (target / deploy_child).exists():
                fail("Prepare 通过 junction 父路径创建了发布目录")
        finally:
            remove_directory_link(link)
        if os.path.lexists(link):
            fail("测试目录链接未清理")
        assert_tree_unchanged(target, before, "目录链接清理不得触及目标")


def assert_post_swap_rollback(project: Path, temp: Path) -> None:
    existing = temp / "post-swap-existing"
    prepare(project, existing)
    existing_before = tree_snapshot(existing)
    unrelated = temp / "unrelated-sentinel.bin"
    unrelated_bytes = b"unrelated-sibling-must-never-be-deleted"
    unrelated.write_bytes(unrelated_bytes)

    for fault_name in ("tamper", "read-failure"):
        candidate = temp / ("post-swap-candidate-" + fault_name)
        prepare(project, candidate, "public-anonymized")
        module = runpy.run_path(str(HERE / "Prepare-FitnessWorkbenchRelease.py"))
        replace = module["replace_deploy_tree"]
        original_validate = replace.__globals__["validate_existing_release"]
        deploy_checks = 0

        def injected_validate(path: Path) -> None:
            nonlocal deploy_checks
            if Path(path) == existing:
                deploy_checks += 1
                if deploy_checks == 2:
                    if fault_name == "tamper":
                        index = Path(path) / "index.html"
                        index.write_bytes(index.read_bytes() + b"\nPOST_SWAP_TAMPER")
                    else:
                        raise OSError("injected post-swap read failure")
            original_validate(path)

        replace.__globals__["validate_existing_release"] = injected_validate
        try:
            replace(candidate, existing)
        except BaseException:
            pass
        else:
            fail("post-swap %s 故障没有触发事务失败" % fault_name)
        assert_tree_unchanged(existing, existing_before, "post-swap %s 回滚" % fault_name)
        if unrelated.read_bytes() != unrelated_bytes:
            fail("post-swap 回滚删除或修改了无关兄弟文件")

    new_candidate = temp / "post-swap-new-target-candidate"
    new_target = temp / "post-swap-new-target"
    prepare(project, new_candidate, "public-anonymized")
    module = runpy.run_path(str(HERE / "Prepare-FitnessWorkbenchRelease.py"))
    replace = module["replace_deploy_tree"]
    original_validate = replace.__globals__["validate_existing_release"]

    def fail_new_target_read(path: Path) -> None:
        if Path(path) == new_target and os.path.lexists(path):
            raise OSError("injected new-target post-swap read failure")
        original_validate(path)

    replace.__globals__["validate_existing_release"] = fail_new_target_read
    try:
        replace(new_candidate, new_target)
    except BaseException:
        pass
    else:
        fail("新目标 post-swap 读取故障没有触发事务失败")
    if os.path.lexists(new_target):
        fail("新目标 post-swap 失败后仍留下被宣称的 deploy")
    if unrelated.read_bytes() != unrelated_bytes:
        fail("新目标回滚删除或修改了无关兄弟文件")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="lzheng-release-safety-") as raw:
        temp = Path(raw)
        project = temp / "私人训练系统"
        execute([sys.executable, str(HERE / "Initialize-FitnessWorkbench.py"), "--target", str(project)])
        private_asset_relative = add_private_source_markers(project)

        leaked_windows_path = "C:" + "\\Users\\owner\\review.md"
        leaked_obsidian_uri = "obsidian:" + "//open?path=C%3A%5CUsers%5Cowner"
        unmanaged = temp / "无所有权旧发布目录"
        unmanaged.mkdir()
        (unmanaged / "健身工作台.html").write_text(
            f'<a href="{leaked_obsidian_uri}">{leaked_windows_path}</a>',
            encoding="utf-8",
        )
        stale_dir = unmanaged / "旧发布备份"
        stale_dir.mkdir()
        (stale_dir / "backup.html").write_text("stale", encoding="utf-8")
        unmanaged_before = tree_snapshot(unmanaged)
        rejected = prepare(project, unmanaged, expect_success=False)
        if "manifest" not in rejected and "所有权" not in rejected:
            fail("Prepare 没有明确拒绝无所有权发布目录")
        assert_tree_unchanged(unmanaged, unmanaged_before, "无所有权目录拒绝")

        assert_link_guard(project, temp)
        assert_post_swap_rollback(project, temp)

        release = temp / "受管发布目录"
        prepare(project, release)
        private_manifest = json.loads((release / "release-manifest.json").read_text(encoding="utf-8"))
        if (
            private_manifest.get("schema") != 2
            or private_manifest.get("kind") != MANIFEST_KIND
            or private_manifest.get("producer") != MANIFEST_PRODUCER
        ):
            fail("受管发布 manifest 缺少 schema=2 所有权标记")
        if private_manifest.get("release_mode") != "private-portable":
            fail("默认模式不是 private-portable")
        if private_manifest.get("anonymized") is not False or private_manifest.get("contains_personal_data") is not True:
            fail("private-portable 被误称为匿名或不含个人数据")
        private_index = (release / "index.html").read_text(encoding="utf-8")
        if "Lzheng" not in private_index or ">LZ<" not in private_index or private_asset_relative not in private_index:
            fail("private-portable 没有保持私人页面身份或本地媒体行为")
        if not (release / private_asset_relative).is_file():
            fail("private-portable 没有复制页面实际引用的私人媒体")

        gated = check(project, release, expect_success=False)
        if "--allow-private-portable" not in gated:
            fail("private-portable 没有要求显式确认私有访问")
        passed = check(
            project,
            release,
            "--allow-private-portable",
            "--expect-release-mode",
            "private-portable",
        )
        if "deploy: PASS (private-portable)" not in passed:
            fail("显式确认后的 private-portable 检查未通过")

        injected = release / "健身工作台.html"
        injected.write_text(f"{leaked_obsidian_uri}\n{leaked_windows_path}\n", encoding="utf-8")
        rejected = check(project, release, "--allow-private-portable", expect_success=False)
        if "健身工作台.html" not in rejected or "允许列表外文件" not in rejected:
            fail("全发布树检查没有明确拒绝回流的旧健身工作台.html")
        tampered_before = tree_snapshot(release)
        rejected = prepare(project, release, "public-anonymized", expect_success=False)
        if "允许列表" not in rejected and "完整" not in rejected:
            fail("Prepare 没有拒绝含额外旧文件的受管目录")
        assert_tree_unchanged(release, tampered_before, "额外旧文件拒绝")
        injected.unlink()

        prepare(project, release, "public-anonymized")
        public_manifest = json.loads((release / "release-manifest.json").read_text(encoding="utf-8"))
        if public_manifest.get("release_mode") != "public-anonymized":
            fail("公开模式没有写入 public-anonymized manifest")
        if public_manifest.get("anonymized") is not True or public_manifest.get("contains_personal_data") is not False:
            fail("public-anonymized 的隐私标记错误")
        if public_manifest.get("public_shell") != "fitness-public-anonymous-v1":
            fail("public-anonymized 缺少固定静态壳标记")
        if set(public_manifest.get("allowed_files", [])) != {"index.html", "release-manifest.json"}:
            fail("public-anonymized 打包了固定静态壳之外的文件")
        if {path.relative_to(release).as_posix() for path in release.rglob("*") if path.is_file()} != {
            "index.html",
            "release-manifest.json",
        }:
            fail("public-anonymized 仍复制了本地媒体或其他文件")

        public_package_text = "\n".join(
            path.read_text(encoding="utf-8") for path in release.rglob("*") if path.is_file()
        )
        for leaked in ("Lzheng", ">LZ<", "family-face-private.png"):
            if leaked in public_package_text:
                fail("public-anonymized 泄露源页面身份或私人媒体: " + leaked)
        public_index = (release / "index.html").read_text(encoding="utf-8")
        if re.search(r"<(?:img|video|audio|source|iframe|object|embed)\b", public_index, re.I):
            fail("public-anonymized 固定静态壳仍包含媒体或嵌入标签")

        public_data = release_data(release)
        for key, empty in (
            ("timeline", []),
            ("week", []),
            ("reviews", []),
            ("documents", {}),
            ("links", {}),
        ):
            if public_data.get(key) != empty:
                fail("public-anonymized 仍包含个人数据字段：" + key)
        if not isinstance(public_data.get("rest_days"), str):
            fail("public-anonymized rest_days 没有保持页面期望的字符串类型")
        public_days = public_data.get("days")
        if not isinstance(public_days, dict) or set(public_days) != {"上肢A", "腿B", "上肢B", "腿A"}:
            fail("public-anonymized 没有提供静态壳所需的四个占位训练日")
        if any(not isinstance(item.get("exercises"), list) or item["exercises"] for item in public_days.values()):
            fail("public-anonymized 占位训练日类型错误或仍包含处方")
        notion = public_data.get("notion", {})
        for key in ("bodyweight", "sessions", "main_lifts", "activity"):
            if notion.get(key) != []:
                fail("public-anonymized Notion 字段不是空列表：" + key)
        if notion.get("latest_by_exercise") != {} or notion.get("notion_url") not in (None, ""):
            fail("public-anonymized 仍包含动作历史或 Notion URL")

        passed = check(project, release, "--expect-release-mode", "public-anonymized")
        if "deploy: PASS (public-anonymized)" not in passed:
            fail("public-anonymized 检查未通过")

        identity_tamper = (release / "index.html").read_text(encoding="utf-8").replace(
            "</main>", '<p id="leakedIdentity">LZ</p></main>', 1
        )
        (release / "index.html").write_text(identity_tamper, encoding="utf-8")
        refresh_index_manifest_entry(release)
        rejected = check(
            project,
            release,
            "--expect-release-mode",
            "public-anonymized",
            expect_success=False,
        )
        if "身份中立" not in rejected and "固定静态壳" not in rejected:
            fail("Checker 没有拒绝带身份文本的伪公开静态壳")
        prepare(project, release, "public-anonymized")

        broken_data = json.loads(json.dumps(release_data(release), ensure_ascii=False))
        broken_data["rest_days"] = []
        broken_data["notion"]["bodyweight"] = [{"date": "2026-01-01", "kg": 70}]
        broken_data["notion"]["sessions"] = [{"date": "2026-01-01", "day": "训练"}]
        broken_data["notion"]["main_lifts"] = {}
        broken_data["notion"]["activity"] = [{"date": "2026-01-01"}]
        broken_data["notion"]["latest_by_exercise"] = {"卧推": {"kg": 1}}
        broken_data["notion"]["notion_url"] = "https://www.notion.so/private"
        write_release_data(release, broken_data)
        rejected = check(
            project,
            release,
            "--expect-release-mode",
            "public-anonymized",
            expect_success=False,
        )
        for marker in (
            "rest_days",
            "bodyweight",
            "sessions",
            "main_lifts",
            "activity",
            "latest_by_exercise",
            "Notion URL",
        ):
            if marker not in rejected:
                fail("Checker 没有拒绝匿名包中的字段：" + marker)
        prepare(project, release, "public-anonymized")

        stale_text = release / "旧目录" / "data.txt"
        stale_text.parent.mkdir()
        stale_text.write_text(leaked_windows_path, encoding="utf-8")
        rejected = check(
            project,
            release,
            "--expect-release-mode",
            "public-anonymized",
            expect_success=False,
        )
        if "旧目录/data.txt" not in rejected.replace("\\", "/"):
            fail("全发布树检查没有报告嵌套陈旧文件")
        stale_before = tree_snapshot(release)
        prepare(project, release, "public-anonymized", expect_success=False)
        assert_tree_unchanged(release, stale_before, "嵌套陈旧文件拒绝")
        stale_text.unlink()
        stale_text.parent.rmdir()
        check(project, release, "--expect-release-mode", "public-anonymized")

        clean_index = (release / "index.html").read_bytes()
        (release / "index.html").write_bytes(clean_index + b"\nTAMPERED")
        hash_tampered_before = tree_snapshot(release)
        rejected = prepare(project, release, "public-anonymized", expect_success=False)
        if "哈希" not in rejected:
            fail("Prepare 没有明确拒绝 manifest 哈希不匹配的目录")
        assert_tree_unchanged(release, hash_tampered_before, "哈希不一致目录拒绝")
        (release / "index.html").write_bytes(clean_index)
        check(project, release, "--expect-release-mode", "public-anonymized")

    print("FITNESS_WORKBENCH_RELEASE_SAFETY: PASS")


if __name__ == "__main__":
    main()
