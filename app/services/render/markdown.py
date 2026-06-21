from __future__ import annotations

from pathlib import Path

from app.core.domain import Category, DigestRun, NewsItem
from app.services.net import is_http_url

CATEGORY_TITLES: dict[Category, str] = {
    Category.AI_TECH: "AI & Technology",
    Category.BUSINESS_FINANCE: "Business & Finance",
    Category.WORLD_GEOPOLITICS: "World & Geopolitics",
    Category.GULF_MENA: "Gulf & MENA",
}


def _md_escape(text: str) -> str:
    """Escape characters that would break markdown link/emphasis syntax, so a
    crafted title/source can't inject a link or formatting."""
    for ch in ("\\", "[", "]", "(", ")", "*", "`", "_"):
        text = text.replace(ch, "\\" + ch)
    return text


def render_markdown(run: DigestRun, items: list[NewsItem]) -> str:
    n_categories = len({i.category for i in items if i.category})
    lines: list[str] = [
        f"# News Catch-Up — {run.started_at:%Y-%m-%d %H:%M UTC}",
        "",
        f"*{len(items)} items across {n_categories} categories.*",
        "",
    ]
    if run.narrative:
        lines += ["## What matters most", "", run.narrative, ""]

    grouped: dict[Category | None, list[NewsItem]] = {}
    for item in items:
        grouped.setdefault(item.category, []).append(item)

    ordered_keys: list[Category | None] = [*list(CATEGORY_TITLES.keys()), None]
    for cat in ordered_keys:
        group = grouped.get(cat)
        if not group:
            continue
        lines.append(f"## {CATEGORY_TITLES.get(cat, 'Uncategorized')}")
        lines.append("")
        for item in group:
            badge = f" `{item.importance.value.upper()}`" if item.importance else ""
            title = _md_escape(item.title)
            source = _md_escape(item.source_name)
            # Only link http(s) URLs (a javascript:/data: URL would become an
            # active link); otherwise render the title as plain text.
            if is_http_url(item.url):
                lines.append(f"- [{title}]({item.url}){badge} — *{source}*")
            else:
                lines.append(f"- {title}{badge} — *{source}*")
            if item.summary_en:
                lines.append(f"  {item.summary_en}")
        lines.append("")
    return "\n".join(lines)


def write_markdown(run: DigestRun, items: list[NewsItem], output_dir: str) -> str:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"digest-{run.run_id}.md"
    path.write_text(render_markdown(run, items), encoding="utf-8")
    return str(path)
