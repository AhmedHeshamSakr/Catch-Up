from app.core.domain import (
    Category,
    DigestRun,
    Importance,
    NewsItem,
    RawItem,
    SourceType,
)
from app.services.render import markdown


def _item(title, summary, importance):
    raw = RawItem(source_id="s", source_type=SourceType.RSS, source_name="Src",
                  url="https://a.com/1", title=title, category_hint=Category.AI_TECH)
    it = NewsItem.from_raw(raw, run_id="r1")
    it.summary_en = summary
    it.importance = importance
    return it


def test_render_includes_narrative_summary_and_importance_badge():
    run = DigestRun(run_id="r1", narrative="The big picture today.")
    items = [_item("AI thing", "A concise summary.", Importance.HIGH)]
    out = markdown.render_markdown(run, items)
    assert "## What matters most" in out
    assert "The big picture today." in out
    assert "A concise summary." in out
    assert "`HIGH`" in out
