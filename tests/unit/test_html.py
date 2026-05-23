from app.core.domain import (
    Category,
    DigestRun,
    Importance,
    NewsItem,
    RawItem,
    SourceType,
)
from app.services.render import html as html_render


def _item(title, summary, imp, cat):
    raw = RawItem(source_id="s", source_type=SourceType.RSS, source_name="Src",
                  url="https://a.com/x", title=title, category_hint=cat)
    it = NewsItem.from_raw(raw, run_id="r1")
    it.category = cat
    it.summary_en = summary
    it.importance = imp
    return it


def test_render_html_includes_narrative_sections_and_badge():
    run = DigestRun(run_id="r1", narrative="The big picture today.")
    items = [_item("AI launch", "A summary.", Importance.HIGH, Category.AI_TECH)]
    out = html_render.render_html(run, items)
    assert "<!DOCTYPE html>" in out
    assert "The big picture today." in out
    assert "AI launch" in out
    assert "A summary." in out
    assert "HIGH" in out
    assert "AI &amp; Technology" in out  # category title HTML-escaped


def test_render_html_escapes_untrusted_content():
    run = DigestRun(run_id="r1", narrative="<b>x</b>")
    items = [_item("<script>alert(1)</script>", "<img src=x>", Importance.LOW, Category.AI_TECH)]
    out = html_render.render_html(run, items)
    assert "<script>alert(1)</script>" not in out         # raw injection absent
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in out  # escaped form present
    assert "&lt;img src=x&gt;" in out
    assert "&lt;b&gt;x&lt;/b&gt;" in out                   # narrative escaped


def test_write_html_creates_file(tmp_path):
    run = DigestRun(run_id="rZ")
    path = html_render.write_html(run, [_item("t", "s", Importance.MEDIUM, Category.AI_TECH)], str(tmp_path))
    assert path.endswith("digest-rZ.html")
    from pathlib import Path
    assert "<!DOCTYPE html>" in Path(path).read_text(encoding="utf-8")
