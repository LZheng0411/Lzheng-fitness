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


def default_template() -> Path:
    return Path(__file__).resolve().parents[1] / "assets" / "strength-cycle-template.html"


def fill_template(values: dict[str, str]) -> str:
    path = default_template()
    if not path.is_file():
        raise ValueError(f"固定力量周期模板不存在：{path}")
    output = path.read_text(encoding="utf-8")
    for key, value in values.items():
        token = f"__{key}__"
        if token not in output:
            raise ValueError(f"固定力量周期模板缺少占位符：{token}")
        output = output.replace(token, value)
    unresolved = sorted(set(re.findall(r"__[A-Z0-9_]+__", output)))
    if unresolved:
        raise ValueError("固定力量周期模板仍有未替换占位符：" + ", ".join(unresolved))
    return output


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
    overview_html = (
        '<div class="parameter-card"><div class="section-label"><span>01</span>计划参数</div>'
        f'<p class="baseline">{text(baseline)}</p><div class="metrics">{metric_html}</div></div>'
    )
    schedule_html = (
        '<h2>周结构</h2><p class="lead">先看每个训练日承担的职责，再进入具体动作；这里不推算具体执行日期。</p>'
        f'<div class="schedule-table"><table><thead><tr><th>建议日程</th><th>训练主题</th><th>主项职责</th></tr></thead><tbody>{schedule_rows}</tbody></table></div>'
    )
    sessions_html = '<h2>训练日安排</h2><div class="training-cards">' + "".join(session_cards) + "</div>"
    cycles_html = '<h2>主项周期</h2><div class="scope-note">每个主项固定按“标题 → 强度/容量曲线 → 完整周期表”呈现；曲线和表格必须来自同一份 JSON。</div>' + "".join(
        f'<div class="cycle-block">{item}</div>' for item in cycle_html
    )
    rules_html = '<h2>执行规则</h2>' + rules
    return fill_template({
        "DOCUMENT_TITLE": text(plan.get("title", "力量训练周期计划")),
        "HEADER_STYLE": header_style.strip(),
        "PLAN_TITLE": text(plan.get("title", "力量训练周期计划")),
        "PLAN_SUBTITLE": text(plan.get("subtitle", plan.get("goal", "待核验"))),
        "OVERVIEW_HTML": overview_html,
        "SCHEDULE_HTML": schedule_html,
        "SESSIONS_HTML": sessions_html,
        "CYCLES_HTML": cycles_html,
        "RULES_HTML": rules_html,
    })


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
