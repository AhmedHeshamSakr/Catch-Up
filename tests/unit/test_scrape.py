from app.core.config import SourceConfig
from app.core.domain import Category, SourceType
from app.services import scrape

HTML = """
<html><body>
  <a class="headline" href="/news/1">First Headline</a>
  <a class="headline" href="https://site.example/news/2">Second Headline</a>
  <a class="other" href="/ignore">Ignore me</a>
  <a class="headline" href="/news/3"></a>
</body></html>
"""


def _source():
    return SourceConfig(id="site", type=SourceType.SCRAPE, name="Site",
                        url="https://site.example/news", selector="a.headline",
                        category_hint=Category.BUSINESS_FINANCE)


def test_parse_page_extracts_selected_links_and_resolves_relative():
    items = scrape.parse_page(HTML, _source())
    urls = [i.url for i in items]
    assert urls == ["https://site.example/news/1", "https://site.example/news/2"]
    assert items[0].title == "First Headline"
    assert items[0].source_name == "Site"
    assert items[0].category_hint == Category.BUSINESS_FINANCE


def test_parse_page_empty_without_selector():
    s = _source()
    s.selector = None
    assert scrape.parse_page(HTML, s) == []


def test_collect_uses_injected_fetch():
    items = scrape.collect(_source(), fetch=lambda url: HTML)
    assert len(items) == 2
