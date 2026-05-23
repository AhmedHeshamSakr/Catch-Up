from __future__ import annotations

from pathlib import Path

from app.core.domain import Category, DigestRun, Importance, NewsItem

CATEGORY_TITLES: dict[Category, str] = {
    Category.AI_TECH: "AI & Technology",
    Category.BUSINESS_FINANCE: "Business & Finance",
    Category.WORLD_GEOPOLITICS: "World & Geopolitics",
    Category.GULF_MENA: "Gulf & MENA",
}


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
            lines.append(f"- [{item.title}]({item.url}){badge} — *{item.source_name}*")
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
