#!/usr/bin/env python3
"""Export the six source-limited expert modules into the portable Skill bundle.

The exporter copies only distilled Markdown. Raw books, article snapshots,
private training records, and machine-specific paths are deliberately excluded.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from pathlib import Path


MODULES = (
    {
        "id": "alan-aragon-flexible-dieting",
        "source_dir": "Alan Aragon灵活饮食营养专家",
        "display_name": "Alan Aragon 灵活饮食营养专家",
        "source": "Flexible Dieting (2022)",
        "status": "book_distilled_plan_review_accepted",
        "variables": ["nutrition", "energy_balance", "macros", "supplements", "adherence", "maintenance"],
        "excluded": ["medical nutrition", "eating-disorder treatment", "post-2022 author positions"],
    },
    {
        "id": "brad-schoenfeld-hypertrophy",
        "source_dir": "Brad Schoenfeld增肌研究专家",
        "display_name": "Brad Schoenfeld 增肌研究专家",
        "source": "Science and Development of Muscle Hypertrophy, Second Edition (2021)",
        "status": "book_distilled_two_entries_accepted",
        "variables": ["hypertrophy", "volume", "frequency", "failure", "range_of_motion", "concurrent_training"],
        "excluded": ["medical decisions", "post-2021 author positions", "current user facts"],
    },
    {
        "id": "brukner-khan-return-to-sport",
        "source_dir": "Brukner-Khan运动康复与返场专家",
        "display_name": "Brukner 与 Khan 运动康复与返场专家",
        "source": "Brukner & Khan's Clinical Sports Medicine, Fourth Edition (2012)",
        "status": "book_distilled_plan_return_accepted",
        "variables": ["medically_cleared_return", "functional_progression", "return_to_sport", "secondary_prevention"],
        "excluded": ["diagnosis", "imaging", "medication", "surgery", "emergency care", "current guidelines"],
    },
    {
        "id": "dan-john-intervention-easy-strength",
        "source_dir": "Dan John训练干预与Easy Strength专家",
        "wiki_dir": "Dan John训练干预与Easy Strength",
        "display_name": "Dan John 训练干预与 Easy Strength 专家",
        "source": "Intervention (2013) and Easy Strength Omnibook (2022)",
        "status": "content_ready_entry_acceptance_pending",
        "variables": ["point_a", "goal_clarity", "movement_gap", "return_to_basics", "low_fatigue_practice"],
        "excluded": ["medical decisions", "nutrition prescription", "precise cycle dosage", "current user facts"],
    },
    {
        "id": "eric-helms-training-pyramid",
        "source_dir": "Eric Helms训练金字塔专家",
        "wiki_dir": "Eric Helms训练金字塔",
        "display_name": "Eric Helms 训练金字塔专家",
        "source": "The Muscle & Strength Training Pyramid: Training, Second Edition (2018)",
        "status": "content_ready_entry_acceptance_pending",
        "variables": ["adherence", "training_structure", "volume", "intensity", "frequency", "progression", "deload", "peaking"],
        "excluded": ["medical decisions", "post-2018 author positions", "current user facts"],
    },
    {
        "id": "greg-nuckols-strength-periodization",
        "source_dir": "Greg Nuckols增力与力量周期",
        "wiki_dir": "Greg Nuckols增力与力量周期",
        "display_name": "Greg Nuckols 增力与力量周期专家",
        "source": "Stronger by Science public articles, cutoff 2026-08-10",
        "status": "content_ready_entry_acceptance_pending",
        "variables": ["strength_stall", "specificity", "volume", "frequency", "periodization", "autoregulation", "peaking", "technique_hypothesis"],
        "excluded": ["complete plan ownership", "medical decisions", "post-cutoff positions", "current user facts"],
    },
)

WIKI_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]")
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def clean_name(value: str) -> str:
    return value.strip().replace("\\", "/")


def rel_link(from_path: Path, to_path: Path) -> str:
    return Path(os.path.relpath(to_path, from_path.parent)).as_posix()


def rewrite_markdown(text: str, source_file: Path, out_file: Path, module: dict, source_root: Path, wiki_root: Path) -> str:
    module_source = source_root / module["source_dir"]
    module_out = out_file.parents[0]
    while module_out.name not in {module["id"], "experts"} and module_out.parent != module_out:
        module_out = module_out.parent

    def wiki_replace(match: re.Match[str]) -> str:
        raw_target = clean_name(match.group(1))
        label = (match.group(2) or Path(raw_target).name).strip()
        candidates: list[tuple[Path, Path]] = []

        if raw_target.startswith("知识卡/"):
            candidates.append((module_source / f"{raw_target}.md", module_out / f"{raw_target}.md"))
        elif "/Wiki/训练与周期/" in raw_target and module.get("wiki_dir"):
            marker = f"/Wiki/训练与周期/{module['wiki_dir']}/"
            if marker in raw_target:
                tail = raw_target.split(marker, 1)[1]
                candidates.append((wiki_root / module["wiki_dir"] / f"{tail}.md", module_out / "knowledge" / f"{tail}.md"))
        elif raw_target.endswith(f"/Wiki/训练与周期/{module.get('wiki_dir', '')}/README"):
            candidates.append((wiki_root / module["wiki_dir"] / "README.md", module_out / "knowledge" / "README.md"))
        elif "/" not in raw_target:
            candidates.append((module_source / f"{raw_target}.md", module_out / f"{raw_target}.md"))

        for source_candidate, out_candidate in candidates:
            if source_candidate.is_file() and out_candidate.is_file():
                return f"[{label}]({rel_link(out_file, out_candidate)})"
        return label

    def md_replace(match: re.Match[str]) -> str:
        label, target = match.group(1), clean_name(match.group(2)).strip("<>")
        if target.startswith(("https://", "http://", "mailto:")):
            return match.group(0)
        return label

    text = WIKI_RE.sub(wiki_replace, text)
    text = MD_LINK_RE.sub(md_replace, text)
    text = text.replace("E:\\obsidian", "private source vault")
    text = text.replace("E:/obsidian", "private source vault")
    return text


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def export_module(module: dict, source_root: Path, wiki_root: Path, experts_out: Path) -> dict:
    source_dir = source_root / module["source_dir"]
    if not source_dir.is_dir():
        raise SystemExit(f"Missing expert source directory: {source_dir}")

    module_out = experts_out / module["id"]
    module_out.mkdir(parents=True, exist_ok=True)

    source_files = sorted(source_dir.rglob("*.md"))
    for source_file in source_files:
        rel = source_file.relative_to(source_dir)
        out_file = module_out / rel
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(source_file.read_text(encoding="utf-8"), encoding="utf-8")

    knowledge_files: list[Path] = []
    if module.get("wiki_dir"):
        wiki_dir = wiki_root / module["wiki_dir"]
        if not wiki_dir.is_dir():
            raise SystemExit(f"Missing expert knowledge directory: {wiki_dir}")
        for source_file in sorted(wiki_dir.rglob("*.md")):
            rel = source_file.relative_to(wiki_dir)
            out_file = module_out / "knowledge" / rel
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(source_file.read_text(encoding="utf-8"), encoding="utf-8")
            knowledge_files.append(out_file)
    else:
        knowledge_files = list((module_out / "知识卡").rglob("*.md"))

    # Rewrite after every target exists, so internal links can be resolved.
    for out_file in sorted(module_out.rglob("*.md")):
        relative = out_file.relative_to(module_out)
        if relative.parts and relative.parts[0] == "knowledge":
            source_file = wiki_root / module["wiki_dir"] / Path(*relative.parts[1:])
        else:
            source_file = source_dir / relative
        text = rewrite_markdown(out_file.read_text(encoding="utf-8"), source_file, out_file, module, source_root, wiki_root)
        out_file.write_text(text, encoding="utf-8")

    boundary = (
        f"# {module['display_name']}：公开来源边界\n\n"
        f"- 主源与版本：{module['source']}\n"
        f"- 模块性质：来源限定的蒸馏知识，不模拟专家本人，也不代表出版或截止日期后的观点。\n"
        f"- 当前状态：`{module['status']}`\n"
        f"- 可处理变量：{'、'.join(module['variables'])}\n"
        f"- 明确排除：{'、'.join(module['excluded'])}\n\n"
        "公开包不分发原书、文章快照、转换全文、私有训练数据或来源文件路径。"
        "当前事实和最终训练处方始终由调用它的 Lzheng 主 Skill 所有。\n"
    )
    (module_out / "PUBLIC-SOURCE-BOUNDARY.md").write_text(boundary, encoding="utf-8")

    manifest = {
        "schema": 1,
        "id": module["id"],
        "display_name": module["display_name"],
        "source": module["source"],
        "status": module["status"],
        "entry": "00-专家总入口.md" if (module_out / "00-专家总入口.md").is_file() else "README.md",
        "source_boundary": "PUBLIC-SOURCE-BOUNDARY.md",
        "variables": module["variables"],
        "excluded": module["excluded"],
        "distilled_markdown_files": len(list(module_out.rglob("*.md"))),
        "knowledge_files": len(knowledge_files),
        "raw_sources_included": False,
    }
    write_json(module_out / "module.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the portable Lzheng expert library from distilled local modules.")
    parser.add_argument("--modules-root", type=Path, required=True, help="Directory containing the six distilled expert modules")
    parser.add_argument("--wiki-root", type=Path, required=True, help="Directory containing distilled expert knowledge cards")
    parser.add_argument("--out", type=Path, required=True, help="Output references directory for the expert library Skill")
    parser.add_argument("--force", action="store_true", help="Replace an existing generated experts directory")
    args = parser.parse_args()

    source_root = args.modules_root.resolve()
    wiki_root = args.wiki_root.resolve()
    out = args.out.resolve()
    experts_out = out / "experts"
    if experts_out.exists():
        if not args.force:
            raise SystemExit(f"Refusing to replace existing export without --force: {experts_out}")
        shutil.rmtree(experts_out)
    experts_out.mkdir(parents=True)

    manifests = [export_module(module, source_root, wiki_root, experts_out) for module in MODULES]
    registry = {
        "schema": 1,
        "library": "Lzheng source-limited training expert library",
        "experts": manifests,
    }
    write_json(out / "expert-registry.json", registry)
    print(f"Exported {len(manifests)} expert modules to {experts_out}")
    for item in manifests:
        print(f"- {item['id']}: {item['distilled_markdown_files']} markdown files, {item['knowledge_files']} knowledge files")


if __name__ == "__main__":
    main()
