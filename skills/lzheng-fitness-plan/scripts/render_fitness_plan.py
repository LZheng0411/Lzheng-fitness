#!/usr/bin/env python3
"""Render a standalone mobile-friendly fitness plan HTML from plan_contract JSON."""

from __future__ import annotations

import argparse
import base64
import html
import json
import mimetypes
import sys
from pathlib import Path
from typing import Any

from validate_plan import load_plan, validate_plan


def esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def data_uri(path: Path | None) -> str:
    if path is None or not path.is_file():
        return ""
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def default_header_image() -> Path:
    return Path(__file__).resolve().parents[1] / "assets" / "header-lineart.png"


def pills(values: list[Any], empty: str = "无") -> str:
    if not values:
        return f'<span class="muted">{esc(empty)}</span>'
    return "".join(f'<span class="pill">{esc(item)}</span>' for item in values)


def render_exercise(exercise: dict[str, Any]) -> str:
    prescription = exercise.get("prescription", {})
    alternatives = exercise.get("alternatives", [])
    checks = exercise.get("technique_checks", [])
    details = ""
    if alternatives or checks:
        details = f"""
        <details>
          <summary>替代与执行检查</summary>
          <div class="detail-grid">
            <div><h5>同目的替代</h5>{pills(alternatives)}</div>
            <div><h5>本次检查</h5><ul>{''.join(f'<li>{esc(item)}</li>' for item in checks) or '<li>按已确认动作标准执行</li>'}</ul></div>
          </div>
        </details>"""
    load = exercise.get("load", {})
    load_status = load.get("status")
    if load_status == "verified":
        load_html = f'<div class="load-card verified"><span>本次工作重量</span><strong>{esc(load.get("working_weight"))}{esc(load.get("unit"))}</strong><p>依据：{esc(load.get("source"))}</p><p>下次：{esc(load.get("next_rule"))}</p></div>'
    elif load_status == "calibration_required":
        load_html = f'<div class="load-card calibrate"><span>本次先校准重量</span><strong>按引导确定工作重量</strong><p>{esc(load.get("starting_instruction"))}</p><p>判断：{esc(load.get("decision_rule"))}</p></div>'
    else:
        load_html = f'<div class="load-card neutral"><span>本次渐进指标</span><strong>{esc(load.get("progression_metric", "按动作质量与目标次数推进"))}</strong></div>'
    return f"""
    <article class="exercise-card priority-{esc(exercise.get('priority'))}">
      <div class="exercise-head">
        <div><span class="eyebrow">{esc(exercise.get('pattern'))} · {esc(exercise.get('modality'))}</span><h4>{esc(exercise.get('name'))}</h4></div>
        <span class="priority">{esc(exercise.get('priority'))}</span>
      </div>
      <div class="dose-grid">
        <div><b>{esc(prescription.get('sets'))} × {esc(prescription.get('reps'))}</b><small>组数 × 次数</small></div>
        <div><b>{esc(prescription.get('intensity'))}</b><small>强度</small></div>
        <div><b>{esc(prescription.get('rest'))}</b><small>休息</small></div>
        <div><b>{esc(exercise.get('equipment'))}</b><small>器械</small></div>
      </div>
      {load_html}
      <p>{esc(exercise.get('purpose'))}</p>
      <p class="reason"><strong>为什么选：</strong>{esc(exercise.get('selection_reason'))}</p>
      {details}
    </article>"""


def render_day(day: dict[str, Any]) -> str:
    exercises = day.get("exercises", [])
    warmup = day.get("warmup", [])
    warmup_html = ""
    if warmup:
        warmup_html = '<div class="warmup"><h4>专项热身</h4><ol>' + "".join(f"<li>{esc(item)}</li>" for item in warmup) + "</ol></div>"
    ex_by_id = {item.get("id"): item for item in exercises}
    panels = [f'<div class="variant-panel active" data-variant="standard">{"".join(render_exercise(item) for item in exercises)}</div>']
    buttons = ['<button type="button" class="variant-button active" data-variant-button="standard">标准版</button>']
    for key, label in (("minutes_30", "30 分钟"), ("minutes_20", "20 分钟"), ("minutes_10", "10 分钟")):
        version = day.get("minimum_versions", {}).get(key, {})
        selected = [ex_by_id[item] for item in version.get("exercise_ids", []) if item in ex_by_id]
        buttons.append(f'<button type="button" class="variant-button" data-variant-button="{key}">{label}</button>')
        panels.append(
            f'<div class="variant-panel" data-variant="{key}"><p class="variant-note">{esc(version.get("note", ""))}</p>'
            + "".join(render_exercise(item) for item in selected)
            + "</div>"
        )
    return f"""
    <section id="{esc(day.get('id'))}" class="section workout-day">
      <div class="section-title"><div><span class="eyebrow">{esc(day.get('theme'))}</span><h2>{esc(day.get('title'))}</h2></div><span class="duration">{esc(day.get('duration'))}</span></div>
      <p>{esc(day.get('role', ''))}</p>
      {warmup_html}
      <div class="variant-buttons">{''.join(buttons)}</div>
      {''.join(panels)}
    </section>"""


def render_schedule(plan: dict[str, Any]) -> str:
    day_by_id = {item.get("id"): item for item in plan.get("training_days", [])}
    cards = []
    for item in plan.get("weekly_schedule", []):
        day = day_by_id.get(item.get("day_id"), {})
        href = f' href="#{esc(item.get("day_id"))}"' if item.get("day_id") else ""
        cards.append(
            f'<a class="schedule-card{" rest" if not item.get("day_id") else ""}"{href}>'
            f'<span>{esc(item.get("label", item.get("day_index", "")))}</span>'
            f'<strong>{esc(item.get("theme", "休息/轻活动"))}</strong>'
            f'<small>{esc(day.get("duration", item.get("role", "恢复")))}</small></a>'
        )
    return "".join(cards)


def render_sources(sources: list[dict[str, Any]]) -> str:
    rows = []
    for source in sources:
        location = str(source.get("local_path_or_url", ""))
        if location.startswith(("https://", "http://")):
            location_html = f'<a href="{esc(location)}" target="_blank" rel="noreferrer">打开来源</a>'
        else:
            location_html = f'<code>{esc(location)}</code>'
        rows.append(
            f"<tr><td>{esc(source.get('source_title'))}</td><td>{esc(source.get('chapter_or_section'))}</td>"
            f"<td>{esc(source.get('rule_used'))}</td><td>{location_html}</td></tr>"
        )
    return "".join(rows)


def render(plan: dict[str, Any], image_path: Path | None = None) -> str:
    meta = plan["plan_meta"]
    snapshot = plan["profile_snapshot"]
    safety = plan["safety_status"]
    goals = plan["goals"]
    next_day = next((item for item in plan.get("training_days", []) if item.get("id") == meta.get("next_training_day_id")), None)
    if next_day is None and plan.get("training_days"):
        next_day = plan["training_days"][0]
    image = data_uri(image_path or default_header_image())
    image_html = f'<img class="hero-art" src="{image}" alt="训练人物线稿">' if image else ""
    coverage_rows = "".join(
        f"<tr><td>{esc(item.get('pattern'))}</td><td>{esc(', '.join(map(str, item.get('days', []))))}</td>"
        f"<td>{esc(item.get('evidence'))}</td><td>{'合格' if item.get('adequate') else '待检查'}</td></tr>"
        for item in plan.get("movement_coverage", [])
    )
    movement_rows = "".join(
        f"<tr><td>{esc(item.get('movement'))}</td><td>{esc(item.get('stage'))}</td>"
        f"<td>{esc(item.get('evidence'))}</td><td>{esc(item.get('role'))}</td></tr>"
        for item in plan.get("movement_profile", [])
    )
    progression = "".join(
        f'<article class="rule-card"><h4>{esc(item.get("scope"))}</h4><p><strong>当：</strong>{esc(item.get("when"))}</p><p><strong>则：</strong>{esc(item.get("action"))}</p></article>'
        for item in plan.get("progression_rules", [])
    )
    reviews = "".join(
        f'<article class="rule-card"><h4>{esc(item.get("timing"))}</h4><p>{esc(item.get("collect"))}</p><p class="muted">{esc(item.get("decision"))}</p></article>'
        for item in plan.get("review_checkpoints", [])
    )
    minimum_cards = "".join(
        f'<article class="rule-card"><h4>{esc(item.get("name", item.get("version", "短版")))}</h4><p>{esc(item.get("rule", item.get("description", "")))}</p></article>'
        for item in plan.get("minimum_versions", [])
    )
    interruption_cards = "".join(
        f'<article class="rule-card"><h4>{esc(key.replace("_", " "))}</h4><p>{esc(value)}</p></article>'
        for key, value in plan.get("short_interruption_rules", {}).items()
    )
    cycles = plan.get("cycle_links", [])
    active_cycles = [item for item in cycles if item.get("status") == "active"]
    cycle_section = ""
    if active_cycles:
        cycle_section = '<section id="cycles" class="section"><div class="section-title"><h2>专项力量周期</h2></div>' + "".join(
            f'<article class="rule-card"><h4>{esc(item.get("movement"))}</h4><p>{esc(item.get("summary", item.get("source_plan_id", "")))}</p></article>'
            for item in active_cycles
        ) + "</section>"
    assumptions = "".join(f"<li>{esc(item)}</li>" for item in plan.get("assumptions", [])) or "<li>无未标注假设</li>"
    stop_signals = "".join(f"<li>{esc(item)}</li>" for item in safety.get("stop_signals", [])) or "<li>按已确认安全边界执行</li>"
    days_html = '<div id="training" class="anchor-target"></div>' + "".join(render_day(day) for day in plan.get("training_days", []))
    return f"""<!doctype html>
<html lang="zh-CN" data-ui-contract="lzheng-plan-v2" data-plan-id="{esc(meta.get('plan_id'))}" data-snapshot-id="{esc(snapshot.get('snapshot_id'))}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(meta.get('title'))}</title>
<style>
:root{{--ink:#17221e;--muted:#66736d;--line:#dfe5e1;--soft:#f4f6f4;--green:#174f3d;--green2:#e7f0ec;--warn:#9a5b1f;--warnbg:#fff5e8;--white:#fff;--nav-h:52px}}
*{{box-sizing:border-box}}html,body{{max-width:100%;overflow-x:hidden}}html{{scroll-behavior:smooth}}body{{margin:0;padding-top:var(--nav-h);background:#eef1ef;color:var(--ink);font:15px/1.65 system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif}}
a{{color:inherit}}.page{{width:100%;max-width:1160px;margin:auto;background:var(--white);min-height:100vh;box-shadow:0 0 40px #173d2d14}}.wrap{{min-width:0;padding:0 44px}}
.hero{{position:relative;min-height:330px;padding:58px 44px 38px;overflow:hidden;border-bottom:1px solid var(--line)}}.hero-copy{{min-width:0;max-width:700px;position:relative;z-index:2}}.brand{{font-weight:750;letter-spacing:.08em;color:var(--green)}}
h1,h2,h3,h4,h5,p,strong{{overflow-wrap:anywhere;word-break:break-word}}h1{{font-size:clamp(34px,5vw,66px);line-height:1.05;letter-spacing:-.04em;margin:22px 0 18px}}h2{{font-size:28px;line-height:1.2;margin:0}}h4{{font-size:18px;margin:0 0 8px}}h5{{margin:0 0 6px}}
.hero p{{font-size:18px;color:var(--muted);max-width:620px}}.hero-art{{position:absolute;right:24px;bottom:0;width:35%;max-height:315px;object-fit:contain;object-position:right bottom;opacity:.82}}
.meta{{display:flex;flex-wrap:wrap;gap:10px;margin-top:24px}}.pill,.meta span{{display:inline-flex;min-width:0;max-width:100%;padding:6px 10px;border:1px solid var(--line);border-radius:999px;background:var(--soft);font-size:13px;white-space:normal;overflow-wrap:anywhere}}
.sticky{{position:fixed;top:0;left:0;right:0;z-index:100;background:#fffffff2;border-bottom:1px solid var(--line);backdrop-filter:blur(10px);overflow:auto;white-space:nowrap;padding:14px max(20px,calc((100vw - 1080px)/2)) 12px}}.sticky a{{text-decoration:none;margin-right:26px;font-size:13px;color:var(--muted)}}.sticky a.active{{color:var(--green);font-weight:750;border-bottom:2px solid var(--green);padding-bottom:10px}}
.section{{padding:48px 0;border-bottom:1px solid var(--line);scroll-margin-top:calc(var(--nav-h) + 18px)}}.anchor-target{{scroll-margin-top:calc(var(--nav-h) + 18px)}}.section-title{{display:flex;align-items:flex-end;justify-content:space-between;gap:20px;margin-bottom:18px}}.eyebrow{{display:block;color:var(--green);font-size:12px;font-weight:750;letter-spacing:.08em;text-transform:uppercase}}.duration{{font-weight:700;color:var(--green)}}
.quick{{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(0,.75fr);gap:18px}}.quick>*{{min-width:0}}.quick-card,.alert{{padding:24px;border:1px solid var(--line);background:var(--soft);border-radius:16px}}.alert{{background:var(--warnbg);color:#623b18}}.quick-card strong.big{{display:block;font-size:24px}}
.schedule{{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:8px}}.schedule-card{{min-width:0;padding:14px 10px;border:1px solid var(--line);border-radius:12px;text-decoration:none;background:#fff}}.schedule-card span,.schedule-card small{{display:block;color:var(--muted);font-size:12px}}.schedule-card strong{{display:block;margin:6px 0}}.schedule-card.rest{{background:var(--soft)}}
.variant-buttons{{display:flex;gap:8px;flex-wrap:wrap;margin:20px 0}}.variant-button{{border:1px solid var(--line);background:#fff;color:var(--ink);padding:9px 14px;border-radius:999px;cursor:pointer}}.variant-button.active{{background:var(--green);border-color:var(--green);color:#fff}}.variant-panel{{display:none}}.variant-panel.active{{display:block}}.variant-note{{padding:12px 16px;border-left:3px solid var(--green);background:var(--green2)}}
.warmup{{margin:18px 0;padding:18px 20px;border:1px solid var(--line);border-radius:14px;background:var(--green2)}}.warmup ol{{margin:8px 0 0;padding-left:20px}}.load-card{{margin:14px 0;padding:14px 16px;border-radius:12px;border:1px solid var(--line)}}.load-card span,.load-card p{{display:block;margin:0;color:var(--muted);font-size:12px}}.load-card strong{{display:block;font-size:18px;margin:3px 0 8px}}.load-card.verified{{background:var(--green2);border-color:#bdd1c6}}.load-card.calibrate{{background:var(--warnbg);border-color:#ebd5b6}}.load-card.neutral{{background:var(--soft)}}
.exercise-card{{min-width:0;padding:20px 0;border-top:1px solid var(--line)}}.exercise-head{{display:flex;justify-content:space-between;gap:16px;min-width:0}}.priority{{font-size:12px;color:var(--muted)}}.dose-grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:14px 0}}.dose-grid>div{{min-width:0;padding:12px;background:var(--soft);border-radius:10px}}.dose-grid b,.dose-grid small{{display:block}}.dose-grid small{{color:var(--muted);font-size:11px;margin-top:4px}}.reason{{color:var(--muted)}}details{{border-top:1px dashed var(--line);padding-top:10px}}summary{{cursor:pointer;color:var(--green);font-weight:700}}.detail-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;padding-top:12px}}
.table-wrap{{overflow:auto}}table{{width:100%;border-collapse:collapse;min-width:680px}}th,td{{padding:12px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}}th{{font-size:12px;color:var(--muted)}}code{{font-size:12px;word-break:break-all}}
.rule-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}}.rule-card{{min-width:0;padding:18px;border:1px solid var(--line);border-radius:12px}}.muted{{color:var(--muted)}}.source-note{{font-size:12px;color:var(--muted)}}ul{{padding-left:20px}}
@media(max-width:820px){{.wrap{{padding:0 20px}}.hero{{padding:40px 20px 28px;min-height:auto}}.hero-art{{display:none}}.sticky{{padding:14px 20px 12px}}.sticky a{{margin-right:20px}}.quick,.detail-grid,.rule-grid{{grid-template-columns:1fr}}.schedule{{display:flex;overflow:auto}}.schedule-card{{min-width:140px}}.dose-grid{{grid-template-columns:1fr 1fr}}.section{{padding:34px 0}}.meta .snapshot-pill{{flex-basis:100%}}}}
@media(max-width:480px){{.dose-grid{{grid-template-columns:1fr}}h2{{font-size:24px}}}}
@media print{{body{{background:#fff}}.page{{box-shadow:none}}.sticky,.variant-buttons,.hero-art{{display:none!important}}.variant-panel{{display:block!important}}.section{{break-inside:avoid}}a{{text-decoration:none}}}}
</style>
</head>
<body><main class="page">
<header class="hero">{image_html}<div class="hero-copy"><div class="brand">LZHENG FITNESS PLAN</div><h1>{esc(meta.get('title'))}</h1><p>{esc(meta.get('subtitle', meta.get('phase_goal')))}</p><div class="meta"><span>{esc(snapshot.get('overall_stage'))}</span><span>{esc(meta.get('frequency'))}</span><span>{esc(meta.get('weeks'))} 周</span><span class="snapshot-pill">状态快照 {esc(snapshot.get('generated_at'))}</span></div></div></header>
<nav class="sticky" aria-label="计划主导航"><a href="#start">概览</a><a href="#week">本周</a><a href="#training">训练日</a><a href="#progression">进阶</a><a href="#fallback">规则</a></nav>
<div class="wrap">
<section id="start" class="section"><div class="section-title"><div><span class="eyebrow">立即执行</span><h2>下一次训练</h2></div></div><div class="quick"><div class="quick-card"><strong class="big">{esc(next_day.get('title') if next_day else '待安排')}</strong><p>{esc(next_day.get('theme') if next_day else '')}</p><p>{esc(next_day.get('duration') if next_day else '')}</p><a href="#{esc(next_day.get('id') if next_day else 'week')}">打开训练日 →</a></div><div class="alert"><strong>阶段目标</strong><p>{esc(meta.get('phase_goal'))}</p><strong>安全状态：{esc(safety.get('status'))}</strong></div></div></section>
<section id="week" class="section"><div class="section-title"><div><span class="eyebrow">Weekly plan</span><h2>本周安排</h2></div></div><div class="schedule">{render_schedule(plan)}</div></section>
<section id="stages" class="section"><div class="section-title"><h2>动作分层与当前职责</h2></div><div class="table-wrap"><table><thead><tr><th>动作/模式</th><th>阶段</th><th>判断依据</th><th>本阶段职责</th></tr></thead><tbody>{movement_rows}</tbody></table></div></section>
{days_html}
<section id="coverage" class="section"><div class="section-title"><h2>动作模式与肌群覆盖</h2></div><div class="table-wrap"><table><thead><tr><th>模式/肌群</th><th>训练日</th><th>依据</th><th>结论</th></tr></thead><tbody>{coverage_rows}</tbody></table></div></section>
<section id="progression" class="section"><div class="section-title"><h2>渐进与复盘</h2></div><div class="rule-grid">{progression}{reviews}</div></section>
<section id="fallback" class="section"><div class="section-title"><h2>时间不足、状态差与漏练接回</h2></div><div class="rule-grid">{minimum_cards}{interruption_cards}</div></section>
{cycle_section}
<section id="sources" class="section"><div class="section-title"><h2>本计划参考依据</h2></div><div class="table-wrap"><table><thead><tr><th>来源</th><th>章节/范围</th><th>用于什么判断</th><th>位置</th></tr></thead><tbody>{render_sources(plan.get('knowledge_sources', []))}</tbody></table></div><p class="source-note">这里只列出本次实际读取和使用的来源。</p></section>
<section class="section"><div class="section-title"><h2>假设与停止边界</h2></div><div class="quick"><div class="quick-card"><h4>假设/待确认</h4><ul>{assumptions}</ul></div><div class="alert"><h4>出现这些情况停止普通推进</h4><ul>{stop_signals}</ul></div></div></section>
</div></main>
<script>
document.querySelectorAll('.workout-day').forEach(function(day){{
  day.querySelectorAll('[data-variant-button]').forEach(function(button){{
    button.addEventListener('click', function(){{
      var key=button.getAttribute('data-variant-button');
      day.querySelectorAll('[data-variant-button]').forEach(function(x){{x.classList.toggle('active',x===button)}});
      day.querySelectorAll('[data-variant]').forEach(function(x){{x.classList.toggle('active',x.getAttribute('data-variant')===key)}});
    }});
  }});
}});
var navLinks=[].slice.call(document.querySelectorAll('.sticky a'));
var navTargets=navLinks.map(function(link){{return document.querySelector(link.getAttribute('href'));}}).filter(Boolean);
if('IntersectionObserver' in window){{
  var navObserver=new IntersectionObserver(function(entries){{
    entries.forEach(function(entry){{
      if(entry.isIntersecting){{
        navLinks.forEach(function(link){{link.classList.toggle('active',link.getAttribute('href')==='#'+entry.target.id);}});
      }}
    }});
  }},{{rootMargin:'-25% 0px -65% 0px'}});
  navTargets.forEach(function(target){{navObserver.observe(target);}});
}}
</script>
</body></html>"""


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
