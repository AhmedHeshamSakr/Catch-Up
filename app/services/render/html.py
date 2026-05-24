from __future__ import annotations

import html
from pathlib import Path

from app.core.domain import Category, DigestRun, Importance, NewsItem
from app.services.render.markdown import CATEGORY_TITLES

# importance -> (label, text color, bg)
_BADGE: dict[Importance, tuple[str, str, str]] = {
    Importance.HIGH: ("HIGH", "#DC2626", "#FEF2F2"),
    Importance.MEDIUM: ("MEDIUM", "#A16207", "#FEFCE8"),
    Importance.LOW: ("LOW", "#0E7490", "#ECFEFF"),
}

_STYLE = """
:root{--bg:#F4F6F9;--surface:#fff;--line:#E6EBF1;--ink:#0B1220;--sub:#64748B;--emerald:#059669;--cyan:#0891B2}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font-family:'Inter',system-ui,sans-serif;line-height:1.5}
.wrap{max-width:880px;margin:0 auto;padding:32px 20px}
h1{font-size:24px;letter-spacing:-.02em;margin:0 0 4px}
.meta{color:var(--sub);font-size:13px;margin-bottom:24px}
.lead{background:var(--surface);border:1px solid var(--line);border-left:3px solid var(--emerald);
border-radius:12px;padding:16px 18px;margin-bottom:24px}
.lead h2{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--emerald);margin:0 0 8px}
h3{font-size:15px;margin:24px 0 12px;color:var(--ink)}
.card{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin-bottom:10px}
.card a{color:var(--ink);text-decoration:none;font-weight:600}
.card a:hover{color:var(--cyan)}
.sum{color:var(--sub);font-size:13.5px;margin-top:6px}
.row{display:flex;gap:8px;align-items:center;margin-top:8px;flex-wrap:wrap}
.badge{font-size:10px;font-weight:700;padding:3px 8px;border-radius:999px;letter-spacing:.04em}
.src{color:#94A3B8;font-size:11.5px}
"""


def _esc(value: str | None) -> str:
    return html.escape(value or "")


def _safe_href(url: str | None) -> str:
    """Allow only http(s) links as live hrefs; collapse anything else to '#'.

    Guards against javascript:/data:/etc. scheme injection in rendered output.
    """
    value = (url or "").strip()
    if value.lower().startswith(("http://", "https://")):
        return value
    return "#"


def _card(item: NewsItem) -> str:
    badge = ""
    if item.importance and item.importance in _BADGE:
        label, fg, bg = _BADGE[item.importance]
        badge = f'<span class="badge" style="color:{fg};background:{bg}">{label}</span>'
    summary = f'<div class="sum">{_esc(item.summary_en)}</div>' if item.summary_en else ""
    return (
        f'<div class="card"><a href="{_esc(_safe_href(item.url))}">{_esc(item.title)}</a>'
        f'<div class="row">{badge}<span class="src">{_esc(item.source_name)}</span></div>'
        f"{summary}</div>"
    )


def render_html(run: DigestRun, items: list[NewsItem]) -> str:
    n_categories = len({i.category for i in items if i.category})
    parts: list[str] = [
        "<!DOCTYPE html>",
        '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>News Catch-Up — {run.started_at:%Y-%m-%d}</title>",
        '<link rel="preconnect" href="https://fonts.googleapis.com">',
        '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">',
        f"<style>{_STYLE}</style></head><body><div class='wrap'>",
        "<h1>News Catch-Up</h1>",
        f'<div class="meta">{run.started_at:%A, %d %B %Y · %H:%M UTC} — {len(items)} items across {n_categories} categories</div>',
    ]
    if run.narrative:
        parts.append(f'<div class="lead"><h2>What matters most</h2>{_esc(run.narrative)}</div>')

    grouped: dict[Category | None, list[NewsItem]] = {}
    for item in items:
        grouped.setdefault(item.category, []).append(item)
    for category in [*CATEGORY_TITLES.keys(), None]:
        group = grouped.get(category)
        if not group:
            continue
        title = CATEGORY_TITLES.get(category, "Uncategorized")
        parts.append(f"<h3>{_esc(title)}</h3>")
        parts.extend(_card(i) for i in group)

    parts.append("</div></body></html>")
    return "\n".join(parts)


def write_html(run: DigestRun, items: list[NewsItem], output_dir: str) -> str:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"digest-{run.run_id}.html"
    path.write_text(render_html(run, items), encoding="utf-8")
    return str(path)
