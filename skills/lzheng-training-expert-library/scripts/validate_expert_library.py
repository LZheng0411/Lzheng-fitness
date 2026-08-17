#!/usr/bin/env python3
"""Validate the portable expert library's structure, privacy, links, and routes."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REFERENCES = ROOT / "references"
REGISTRY = REFERENCES / "expert-registry.json"
EXPECTED = {
    "alan-aragon-flexible-dieting",
    "brad-schoenfeld-hypertrophy",
    "brukner-khan-return-to-sport",
    "dan-john-intervention-easy-strength",
    "eric-helms-training-pyramid",
    "greg-nuckols-strength-periodization",
}
PRIVATE = (
    re.compile(r"\b[A-Za-z]:\\"),
    re.compile(r"E:/", re.IGNORECASE),
    re.compile("|".join(("个人" + "健身知识库", "lz" + "政系统健身", "李" + "政"))),
    re.compile(r"obsidian://|file://", re.IGNORECASE),
)
MD_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def fail(message: str) -> None:
    raise SystemExit(message)


def validate_links(path: Path, text: str) -> None:
    if "[[" in text or "]]" in text:
        fail(f"Unconverted Obsidian link: {path.relative_to(ROOT)}")
    for raw in MD_LINK.findall(text):
        target = raw.strip().strip("<>").split("#", 1)[0]
        if not target or target.startswith(("https://", "http://", "mailto:")):
            continue
        if not (path.parent / target).resolve().exists():
            fail(f"Broken local link in {path.relative_to(ROOT)}: {target}")


def validate_module(item: dict) -> None:
    module = REFERENCES / "experts" / item["id"]
    manifest_path = module / "module.json"
    if not module.is_dir() or not manifest_path.is_file():
        fail(f"Missing expert module: {item['id']}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest != item:
        fail(f"Registry and module manifest differ: {item['id']}")
    for required in (manifest["entry"], manifest["source_boundary"]):
        if not (module / required).is_file():
            fail(f"Missing required expert file: {item['id']}/{required}")
    if manifest["raw_sources_included"] is not False:
        fail(f"Raw source flag must be false: {item['id']}")
    if manifest["knowledge_files"] < 4:
        fail(f"Expert module has too few knowledge files: {item['id']}")
    actual_markdown = len(list(module.rglob("*.md")))
    if actual_markdown != manifest["distilled_markdown_files"]:
        fail(f"Markdown count mismatch: {item['id']}")
    for path in module.rglob("*"):
        if path.is_dir():
            continue
        if path.suffix.lower() in {".pdf", ".epub", ".docx", ".mobi", ".html"}:
            fail(f"Raw or converted source artifact is not allowed: {path.relative_to(ROOT)}")
        if path.suffix.lower() not in {".md", ".json"}:
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in PRIVATE:
            if pattern.search(text):
                fail(f"Private path or identity found: {path.relative_to(ROOT)}")
        if path.suffix.lower() == ".md":
            validate_links(path, text)


def validate_routes() -> None:
    selector = ROOT / "scripts" / "select_experts.py"
    cases = {
        "nutrition": ["alan-aragon-flexible-dieting"],
        "hypertrophy_programming": ["brad-schoenfeld-hypertrophy", "eric-helms-training-pyramid"],
        "strength_stall": ["greg-nuckols-strength-periodization", "eric-helms-training-pyramid"],
        "medically_cleared_return": ["brukner-khan-return-to-sport"],
        "unassessed_pain": [],
    }
    for variable, expected in cases.items():
        completed = subprocess.run(
            [sys.executable, str(selector), variable],
            text=True,
            encoding="utf-8",
            capture_output=True,
        )
        if completed.returncode:
            fail(f"Selector failed for {variable}: {completed.stderr}")
        result = json.loads(completed.stdout)
        if result["experts"] != expected:
            fail(f"Unexpected route for {variable}: {result['experts']}")
        if variable == "unassessed_pain" and not result["blocked"]:
            fail("Unassessed pain must route to safety triage")


def main() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    ids = {item["id"] for item in registry.get("experts", [])}
    if ids != EXPECTED or len(registry.get("experts", [])) != len(EXPECTED):
        fail(f"Expert registry mismatch: {sorted(ids)}")
    for item in registry["experts"]:
        validate_module(item)
    validate_routes()
    print("OK: six portable expert modules, privacy boundaries, links, and routes validated.")


if __name__ == "__main__":
    main()
