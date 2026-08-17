#!/usr/bin/env python3
"""Render a standalone fixed-template fitness plan HTML from plan_contract JSON."""

from __future__ import annotations

import argparse
import base64
import html
import mimetypes
import re
import sys
from pathlib import Path
from typing import Any

from validate_plan import load_plan, validate_plan


PATTERN_ORDER = ("蹲", "髋铰链", "推", "拉", "单腿", "核心")
MUSCLE_ORDER = (
    "胸肌",
    "背阔肌",
    "上背/中背",
    "下背/竖脊肌",
    "肩前束",
    "肩中束",
    "肩后束",
    "肱二头肌",
    "肱三头肌",
    "股四头肌",
    "腘绳肌",
    "臀部",
    "小腿",
    "核心",
)


def esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def fmt_number(value: float | int) -> str:
    numeric = float(value)
    return str(int(numeric)) if numeric.is_integer() else f"{numeric:.1f}".rstrip("0").rstrip(".")


def data_uri(path: Path | None) -> str:
    if path is None or not path.is_file():
        return ""
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def default_header_image() -> Path:
    return Path(__file__).resolve().parents[1] / "assets" / "header-lineart.png"


def default_template() -> Path:
    return Path(__file__).resolve().parents[1] / "assets" / "fitness-plan-template.html"


def fill_template(values: dict[str, str]) -> str:
    template_path = default_template()
    if not template_path.is_file():
        raise ValueError(f"fixed HTML template not found: {template_path}")
    output = template_path.read_text(encoding="utf-8")
    for key, value in values.items():
        token = f"__{key}__"
        if token not in output:
            raise ValueError(f"fixed HTML template missing token: {token}")
        output = output.replace(token, value)
    unresolved = sorted(set(re.findall(r"__[A-Z0-9_]+__", output)))
    if unresolved:
        raise ValueError("fixed HTML template has unresolved tokens: " + ", ".join(unresolved))
    return output


def pills(values: list[Any], empty: str = "无") -> str:
    if not values:
        return f'<span class="muted">{esc(empty)}</span>'
    return '<span class="pill-row">' + "".join(f'<span class="pill">{esc(item)}</span>' for item in values) + "</span>"


def rir_summary(intensity: Any) -> str:
    text = str(intensity or "")
    match = re.search(r"RPE\s*(\d+(?:\.\d+)?)(?:\s*[—–-]\s*(\d+(?:\.\d+)?))?", text, flags=re.I)
    if not match:
        return text
    first = max(0.0, 10.0 - float(match.group(1)))
    second = max(0.0, 10.0 - float(match.group(2))) if match.group(2) else first
    low, high = sorted((first, second))
    if low == high:
        return f"留约 {fmt_number(low)} 次余力"
    return f"留约 {fmt_number(low)}—{fmt_number(high)} 次余力"


def humanize_rpe_text(value: Any) -> str:
    text = str(value or "").replace("RPE偏差", "余力判断偏差")

    def replace_not_above(match: re.Match[str]) -> str:
        rir = max(0.0, 10.0 - float(match.group(1)))
        return f"至少保留约 {fmt_number(rir)} 次余力"

    text = re.sub(r"不超过\s*RPE\s*(\d+(?:\.\d+)?)", replace_not_above, text, flags=re.I)

    def replace_rpe(match: re.Match[str]) -> str:
        rir = max(0.0, 10.0 - float(match.group(1)))
        return f"约留 {fmt_number(rir)} 次余力"

    return re.sub(r"RPE\s*(\d+(?:\.\d+)?)", replace_rpe, text, flags=re.I)


def load_short(load: dict[str, Any]) -> str:
    status = load.get("status")
    if status == "verified":
        return f"{load.get('working_weight', '')}{load.get('unit', '')}"
    if status == "calibration_required":
        return "现场校准"
    return str(load.get("progression_metric", "按目标推进"))


def render_exercise_note(exercise: dict[str, Any]) -> str:
    load = exercise.get("load", {})
    if load.get("status") == "verified":
        load_detail = (
            f'<p><strong>重量：</strong>{esc(load_short(load))}</p>'
            f'<p><strong>依据：</strong>{esc(load.get("source"))}</p>'
            f'<p><strong>下次：</strong>{esc(load.get("next_rule"))}</p>'
        )
    elif load.get("status") == "calibration_required":
        load_detail = (
            f'<p><strong>起点：</strong>{esc(load.get("starting_instruction"))}</p>'
            f'<p><strong>确定重量：</strong>{esc(load.get("decision_rule"))}</p>'
        )
    else:
        load_detail = f'<p><strong>推进指标：</strong>{esc(load.get("progression_metric"))}</p>'
    checks = "".join(f"<li>{esc(item)}</li>" for item in exercise.get("technique_checks", []))
    return (
        '<div class="exercise-note">'
        f'<h4>{esc(exercise.get("name"))}</h4>{load_detail}'
        f'<p><strong>为什么选：</strong>{esc(exercise.get("selection_reason"))}</p>'
        f'<div class="note-columns"><div><strong>替代动作</strong>{pills(exercise.get("alternatives", []))}</div>'
        f'<div><strong>动作检查</strong><ul>{checks or "<li>按已确认动作标准执行</li>"}</ul></div></div></div>'
    )


def render_day_card(day: dict[str, Any]) -> str:
    exercises = day.get("exercises", [])
    rows = []
    for exercise in exercises:
        prescription = exercise.get("prescription", {})
        rows.append(
            f'<tr><td><strong>{esc(exercise.get("name"))}</strong><small>{esc(exercise.get("equipment"))}</small></td>'
            f'<td>{esc(prescription.get("sets"))} × {esc(prescription.get("reps"))}</td>'
            f'<td><strong>{esc(load_short(exercise.get("load", {})))}</strong>'
            f'<small>{esc(rir_summary(prescription.get("intensity")))} · 休息 {esc(prescription.get("rest"))}</small></td></tr>'
        )
    versions = []
    by_id = {item.get("id"): item for item in exercises}
    for key, label in (("minutes_30", "30 分钟"), ("minutes_20", "20 分钟"), ("minutes_10", "10 分钟")):
        version = day.get("minimum_versions", {}).get(key, {})
        names = [by_id[item].get("name") for item in version.get("exercise_ids", []) if item in by_id]
        versions.append(
            f'<div class="short-row"><b>{label}</b><span>{esc("、".join(map(str, names)))}</span><small>{esc(version.get("note"))}</small></div>'
        )
    warmup = day.get("warmup", [])
    warmup_html = ""
    if warmup:
        warmup_html = '<div class="warmup-line"><strong>热身</strong><span>' + esc(" → ".join(map(str, warmup))) + "</span></div>"
    return (
        f'<article id="{esc(day.get("id"))}" class="training-day-card">'
        f'<header><div><span class="day-label">{esc(day.get("theme"))}</span><h3>{esc(day.get("title"))}</h3></div>'
        f'<span class="day-time">{esc(day.get("duration"))}</span></header>{warmup_html}'
        '<div class="day-table"><table><thead><tr><th>动作</th><th>组次</th><th>目标</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
        f'<details class="day-extra"><summary>重量与动作说明</summary><div class="note-list">{"".join(render_exercise_note(item) for item in exercises)}</div></details>'
        f'<details class="day-extra"><summary>时间不足版本</summary><div class="short-list">{"".join(versions)}</div></details>'
        "</article>"
    )


def render_schedule(plan: dict[str, Any]) -> str:
    day_by_id = {item.get("id"): item for item in plan.get("training_days", [])}
    cards = []
    for item in plan.get("weekly_schedule", []):
        day = day_by_id.get(item.get("day_id"), {})
        href = f' href="#{esc(item.get("day_id"))}"' if item.get("day_id") else ""
        kind = item.get("kind") or ("recovery" if not item.get("day_id") else "required")
        if kind not in {"required", "optional", "recovery"}:
            kind = "required"
        kind_label = {"required": "必练", "optional": "可选", "recovery": "恢复"}[kind]
        focus = day.get("theme") or item.get("role") or "不安排正式训练"
        cards.append(
            f'<a class="schedule-card {kind}" data-kind-label="{kind_label}"{href}>'
            f'<span>{esc(item.get("label", item.get("day_index", "")))}</span>'
            f'<strong>{esc(item.get("theme", "休息/轻活动"))}</strong>'
            f'<span class="schedule-focus">{esc(focus)}</span>'
            f'<small>{esc(day.get("duration", item.get("role", "恢复")))}</small></a>'
        )
    return "".join(cards)


def derive_coverage(plan: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    schedule_counts: dict[str, int] = {}
    for item in plan.get("weekly_schedule", []):
        day_id = item.get("day_id") if isinstance(item, dict) else None
        if day_id:
            schedule_counts[day_id] = schedule_counts.get(day_id, 0) + 1
    patterns = {name: {"sets": 0, "days": [], "exercises": []} for name in PATTERN_ORDER}
    muscles = {name: {"direct": 0.0, "indirect": 0.0, "sources": []} for name in MUSCLE_ORDER}
    for day in plan.get("training_days", []):
        occurrences = schedule_counts.get(day.get("id"), 0)
        if occurrences < 1:
            continue
        day_title = str(day.get("title", ""))
        for exercise in day.get("exercises", []):
            prescription = exercise.get("prescription", {})
            weekly_sets = int(prescription.get("set_count", 0)) * occurrences
            name = str(exercise.get("name", ""))
            pattern = patterns[exercise.get("pattern_group")]
            pattern["sets"] += weekly_sets
            if day_title not in pattern["days"]:
                pattern["days"].append(day_title)
            if name not in pattern["exercises"]:
                pattern["exercises"].append(name)
            for contribution in exercise.get("muscle_contributions", []):
                muscle = muscles[contribution.get("muscle_group")]
                coefficient = float(contribution.get("coefficient"))
                effective = weekly_sets * coefficient
                if coefficient == 1.0:
                    muscle["direct"] += effective
                else:
                    muscle["indirect"] += effective
                muscle["sources"].append(
                    f"{name} {fmt_number(weekly_sets)}×{fmt_number(coefficient)}={fmt_number(effective)}"
                )
    return patterns, muscles


def render_coverage(plan: dict[str, Any]) -> tuple[str, str]:
    patterns, muscles = derive_coverage(plan)
    pattern_rows = "".join(
        f'<tr><td>{esc(name)}</td><td>{fmt_number(data["sets"])}</td>'
        f'<td>{esc("、".join(data["days"]) or "—")}</td><td>{esc("、".join(data["exercises"]) or "—")}</td></tr>'
        for name, data in patterns.items() if data["sets"] > 0
    )
    muscle_rows = "".join(
        f'<tr><td>{esc(name)}</td>'
        f'<td>{fmt_number(data["direct"])}</td><td>{fmt_number(data["indirect"])}</td>'
        f'<td><strong>{fmt_number(data["direct"] + data["indirect"])}</strong></td>'
        f'<td>{esc("；".join(data["sources"]) or "—")}</td></tr>'
        for name, data in muscles.items() if data["direct"] + data["indirect"] > 0
    )
    return pattern_rows, muscle_rows


def render(plan: dict[str, Any], image_path: Path | None = None) -> str:
    meta = plan["plan_meta"]
    snapshot = plan["profile_snapshot"]
    image = data_uri(image_path or default_header_image())
    image_html = f'<img class="hero-art" src="{image}" alt="训练人物线稿">' if image else ""
    goal_label = {
        "strength": "力量",
        "hypertrophy": "增肌",
        "fat_loss": "减脂",
        "general_fitness": "综合健身",
    }.get(meta.get("goal_mode"), "待确认")
    progression_rows = "".join(
        f"<tr><td>动作推进</td><td>{esc(item.get('scope'))}</td><td>{esc(humanize_rpe_text(item.get('when')))}</td><td>{esc(item.get('action'))}</td></tr>"
        for item in plan.get("progression_rules", [])
    )
    checkpoints = plan.get("review_checkpoints", [])
    review_rows = "".join(
        f"<tr><td>{'周期复盘' if index == len(checkpoints) - 1 else '阶段复盘'}</td>"
        f"<td>{esc(item.get('timing'))}</td>"
        f"<td>{esc('AI 主动向用户确认：' + humanize_rpe_text(item.get('collect')))}</td>"
        f"<td>{esc('确认后，' + str(item.get('decision') or '') + ('；生成下一阶段计划' if index == len(checkpoints) - 1 else ''))}</td></tr>"
        for index, item in enumerate(checkpoints)
    )
    active_cycles = [item for item in plan.get("cycle_links", []) if item.get("status") == "active"]
    cycle_section = ""
    if active_cycles:
        cycle_rows = "".join(
            f'<tr><td>{esc(item.get("movement"))}</td><td>{esc(item.get("summary", item.get("source_plan_id", "")))}</td></tr>'
            for item in active_cycles
        )
        cycle_section = (
            '<div class="subsection"><h3>已启用的专项力量周期</h3><div class="table-wrap">'
            f'<table><thead><tr><th>动作</th><th>周期</th></tr></thead><tbody>{cycle_rows}</tbody></table></div></div>'
        )
    overview_html = (
        '<div class="section-title"><div><span class="eyebrow">Plan overview</span><h2>计划概览</h2></div></div>'
        '<div class="goal-statement"><div class="kicker">阶段目标</div>'
        f'<strong>{esc(meta.get("phase_goal"))}</strong></div><div class="metric-row">'
        f'<div class="metric"><b>{esc(meta.get("frequency"))}</b><small>训练频率</small></div>'
        f'<div class="metric"><b>{esc(meta.get("weeks"))} 周</b><small>周期长度</small></div>'
        f'<div class="metric"><b>{esc(snapshot.get("overall_stage"))}</b><small>当前阶段</small></div>'
        f'<div class="metric"><b>{esc(goal_label)}</b><small>目标类型</small></div></div>'
    )
    week_html = (
        '<div class="section-title"><div><span class="eyebrow">Weekly structure</span><h2>本周结构</h2></div></div>'
        f'<div class="schedule">{render_schedule(plan)}</div>'
    )
    training_html = (
        '<div class="section-title"><div><span class="eyebrow">Training days</span><h2>训练日安排</h2></div></div>'
        f'<div class="training-grid">{"".join(render_day_card(day) for day in plan.get("training_days", []))}</div>'
    )
    progression_html = (
        '<div class="section-title"><div><span class="eyebrow">Progression</span><h2>进阶与周期复盘</h2></div></div>'
        '<p class="section-lead">动作按实际表现推进；到达复盘节点时，AI 会先向用户确认完成率、余力、动作稳定性与恢复，再决定调整。周期末确认后，由 AI 生成下一阶段计划。</p>'
        '<div class="table-wrap"><table class="progress-table"><thead><tr><th>类型</th><th>适用范围 / 时机</th><th>判断依据</th><th>下一步</th></tr></thead>'
        f'<tbody>{progression_rows}{review_rows}</tbody></table></div>{cycle_section}'
    )
    pattern_rows, muscle_rows = render_coverage(plan)
    coverage_html = (
        '<div class="section-title"><div><span class="eyebrow">Coverage</span><h2>训练覆盖</h2></div></div>'
        '<div class="coverage-tabs" role="tablist"><button type="button" class="coverage-tab active" data-coverage-tab="patterns">动作模式</button>'
        '<button type="button" class="coverage-tab" data-coverage-tab="muscles">健美肌群</button></div>'
        '<div class="coverage-panel active" data-coverage-panel="patterns"><div class="table-wrap"><table class="coverage-table">'
        f'<thead><tr><th>模式</th><th>每周组数</th><th>训练日</th><th>动作</th></tr></thead><tbody>{pattern_rows}</tbody></table></div></div>'
        '<div class="coverage-panel" data-coverage-panel="muscles"><p class="coverage-note">直接组按 1.0 计；间接参与按 0.5 折算。合计是计划估算值。</p>'
        '<div class="table-wrap"><table class="coverage-table muscle-table"><thead><tr><th>肌群</th><th>直接组</th><th>间接折算</th><th>合计</th><th>全部来源</th></tr></thead>'
        f'<tbody>{muscle_rows}</tbody></table></div></div>'
    )
    meta_html = (
        f'<span>{esc(snapshot.get("overall_stage"))}</span><span>{esc(meta.get("frequency"))}</span>'
        f'<span>{esc(meta.get("weeks"))} 周</span><span class="snapshot-pill">状态快照 {esc(snapshot.get("generated_at"))}</span>'
    )
    return fill_template(
        {
            "PLAN_ID": esc(meta.get("plan_id")),
            "SNAPSHOT_ID": esc(snapshot.get("snapshot_id")),
            "DOCUMENT_TITLE": esc(meta.get("title")),
            "HERO_IMAGE_HTML": image_html,
            "PLAN_TITLE": esc(meta.get("title")),
            "PLAN_SUBTITLE": esc(meta.get("subtitle", meta.get("phase_goal"))),
            "PLAN_META": meta_html,
            "OVERVIEW_HTML": overview_html,
            "WEEK_HTML": week_html,
            "TRAINING_HTML": training_html,
            "PROGRESSION_HTML": progression_html,
            "COVERAGE_HTML": coverage_html,
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--header-image", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        print(f"ERROR: refusing to overwrite existing file: {args.output}", file=sys.stderr)
        return 2
    try:
        plan = load_plan(args.plan)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    errors, warnings = validate_plan(plan)
    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(plan, args.header_image), encoding="utf-8")
    print(f"OK: wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
