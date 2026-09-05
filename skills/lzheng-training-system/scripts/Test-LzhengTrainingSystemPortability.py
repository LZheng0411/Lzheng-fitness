#!/usr/bin/env python3
"""Regression test for whole-suite moves and legacy absolute-path migration."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
SYSTEM = HERE / "lzheng_training_system.py"


def fail(message: str) -> None:
    raise SystemExit("LZHENG_TRAINING_SYSTEM_PORTABILITY: FAIL\n- " + message)


def run(command: list[str]) -> str:
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
    if completed.returncode:
        fail("命令失败：" + " ".join(command) + "\n" + (completed.stdout + completed.stderr).strip())
    return completed.stdout


def config_path(root: Path) -> Path:
    return root / "系统" / "lzheng-system.json"


def assert_portable(root: Path) -> dict:
    path = config_path(root)
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    expected = {
        "project_root": "个人训练系统",
        "skills_root": "@runtime",
        "backup_root": "系统/backups",
    }
    for key, value in expected.items():
        if data.get(key) != value:
            fail(f"{key} 不是可迁移值：{data.get(key)!r}")
    if data.get("portable_config_version") != 1:
        fail("配置缺少 portable_config_version=1")
    text = path.read_text(encoding="utf-8-sig")
    if str(root) in text:
        fail("配置仍保存当前电脑的绝对系统路径")
    return data


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="lzheng-suite-portable-") as raw:
        temp = Path(raw)
        original = temp / "旧电脑 系统"
        moved = temp / "新电脑（中文 空格）" / "健身系统-已改名"

        output = run([sys.executable, str(SYSTEM), "bootstrap", "--target", str(original)])
        if "LZHENG_TRAINING_SYSTEM: PASS" not in output:
            fail("初始化未通过")
        assert_portable(original)

        legacy_path = config_path(original)
        legacy = json.loads(legacy_path.read_text(encoding="utf-8-sig"))
        legacy["project_root"] = str(original / "个人训练系统")
        legacy["skills_root"] = r"Z:\\old-computer\\skills"
        legacy["backup_root"] = r"Z:\\old-computer\\backups"
        legacy.pop("portable_config_version", None)
        legacy_path.write_text(json.dumps(legacy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        moved.parent.mkdir(parents=True)
        shutil.move(str(original), str(moved))
        output = run([sys.executable, str(SYSTEM), "doctor", "--root", str(moved)])
        if "LZHENG_TRAINING_SYSTEM_DOCTOR: PASS" not in output:
            fail("移动后 doctor 未通过")
        migrated = assert_portable(moved)
        if not migrated.get("paths_migrated_at"):
            fail("旧配置迁移后未记录迁移时间")
        backups = list((moved / "系统/backups/config-migrations").glob("*.json"))
        if len(backups) != 1:
            fail("旧配置迁移备份数量异常")

        output = run([sys.executable, str(SYSTEM), "upgrade", "--root", str(moved)])
        if "LZHENG_TRAINING_SYSTEM_UPGRADE: CONFIG_ONLY" not in output:
            fail("移动后 upgrade 未通过")
        assert_portable(moved)

    print("LZHENG_TRAINING_SYSTEM_PORTABILITY: PASS")


if __name__ == "__main__":
    main()
