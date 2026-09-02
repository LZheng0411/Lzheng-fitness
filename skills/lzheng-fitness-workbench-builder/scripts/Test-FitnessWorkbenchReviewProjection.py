#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression test: every indexed review is projected without a fixed cap."""

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
BUILDER_PATH = SCRIPT_DIR / "Build-FitnessWorkbenchData.py"


def load_builder():
    spec = importlib.util.spec_from_file_location("fitness_workbench_builder", BUILDER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载工作台构建器")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    builder = load_builder()
    with tempfile.TemporaryDirectory(prefix="fitness-review-projection-") as tmp:
        project = Path(tmp)
        review_dir = project / "训练复盘与状态" / "训练复盘"
        review_dir.mkdir(parents=True)

        review_rows = []
        expected_files = []
        for index in range(12):
            stem = f"review-{index:02d}"
            body = (
                "---\n"
                f"workbench_title: 第 {index + 1} 条复盘\n"
                f"workbench_lead: 唯一标记 {index:02d}\n"
                "---\n\n"
                f"# 第 {index + 1} 条复盘\n"
            )
            (review_dir / f"{stem}.md").write_text(body, encoding="utf-8")
            review_rows.append(
                {
                    "full_date": f"2026-08-{28 - index:02d}",
                    "week": f"W{12 - index}",
                    "day": "上肢A",
                    "file": stem,
                }
            )
            expected_files.append(f"训练复盘与状态/训练复盘/{stem}.md")

        projected = builder.build_reviews(review_rows, str(project))

        require(len(projected) == len(review_rows), "复盘投影数量与索引数量不一致")
        require(
            [item.get("file_path") for item in projected] == expected_files,
            "复盘投影没有保持索引顺序",
        )
        require(
            projected[-1].get("workbench_title") == "第 12 条复盘",
            "超过第 5 条的复盘没有完整读取",
        )
        require(
            "# 第 12 条复盘" in projected[-1].get("content_markdown", ""),
            "超过第 5 条的复盘正文没有嵌入工作台",
        )

    print("FITNESS_WORKBENCH_REVIEW_PROJECTION: PASS")


if __name__ == "__main__":
    main()
