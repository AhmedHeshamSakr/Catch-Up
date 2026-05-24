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


def test_render_html_rejects_dangerous_href_schemes():
    run = DigestRun(run_id="r1")
    js_item = _item("JS link", "s", Importance.LOW, Category.AI_TECH)
    js_item.url = "javascript:alert(1)"
    data_item = _item("Data link", "s", Importance.LOW, Category.AI_TECH)
    data_item.url = "data:text/html,<script>alert(1)</script>"
    out = html_render.render_html(run, [js_item, data_item])
    # No live href to the dangerous schemes (escaped or not).
    assert 'href="javascript:' not in out
    assert "href=\"javascript:alert(1)\"" not in out
    assert 'href="data:' not in out
    # Dangerous urls collapse to a neutral href.
    assert 'href="#"' in out


def test_render_html_keeps_http_https_href():
    run = DigestRun(run_id="r1")
    http_item = _item("HTTP link", "s", Importance.LOW, Category.AI_TECH)
    http_item.url = "http://example.com/a"
    https_item = _item("HTTPS link", "s", Importance.LOW, Category.AI_TECH)
    https_item.url = "https://example.com/b"
    out = html_render.render_html(run, [http_item, https_item])
    assert 'href="http://example.com/a"' in out
    assert 'href="https://example.com/b"' in out


def test_write_html_creates_file(tmp_path):
    run = DigestRun(run_id="rZ")
    path = html_render.write_html(run, [_item("t", "s", Importance.MEDIUM, Category.AI_TECH)], str(tmp_path))
    assert path.endswith("digest-rZ.html")
    from pathlib import Path
    assert "<!DOCTYPE html>" in Path(path).read_text(encoding="utf-8")
