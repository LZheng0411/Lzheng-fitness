#!/usr/bin/env python3
"""Scaffold and structurally validate a source-bound Douyin distillation report."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

HEADINGS = (
    "问题与来源", "作者核心观点", "完整方法", "时间段证据",
    "适用前提与边界", "不确定与分歧", "Agent 分析与应用",
)
TIME = re.compile(r"\[(\d{2,}):(\d{2})\.(\d{3})[–-](\d{2,}):(\d{2})\.(\d{3})\]")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source(packet: Path) -> tuple[dict, dict]:
    manifest = json.loads((packet / "manifest.json").read_text(encoding="utf-8"))
    transcript_path = packet / "transcript.json"
    transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
    if not (packet / "SOURCE_PACKET.md").is_file():
        raise ValueError("SOURCE_PACKET.md missing")
    if manifest.get("transcript_sha256") != digest(transcript_path):
        raise ValueError("Source packet transcript fingerprint mismatch")
    identity = manifest.get("source", {}).get("source_id")
    if not identity or identity != transcript.get("source_id"):
        raise ValueError("Source packet identity mismatch")
    segments = transcript.get("segments")
    if not isinstance(segments, list) or not segments:
        raise ValueError("No timestamped transcript segments")
    previous = 0.0
    for row in segments:
        start, end = row.get("start"), row.get("end")
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)) or not math.isfinite(start) or not math.isfinite(end) or start < previous or end <= start or not str(row.get("text", "")).strip():
            raise ValueError("Invalid transcript segment")
        previous = start
    return manifest, transcript


def stamp(seconds: float) -> str:
    millis = round(seconds * 1000)
    return f"{millis // 60000:02d}:{millis // 1000 % 60:02d}.{millis % 1000:03d}"


def init(packet: Path, out: Path) -> None:
    manifest, transcript = source(packet)
    if out.exists():
        raise ValueError("Report already exists; choose a new path")
    first = transcript["segments"][0]
    original = manifest["source"].get("original_url", "")
    rows = ["# 抖音视频蒸馏报告", "", f"source_packet_sha256: {digest(packet / 'SOURCE_PACKET.md')}",
            f"transcript_sha256: {digest(packet / 'transcript.json')}", "",
            f"来源：{original}", f"问题：{manifest.get('question', '')}", ""]
    for heading in HEADINGS:
        rows.extend((f"## {heading}", "", "[待填写]", ""))
    rows[rows.index("## 时间段证据") + 2] = f"[待填写] [{stamp(first['start'])}–{stamp(first['end'])}]"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(rows), encoding="utf-8")
    print(out)


def seconds(minutes: str, sec: str, ms: str) -> float:
    if int(sec) >= 60:
        raise ValueError("Invalid timestamp seconds")
    return int(minutes) * 60 + int(sec) + int(ms) / 1000


def validate(packet: Path, report: Path) -> None:
    manifest, transcript = source(packet)
    body = report.read_text(encoding="utf-8")
    for label, path in (("source_packet_sha256", packet / "SOURCE_PACKET.md"),
                        ("transcript_sha256", packet / "transcript.json")):
        if not re.search(rf"(?m)^{label}: {digest(path)}$", body):
            raise ValueError(f"{label} missing or stale")
    original_url = manifest["source"].get("original_url")
    if not original_url or original_url not in body:
        raise ValueError("Original source URL missing")
    sections = re.findall(r"(?ms)^## (.+?)\n(.*?)(?=^## |\Z)", body)
    if [name.strip() for name, _ in sections] != list(HEADINGS):
        raise ValueError("Required report headings missing or reordered")
    for name, content in sections:
        if len(content.strip()) < 12 or "[待填写]" in content:
            raise ValueError(f"Empty or unfinished section: {name}")
    evidence = dict(sections)["时间段证据"]
    matches = list(TIME.finditer(evidence))
    if not matches:
        raise ValueError("No time range in evidence section")
    for match in matches:
        start = seconds(*match.groups()[:3])
        end = seconds(*match.groups()[3:])
        if end <= start or not any(start >= row["start"] - .1 and start <= row["end"] + .1 for row in transcript["segments"]) or not any(end >= row["start"] - .1 and end <= row["end"] + .1 for row in transcript["segments"]):
            raise ValueError("Evidence time range is outside transcript segments")
    print(json.dumps({"status": "structure_valid", "source_id": manifest["source"]["source_id"],
                      "time_ranges": len(matches), "fact_review": "agent_required"}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "validate"))
    parser.add_argument("--packet-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.command == "init":
        if not args.out:
            parser.error("init requires --out")
        init(args.packet_dir, args.out)
    else:
        if not args.report:
            parser.error("validate requires --report")
        validate(args.packet_dir, args.report)


if __name__ == "__main__":
    main()
