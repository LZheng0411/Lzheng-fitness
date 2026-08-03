#!/usr/bin/env python3
"""Render a standalone strength-cycle HTML plan from one JSON data source."""

from __future__ import annotations

import argparse
import base64
import html
import json
import math
import re
from pathlib import Path
from typing import Any


INK = "#1f2937"
GRAY = "#98a2ad"
MUTED = "#737373"
LIGHT = "#e5e5e5"
BODYWEIGHT = "#a3a3a1"


def text(value: Any) -> str:
    return html.escape(str(value), quote=True)


def number(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def require(data: dict[str, Any], key: str, context: str) -> Any:
    if key not in data or data[key] in (None, "", []):
        raise ValueError(f"{context} 缺少必填字段：{key}")
    return data[key]


def point_value(point: dict[str, Any]) -> float:
    if "value" in point:
        return float(point["value"])
    for key in ("load", "sets", "reps"):
        require(point, key, "容量数据点")
    return float(point["load"]) * float(point["sets"]) * float(point["reps"])


def scale(values: list[float], floor_zero: bool = False) -> tuple[float, float]:
    lower, upper = min(values), max(values)
    if floor_zero:
        lower = 0.0
    span = upper - lower
    padding = max(1.0, span * 0.12, upper * 0.04 if upper else 1.0)
    top = upper + padding
    bottom = max(0.0, lower - padding) if floor_zero else lower - padding
    if math.isclose(top, bottom):
        top += 1.0
        bottom -= 1.0
    return bottom, top


def map_y(value: float, bottom: float, top: float, y_top: float = 52, y_bottom: float = 268) -> float:
    return y_bottom - (value - bottom) / (top - bottom) * (y_bottom - y_top)


def map_x(week: int, weeks: int, x_left: float = 72, x_right: float = 968) -> float:
    if weeks <= 1:
        return (x_left + x_right) / 2
    return x_left + (week - 1) / (weeks - 1) * (x_right - x_left)


def pchip_path(points: list[tuple[float, float]]) -> str:
    """Return a Fritsch-Carlson monotone cubic SVG path through sorted points."""
    if not points:
        return ""
    if len(points) == 1:
        return f"M{number(points[0][0])},{number(points[0][1])}"
    xs, ys = zip(*points)
    slopes = [(ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i]) for i in range(len(points) - 1)]
    tangents = [slopes[0]]
    for i in range(1, len(points) - 1):
        previous, following = slopes[i - 1], slopes[i]
        if previous == 0 or following == 0 or previous * following <= 0:
            tangents.append(0.0)
            continue
        h0, h1 = xs[i] - xs[i - 1], xs[i + 1] - xs[i]
        tangents.append(3 * (h0 + h1) / ((2 * h1 + h0) / previous + (h1 + 2 * h0) / following))
    tangents.append(slopes[-1])
    chunks = [f"M{number(xs[0])},{number(ys[0])}"]
    for i in range(len(points) - 1):
        h = xs[i + 1] - xs[i]
        chunks.append(
            "C"
            f"{number(xs[i] + h / 3)},{number(ys[i] + tangents[i] * h / 3)} "
            f"{number(xs[i + 1] - h / 3)},{number(ys[i + 1] - tangents[i + 1] * h / 3)} "
            f"{number(xs[i + 1])},{number(ys[i + 1])}"
        )
    return " ".join(chunks)


def rpe_audit(rows: list[list[Any]], title: str) -> None:
    static = re.compile(r"(?<!\d)([2-9]\d*)\s*[×x]\s*\d+[^;；。\n]*?@([^;；。\n]*)")
    exceptions = ("顶组", "测试", "历史", "实际")
    for row in rows:
        for cell in row:
            content = str(cell)
            for match in static.finditer(content):
                if "→" not in match.group(0) and not any(word in content for word in exceptions):
                    raise ValueError(f"{title} 存在静态多组 RPE 处方：{content}")


def render_chart(cycle: dict[str, Any], phases: list[dict[str, Any]], weeks: int) -> str:
    chart = require(cycle, "chart", cycle.get("title", "周期"))
    strong = list(require(chart, "strength", "图表"))
    volume = list(require(chart, "volume", "图表"))
    for collection in (strong, volume):
        for point in collection:
            require(point, "week", "图表数据点")
            if not 1 <= int(point["week"]) <= weeks:
                raise ValueError(f"图表周次超出周期范围：W{point['week']}")
    strong_values = [point_value(point) for point in strong]
    volume_values = [point_value(point) for point in volume]
    s_bottom, s_top = scale(strong_values)
    v_bottom, v_top = scale(volume_values, floor_zero=True)
    strong_xy = [(map_x(int(p["week"]), weeks), map_y(point_value(p), s_bottom, s_top)) for p in strong]
    volume_xy = [(map_x(int(p["week"]), weeks), map_y(point_value(p), v_bottom, v_top)) for p in volume]
    strong_path, volume_path = pchip_path(strong_xy), pchip_path(volume_xy)
    area = f"{strong_path} L{number(strong_xy[-1][0])},268 L{number(strong_xy[0][0])},268 Z"
    phase_colors = ("#1f2937", "#737373", "#c2571f", "#1f2937", "#171717")
    bands = []
    for index, phase in enumerate(phases):
        start, end = int(phase["start_week"]), int(phase["end_week"])
        left = map_x(start, weeks) - (0 if start == 1 else 0.5 * (map_x(start, weeks) - map_x(start - 1, weeks)))
        right = map_x(end, weeks) + (0 if end == weeks else 0.5 * (map_x(end + 1, weeks) - map_x(end, weeks)))
        center = (left + right) / 2
        bands.append(f'<rect x="{number(left)}" y="52" width="{number(right-left)}" height="216" fill="{phase_colors[index % len(phase_colors)]}" opacity="0.055"/>')
        bands.append(f'<text x="{number(center)}" y="66" font-size="12" fill="{MUTED}" text-anchor="middle">{text(phase["label"])}</text>')
    grids = []
    for i in range(6):
        y = 52 + i * (216 / 5)
        s_value = s_top - i * (s_top - s_bottom) / 5
        v_value = v_top - i * (v_top - v_bottom) / 5
        grids.append(f'<line x1="72" y1="{number(y)}" x2="968" y2="{number(y)}" stroke="{LIGHT}" stroke-width="0.5"/>')
        grids.append(f'<text x="64" y="{number(y+4)}" font-size="12" fill="#a3a3a1" text-anchor="end">{number(s_value)}</text>')
        grids.append(f'<text x="976" y="{number(y+4)}" font-size="12" fill="#a3a3a1">{number(v_value)}</text>')
    dots = []
    for point, (x, y) in zip(strong, strong_xy):
        label = point.get("label", number(point_value(point)))
        fill = BODYWEIGHT if point.get("kind") == "bodyweight" else INK
        anchor = "end" if x > 940 else "middle"
        label_x = x - 6 if anchor == "end" else x
        dots.append(f'<circle cx="{number(x)}" cy="{number(y)}" r="3.5" fill="{fill}" stroke="#fff" stroke-width="1.5"/>')
        dots.append(f'<text x="{number(label_x)}" y="{number(max(42, y-10))}" font-size="12" font-weight="500" fill="{fill}" text-anchor="{anchor}">{text(label)}</text>')
    for point, (x, y) in zip(volume, volume_xy):
        label = point.get("label", number(point_value(point)))
        anchor = "end" if x > 940 else "middle"
        label_x = x - 6 if anchor == "end" else x
        dots.append(f'<circle cx="{number(x)}" cy="{number(y)}" r="3.5" fill="#fff" stroke="{GRAY}" stroke-width="1.5"/>')
        dots.append(f'<text x="{number(label_x)}" y="{number(min(258, y+18))}" font-size="12" font-weight="500" fill="{GRAY}" text-anchor="{anchor}">{text(label)}</text>')
    weeks_text = "".join(f'<text x="{number(map_x(week, weeks))}" y="292" font-size="12" fill="{MUTED}" text-anchor="middle">W{week}</text>' for week in range(1, weeks + 1))
    title = cycle.get("title", "主项周期")
    desc = chart.get("description", f"{title} 的强度与容量单调三次渐进曲线")
    footnote = chart.get("footnote", "容量以本计划声明的正式工作组口径计算")
    return f'''<div class="progression-chart">
<svg viewBox="0 0 1040 344" width="100%" role="img" aria-label="{text(title)}力量与容量渐进曲线">
<title>{text(title)} · 力量与容量渐进</title><desc>{text(desc)}</desc>
{''.join(bands)}{''.join(grids)}
<line x1="72" y1="21" x2="90" y2="21" stroke="{INK}" stroke-width="2.5" stroke-linecap="round"/><circle cx="81" cy="21" r="3" fill="{INK}" stroke="#fff" stroke-width="1"/><text x="96" y="25" font-size="12" fill="{INK}">{text(chart.get('strength_label', '强度'))}</text>
<line x1="194" y1="21" x2="212" y2="21" stroke="{GRAY}" stroke-width="2" stroke-linecap="round"/><circle cx="203" cy="21" r="3" fill="#fff" stroke="{GRAY}" stroke-width="1"/><text x="218" y="25" font-size="12" fill="{INK}">{text(chart.get('volume_label', '容量'))}</text>
<path d="{area}" fill="{INK}" opacity="0.05"/><path d="{volume_path}" fill="none" stroke="{GRAY}" stroke-width="2" stroke-linecap="round"/><path d="{strong_path}" fill="none" stroke="{INK}" stroke-width="2.5" stroke-linecap="round"/>
{''.join(dots)}{weeks_text}<text x="72" y="318" font-size="12" fill="#a3a3a1">{text(footnote)}</text>
</svg></div>'''


def table(headers: list[Any], rows: list[list[Any]]) -> str:
    head = "".join(f"<th>{text(value)}</th>" for value in headers)
    body = "".join("<tr>" + "".join(f"<td>{text(value)}</td>" for value in row) + "</tr>" for row in rows)
    return f'<div class="cycle"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def render_html(data: dict[str, Any], header_asset: Path | None) -> str:
    plan = require(data, "plan", "根数据")
    weeks = int(require(plan, "weeks", "计划"))
    if not 8 <= weeks <= 12:
        raise ValueError("周期长度必须为 8—12 周")
    phases = list(require(data, "phases", "根数据"))
    cycles = list(require(data, "cycles", "根数据"))
    image = ""
    if header_asset and header_asset.exists():
        mime = "image/png" if header_asset.suffix.lower() == ".png" else "image/jpeg"
        image = f"data:{mime};base64,{base64.b64encode(header_asset.read_bytes()).decode('ascii')}"
    schedule_rows = "".join(
        f'<tr><td>{text(item.get("day", "训练日"))}</td><td>{text(item.get("theme", item.get("label", "待核验")))}</td><td>{text(item.get("role", "职责"))}</td></tr>'
        for item in data.get("schedule", [])
    )
    session_cards = []
    for item in data.get("schedule", []):
        exercises = item.get("exercises", [])
        if not exercises:
            continue
        exercise_rows = "".join(
            f'<tr><td>{text(exercise.get("name", "动作"))}</td><td>{text(exercise.get("sets", "见处方"))}</td><td>{text(exercise.get("target", "待核验"))}</td></tr>'
            for exercise in exercises
        )
        session_cards.append(
            f'<article class="training-card"><span class="pill">{text(item.get("label", item.get("theme", "训练日")))}</span>'
            f'<h3>{text(item.get("title", item.get("theme", "训练安排")))}</h3>'
            f'<div class="session-table"><table><thead><tr><th>动作</th><th>组次</th><th>目标</th></tr></thead><tbody>{exercise_rows}</tbody></table></div></article>'
        )
    cycle_html = []
    for cycle in cycles:
        rows = list(require(cycle, "rows", cycle.get("title", "周期")))
        headers = list(require(cycle, "headers", cycle.get("title", "周期")))
        rpe_audit(rows, cycle.get("title", "周期"))
        cycle_html.append(f'<h3>{text(require(cycle, "title", "周期"))}</h3>{render_chart(cycle, phases, weeks)}{table(headers, rows)}')
    rules = "".join(f'<article class="rule"><h3>{text(item.get("title", "规则"))}</h3><p>{text(item.get("body", "待补充"))}</p></article>' for item in data.get("rules", []))
    header_style = f' style="--header-image:url(\'{image}\');"' if image else ""
    metrics = plan.get("metrics") or [
        {"value": "4", "label": "每周训练日"},
        {"value": f"{weeks} 周", "label": "本轮周期长度"},
        {"value": "2 次", "label": "每周卧推、引体暴露"},
        {"value": "1 次 / 2周", "label": "重硬拉暴露"},
    ]
    metric_html = "".join(f'<div class="metric"><strong>{text(item.get("value", "待核验"))}</strong><span>{text(item.get("label", ""))}</span></div>' for item in metrics)
    baseline = plan.get("baseline", "当前基准与限制见本计划的执行基准和各主项周期表。")
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{text(plan.get('title', '力量训练周期计划'))}</title><style>
:root{{--bg:#fff;--surface:#f5f5f4;--line:#e5e5e5;--ink:#171717;--muted:#737373;--accent:#1a5c3f;--warn:#c2571f}}*{{box-sizing:border-box}}html,body{{max-width:100%;overflow-x:hidden}}html{{scroll-behavior:smooth}}body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.65 "PingFang SC","Microsoft YaHei",sans-serif}}header{{position:relative;overflow:hidden;border-top:3px solid var(--accent);padding:64px max(28px,calc((100vw - 1040px)/2)) 48px;background:#fff}}header::after{{content:"";position:absolute;right:max(28px,calc((100vw - 1040px)/2));bottom:0;width:300px;height:210px;background:var(--header-image) right bottom/contain no-repeat;opacity:.96}}header>*{{position:relative;z-index:1;min-width:0;max-width:650px}}h1,h2,h3,p,strong{{overflow-wrap:anywhere;word-break:break-word}}h1{{font-size:42px;line-height:1.16;letter-spacing:-.03em;margin:8px 0 12px}}h2{{font-size:32px;line-height:1.25;letter-spacing:-.03em;margin:0 0 34px}}h3{{font-size:26px;line-height:1.3;margin:24px 0 28px;letter-spacing:-.025em}}p{{margin:0;color:#404040}}.eyebrow{{color:var(--accent);font-size:13px;letter-spacing:.12em;font-weight:700}}nav{{position:sticky;top:0;z-index:4;border-top:1px solid var(--line);border-bottom:1px solid var(--line);background:rgba(255,255,255,.95);backdrop-filter:blur(8px);padding:12px max(28px,calc((100vw - 1040px)/2))}}nav a{{margin-right:26px;color:var(--muted);text-decoration:none;font-size:14px}}nav a:hover{{color:var(--accent)}}main{{width:100%;max-width:1040px;min-width:0;margin:auto;padding:64px 0 88px;counter-reset:section}}section{{min-width:0;scroll-margin-top:64px;margin:0 0 76px}}section>h2::before{{counter-increment:section;content:"0" counter(section);color:#737373;font-size:18px;font-weight:500;margin-right:18px;vertical-align:middle;letter-spacing:0}}.parameter-card{{min-width:0;background:var(--surface);border-radius:18px;padding:34px 36px 28px}}.parameter-card .section-label{{display:flex;align-items:center;gap:18px;font-size:30px;font-weight:750;letter-spacing:-.03em;border-top:2px solid var(--line);padding-top:24px}}.parameter-card .section-label span{{color:#737373;font-size:17px;font-weight:500;letter-spacing:0}}.baseline{{font-size:18px;line-height:1.7;margin:34px 0 42px;max-width:920px;overflow-wrap:anywhere}}.metrics{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:28px}}.metric{{min-width:0}}.metric strong{{display:block;font-size:48px;line-height:1.05;letter-spacing:-.04em}}.metric span{{display:block;color:var(--muted);margin-top:8px}}.schedule-table,.session-table,.cycle{{max-width:100%;overflow-x:auto}}table{{width:100%;border-collapse:collapse;min-width:760px}}th,td{{padding:20px 0;text-align:left;vertical-align:top;border-bottom:1px solid var(--line)}}th{{color:var(--muted);font-size:15px;font-weight:500}}td{{font-size:19px}}.schedule-table th:nth-child(1),.schedule-table td:nth-child(1){{width:20%}}.schedule-table th:nth-child(2),.schedule-table td:nth-child(2){{width:31%}}.training-cards{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:22px}}.training-card{{border:1px solid var(--line);border-radius:18px;padding:28px 30px;background:#fff}}.pill{{display:inline-block;background:var(--surface);border-radius:999px;padding:6px 14px;color:#525252;font-size:14px}}.training-card h3{{font-size:25px;margin:26px 0 24px}}.session-table table{{min-width:0}}.session-table th,.session-table td{{padding:15px 0;font-size:16px}}.session-table th:nth-child(1),.session-table td:nth-child(1){{width:34%}}.session-table th:nth-child(2),.session-table td:nth-child(2){{width:26%}}.cycle{{margin:14px 0 42px}}.cycle th,.cycle td{{padding:15px 12px;font-size:15px}}.cycle th{{font-size:13px}}.progression-chart{{margin:0 0 20px;overflow-x:auto}}.progression-chart svg{{display:block;width:100%;min-width:720px;height:auto}}.rule{{border-top:1px solid var(--line);padding:24px 0}}.rule h3{{font-size:20px;margin:0 0 8px}}@media(max-width:760px){{header{{padding:42px 20px 34px}}header::after{{display:none}}h1{{font-size:31px}}h2{{font-size:27px;margin-bottom:26px}}main{{padding:44px 20px 68px}}nav{{padding:11px 20px;white-space:nowrap;overflow-x:auto}}nav a{{margin-right:18px}}section{{margin-bottom:58px}}.parameter-card{{padding:25px 20px}}.parameter-card .section-label{{font-size:24px;padding-top:18px}}.metrics{{grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}}.training-cards{{grid-template-columns:1fr;gap:20px}}.metric strong{{font-size:36px}}.baseline{{font-size:16px;margin:26px 0 30px}}.training-card{{padding:24px 20px}}.session-table{{margin-right:-2px}}.schedule-table table{{min-width:650px}}}}@media print{{nav{{position:static}}header::after{{display:none}}main{{padding:28px 0}}.parameter-card{{break-inside:avoid}}.training-card{{break-inside:avoid}}}}
</style></head><body><header{header_style}><div class="eyebrow">力量训练周期规划</div><h1>{text(plan.get('title', '力量训练周期计划'))}</h1><p>{text(plan.get('subtitle', plan.get('goal', '待核验')))}</p></header><nav><a href="#overview">概览</a><a href="#schedule">每周安排</a><a href="#sessions">训练日</a><a href="#cycles">周期</a><a href="#rules">规则</a></nav><main><section id="overview"><div class="parameter-card"><div class="section-label"><span>01</span>计划参数</div><p class="baseline">{text(baseline)}</p><div class="metrics">{metric_html}</div></div></section><section id="schedule"><h2>每周安排</h2><div class="schedule-table"><table><thead><tr><th>建议日程</th><th>训练主题</th><th>主项职责</th></tr></thead><tbody>{schedule_rows}</tbody></table></div></section><section id="sessions"><h2>训练日安排</h2><div class="training-cards">{''.join(session_cards)}</div></section><section id="cycles"><h2>主项周期</h2>{''.join(cycle_html)}</section><section id="rules"><h2>执行规则</h2>{rules}</section></main></body></html>'''


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a standalone strength-cycle HTML plan from JSON.")
    parser.add_argument("input", type=Path, help="计划 JSON 数据文件")
    parser.add_argument("output", type=Path, help="新 HTML 输出路径")
    parser.add_argument("--header-asset", type=Path, default=Path(__file__).parents[1] / "assets" / "header-lineart.png")
    parser.add_argument("--force", action="store_true", help="允许覆盖输出文件；默认拒绝覆盖")
    args = parser.parse_args()
    if args.output.exists() and not args.force:
        raise SystemExit(f"拒绝覆盖已有文件：{args.output}。请新建 -v02/-v03 版本或显式传入 --force。")
    data = json.loads(args.input.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_html(data, args.header_asset), encoding="utf-8")
    print(f"已生成：{args.output}")


if __name__ == "__main__":
    main()
