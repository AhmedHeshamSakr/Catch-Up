from app.core.domain import Category, DigestRun, NewsItem, RawItem, SourceType
from app.services.render import markdown


def _item(title: str, url: str, cat: Category) -> NewsItem:
    raw = RawItem(
        source_id="s", source_type=SourceType.RSS, source_name="Src",
        url=url, title=title, category_hint=cat,
    )
    return NewsItem.from_raw(raw, run_id="r1")


def test_render_markdown_groups_by_category():
    run = DigestRun(run_id="r1")
    items = [
        _item("AI thing", "https://a.com/1", Category.AI_TECH),
        _item("Gulf thing", "https://a.com/2", Category.GULF_MENA),
    ]
    out = markdown.render_markdown(run, items)
    assert "# News Catch-Up" in out
    assert "## AI & Technology" in out
    assert "## Gulf & MENA" in out
    assert "[AI thing](https://a.com/1)" in out
    assert "Src" in out


def test_write_markdown_creates_file(tmp_path):
    run = DigestRun(run_id="rX")
    path = markdown.write_markdown(run, [_item("t", "https://a.com/9", Category.AI_TECH)], str(tmp_path))
    assert path.endswith("digest-rX.md")
    from pathlib import Path
    assert "AI & Technology" in Path(path).read_text(encoding="utf-8")
