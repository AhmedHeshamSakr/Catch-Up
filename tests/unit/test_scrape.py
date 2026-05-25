from app.core.config import SourceConfig
from app.core.domain import Category, SourceType
from app.services import scrape

HTML = """
<html><head>
  <meta property="og:image" content="https://site.example/og.jpg">
</head><body>
  <a class="headline" href="/news/1">First Headline</a>
  <a class="headline" href="https://site.example/news/2">Second Headline</a>
  <a class="other" href="/ignore">Ignore me</a>
  <a class="headline" href="/news/3"></a>
</body></html>
"""

HTML_TWITTER = """
<html><head>
  <meta name="twitter:image" content="https://site.example/tw.jpg">
</head><body>
  <a class="headline" href="/news/1">First Headline</a>
</body></html>
"""

HTML_NO_IMAGE = """
<html><body>
  <a class="headline" href="/news/1">First Headline</a>
</body></html>
"""

HTML_BAD_IMAGE = """
<html><head>
  <meta property="og:image" content="data:image/png;base64,AAAA">
</head><body>
  <a class="headline" href="/news/1">First Headline</a>
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


def test_parse_page_extracts_og_image():
    items = scrape.parse_page(HTML, _source())
    assert all(i.image_url == "https://site.example/og.jpg" for i in items)


def test_parse_page_falls_back_to_twitter_image():
    items = scrape.parse_page(HTML_TWITTER, _source())
    assert items[0].image_url == "https://site.example/tw.jpg"


def test_parse_page_image_none_when_absent():
    items = scrape.parse_page(HTML_NO_IMAGE, _source())
    assert items[0].image_url is None


def test_parse_page_image_none_when_non_http():
    items = scrape.parse_page(HTML_BAD_IMAGE, _source())
    assert items[0].image_url is None


def test_collect_uses_injected_fetch():
    items = scrape.collect(_source(), fetch=lambda url: HTML)
    assert len(items) == 2
