#!/usr/bin/env python3
"""Render the user-facing SYSTEM-FLOW.md as a standalone local HTML page."""

from __future__ import annotations

import html
import re
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "SYSTEM-FLOW.md"
OUTPUT = ROOT / "SYSTEM-FLOW.html"


def inline(value: str) -> str:
    escaped = html.escape(value, quote=False)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', escaped)
    return escaped


def slugify(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value).strip().lower()
    value = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "-", value)
    return value.strip("-") or "section"


def split_table_row(line: str) -> list[str]:
    return [part.strip() for part in line.strip().strip("|").split("|")]


def render_blocks(lines: list[str], ids: dict[str, int] | None = None, toc: list[tuple[int, str, str]] | None = None) -> str:
    ids = ids if ids is not None else {}
    toc = toc if toc is not None else []
    output: list[str] = []
    index = 0

    while index < len(lines):
        line = lines[index].rstrip()
        if not line.strip():
            index += 1
            continue

        heading = re.match(r"^(#{1,4})\s+(.+)$", line)
        if heading:
            level = len(heading.group(1))
            title = heading.group(2).strip()
            base = slugify(title)
            ids[base] = ids.get(base, 0) + 1
            section_id = base if ids[base] == 1 else f"{base}-{ids[base]}"
            output.append(f'<h{level} id="{section_id}">{inline(title)}</h{level}>')
            if level == 2:
                toc.append((level, title, section_id))
            index += 1
            continue

        if line.startswith(">"):
            quoted: list[str] = []
            while index < len(lines) and (lines[index].startswith(">") or not lines[index].strip()):
                current = lines[index]
                if current.startswith(">"):
                    current = current[1:]
                    if current.startswith(" "):
                        current = current[1:]
                    quoted.append(current)
                elif quoted and quoted[-1].strip():
                    quoted.append("")
                index += 1
            kind = "dialogue"
            title = "AI 对话输出"
            if quoted and re.match(r"^\[![a-zA-Z]+\]", quoted[0]):
                marker = re.match(r"^\[!([a-zA-Z]+)\]\s*(.*)$", quoted.pop(0))
                kind = marker.group(1).lower()
                title = marker.group(2).strip() or "重要说明"
            body = render_blocks(quoted, ids={}, toc=[])
            output.append(f'<section class="quote-card {kind}"><div class="quote-label">{inline(title)}</div>{body}</section>')
            continue

        if index + 1 < len(lines) and line.strip().startswith("|") and re.match(r"^\s*\|?\s*:?-+", lines[index + 1]):
            headers = split_table_row(line)
            index += 2
            rows: list[list[str]] = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                rows.append(split_table_row(lines[index]))
                index += 1
            head_html = "".join(f"<th>{inline(cell)}</th>" for cell in headers)
            body_html = "".join("<tr>" + "".join(f"<td>{inline(cell)}</td>" for cell in row) + "</tr>" for row in rows)
            output.append(f'<div class="table-wrap"><table><thead><tr>{head_html}</tr></thead><tbody>{body_html}</tbody></table></div>')
            continue

        unordered = re.match(r"^\s*-\s+(.+)$", line)
        if unordered:
            items: list[str] = []
            while index < len(lines):
                match = re.match(r"^\s*-\s+(.+)$", lines[index])
                if not match:
                    break
                item = match.group(1)
                checkbox = re.match(r"^\[([ xX])\]\s*(.*)$", item)
                if checkbox:
                    checked = " checked" if checkbox.group(1).lower() == "x" else ""
                    items.append(f'<li class="check"><input type="checkbox" disabled{checked}> {inline(checkbox.group(2))}</li>')
                else:
                    items.append(f"<li>{inline(item)}</li>")
                index += 1
            output.append("<ul>" + "".join(items) + "</ul>")
            continue

        ordered = re.match(r"^\s*\d+\.\s+(.+)$", line)
        if ordered:
            items: list[str] = []
            while index < len(lines):
                match = re.match(r"^\s*\d+\.\s+(.+)$", lines[index])
                if not match:
                    break
                items.append(f"<li>{inline(match.group(1))}</li>")
                index += 1
            output.append("<ol>" + "".join(items) + "</ol>")
            continue

        paragraph = [line.strip()]
        index += 1
        while index < len(lines):
            upcoming = lines[index].rstrip()
            if not upcoming.strip() or re.match(r"^(#{1,4})\s+", upcoming) or upcoming.startswith(">"):
                break
            if re.match(r"^\s*(-|\d+\.)\s+", upcoming):
                break
            if upcoming.strip().startswith("|"):
                break
            paragraph.append(upcoming.strip())
            index += 1
        output.append("<p>" + inline(" ".join(paragraph)) + "</p>")

    return "\n".join(output)


def main() -> None:
    markdown = SOURCE.read_text(encoding="utf-8-sig")
    lines = markdown.splitlines()
    ids: dict[str, int] = {}
    toc: list[tuple[int, str, str]] = []
    article = render_blocks(lines, ids=ids, toc=toc)
    nav = "\n".join(
        f'<a class="toc-link" href="#{section_id}" data-search="{html.escape(title.lower())}">{html.escape(title)}</a>'
        for _, title, section_id in toc
    )
    generated = datetime.now().astimezone().isoformat(timespec="seconds")
    page = f'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>Lzheng AI 健身系统用户流程与对话输出</title>
  <style>
    :root{{--bg:#f3f3f0;--paper:#fff;--ink:#171717;--muted:#686864;--line:#d9d9d4;--soft:#ecece8;--sidebar:#111;--sidebar-text:#deded8;--content:980px}}
    *{{box-sizing:border-box}}html{{scroll-behavior:smooth;background:var(--bg)}}body{{margin:0;color:var(--ink);background:var(--bg);font-family:Inter,"PingFang SC","Microsoft YaHei",system-ui,sans-serif;line-height:1.72}}
    .shell{{display:grid;grid-template-columns:300px minmax(0,1fr);min-height:100vh}}aside{{position:sticky;top:0;height:100vh;overflow:auto;padding:28px 22px;background:var(--sidebar);color:#fff}}
    .brand{{font-size:12px;font-weight:800;letter-spacing:.16em}}.side-title{{margin:14px 0 18px;font-size:23px;line-height:1.22}}.meta{{margin-bottom:18px;color:#999;font-size:11px;line-height:1.55}}
    .search{{width:100%;margin-bottom:16px;padding:11px 12px;border:1px solid #393939;border-radius:10px;background:#1b1b1b;color:#fff;outline:none}}.search:focus{{border-color:#aaa}}.toc{{display:flex;flex-direction:column;gap:2px}}
    .toc-link{{display:block;padding:7px 9px;border-radius:8px;color:var(--sidebar-text);font-size:12px;line-height:1.45;text-decoration:none}}.toc-link:hover,.toc-link.active{{background:#2a2a2a;color:#fff}}.toc-link.hidden{{display:none}}
    main{{min-width:0;padding:54px 5vw 90px}}article{{max-width:var(--content);margin:0 auto;padding:54px 64px 76px;border:1px solid var(--line);border-radius:24px;background:var(--paper);box-shadow:0 20px 60px rgba(0,0,0,.055)}}
    h1{{margin:0 0 18px;font-size:42px;line-height:1.16;letter-spacing:-.035em}}h2{{scroll-margin-top:28px;margin:64px 0 20px;padding-top:9px;border-top:3px solid var(--ink);font-size:28px;line-height:1.28}}h3{{scroll-margin-top:28px;margin:38px 0 14px;font-size:20px}}h4{{margin:28px 0 10px;font-size:16px}}
    p{{margin:12px 0;color:#282826}}strong{{color:#0b0b0b}}a{{color:#111}}hr{{margin:46px 0;border:0;border-top:1px solid var(--line)}}ul,ol{{padding-left:24px}}li{{margin:5px 0}}
    code{{border-radius:5px;background:#edede9;padding:2px 5px;font-family:"Cascadia Code",Consolas,monospace;font-size:.88em}}.table-wrap{{overflow:auto;margin:16px 0;border:1px solid var(--line);border-radius:14px}}table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{padding:11px 13px;border-right:1px solid var(--line);border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}th:last-child,td:last-child{{border-right:0}}tr:last-child td{{border-bottom:0}}th{{background:#181818;color:#fff}}tbody tr:nth-child(even){{background:#f7f7f4}}
    .quote-card{{margin:18px 0;padding:18px 20px;border:1px solid #d4d4cf;border-left:5px solid #151515;border-radius:14px;background:#f7f7f4}}.quote-card.dialogue{{background:#f5f5f1}}.quote-card.important{{background:#eeeeea}}.quote-label{{display:inline-block;margin-bottom:8px;padding:4px 8px;border-radius:999px;background:#181818;color:#fff;font-size:11px;font-weight:750;letter-spacing:.05em}}.quote-card p{{margin:8px 0}}.quote-card ul,.quote-card ol{{margin:8px 0}}.check{{list-style:none;margin-left:-22px}}input[type=checkbox]{{accent-color:#111}}
    .doc-note{{margin:0 0 34px;padding:14px 16px;border:1px solid var(--line);border-radius:12px;background:#f7f7f4;color:var(--muted);font-size:12px}}
    @media(max-width:900px){{.shell{{display:block}}aside{{position:relative;height:auto;max-height:none;padding:22px}}.side-title{{font-size:20px}}.toc{{max-height:260px;overflow:auto}}main{{padding:18px 12px 70px}}article{{padding:32px 20px 54px;border-radius:16px}}h1{{font-size:31px}}h2{{font-size:24px;margin-top:50px}}h3{{font-size:18px}}}}
    @media print{{aside{{display:none}}.shell{{display:block}}main{{padding:0}}article{{max-width:none;border:0;box-shadow:none;padding:0}}h2{{break-before:page}}}}
  </style>
</head>
<body>
  <div class="shell">
    <aside>
      <div class="brand">LZHENG FITNESS</div>
      <div class="side-title">用户流程<br>与对话输出</div>
      <div class="meta">来源：SYSTEM-FLOW.md<br>生成：{html.escape(generated)}</div>
      <input id="tocSearch" class="search" type="search" placeholder="搜索阶段或对话…" aria-label="搜索目录">
      <nav class="toc" aria-label="文档目录">{nav}</nav>
    </aside>
    <main>
      <article>
        <div class="doc-note">这是用户验收版。每个阶段都列出 AI 应怎样回复、用户会拿到哪些文件，以及下一步做什么。</div>
        {article}
      </article>
    </main>
  </div>
  <script>
    const links=[...document.querySelectorAll('.toc-link')];
    const search=document.getElementById('tocSearch');
    search.addEventListener('input',()=>{{const q=search.value.trim().toLowerCase();links.forEach(a=>a.classList.toggle('hidden',q&&!a.dataset.search.includes(q)));}});
    const sections=links.map(a=>document.getElementById(a.getAttribute('href').slice(1))).filter(Boolean);
    const observer=new IntersectionObserver(entries=>{{const visible=entries.filter(e=>e.isIntersecting).sort((a,b)=>a.boundingClientRect.top-b.boundingClientRect.top)[0];if(!visible)return;links.forEach(a=>a.classList.toggle('active',a.getAttribute('href')==='#'+visible.target.id));}},{{rootMargin:'-10% 0px -75% 0px'}});
    sections.forEach(section=>observer.observe(section));
  </script>
</body>
</html>'''
    OUTPUT.write_text(page, encoding="utf-8")
    print(f"SYSTEM_FLOW_HTML: PASS\noutput: {OUTPUT}\nsections: {len(toc)}")


if __name__ == "__main__":
    main()
