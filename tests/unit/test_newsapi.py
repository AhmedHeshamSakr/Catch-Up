import pytest

from app.core.config import SourceConfig
from app.core.domain import Category, SourceType
from app.services import newsapi

SAMPLE = {
    "totalArticles": 2,
    "articles": [
        {"title": "AI breakthrough", "description": "desc one",
         "url": "https://news.example/1", "publishedAt": "2026-05-20T09:00:00Z",
         "image": "https://img.example/1.jpg",
         "source": {"name": "Example News"}},
        {"title": "", "description": "no title -> skipped",
         "url": "https://news.example/2", "publishedAt": "2026-05-20T10:00:00Z",
         "source": {"name": "Example News"}},
    ],
}

SAMPLE_NO_IMAGE = {
    "totalArticles": 1,
    "articles": [
        {"title": "No image article", "description": "desc",
         "url": "https://news.example/3", "publishedAt": "2026-05-20T09:00:00Z",
         "source": {"name": "Example News"}},
    ],
}


def _source():
    return SourceConfig(id="gnews_ai", type=SourceType.API, name="GNews AI",
                        query="artificial intelligence", category_hint=Category.AI_TECH,
                        lang="en")


def test_parse_gnews_maps_articles_and_skips_invalid():
    items = newsapi.parse_gnews(SAMPLE, _source())
    assert len(items) == 1
    it = items[0]
    assert it.title == "AI breakthrough"
    assert it.url == "https://news.example/1"
    assert it.source_name == "Example News"
    assert it.category_hint == Category.AI_TECH
    assert it.published_at is not None


def test_parse_gnews_extracts_image():
    items = newsapi.parse_gnews(SAMPLE, _source())
    assert items[0].image_url == "https://img.example/1.jpg"


def test_parse_gnews_image_none_when_absent():
    items = newsapi.parse_gnews(SAMPLE_NO_IMAGE, _source())
    assert items[0].image_url is None


def test_collect_uses_injected_fetch():
    captured = {}

    def fake_fetch(query, api_key, **kw):
        captured["query"] = query
        captured["api_key"] = api_key
        captured["kw"] = kw
        return SAMPLE

    items = newsapi.collect(_source(), "KEY123", fetch=fake_fetch)
    assert len(items) == 1
    assert captured["query"] == "artificial intelligence"
    assert captured["api_key"] == "KEY123"
    assert captured["kw"].get("lang") == "en"


def test_collect_empty_without_api_key():
    assert newsapi.collect(_source(), "", fetch=lambda *a, **k: SAMPLE) == []


def test_fetch_gnews_rejects_private_address():
    """The DEFAULT GNews fetch path must reject a host resolving to a private IP.

    Injects a resolver mapping the GNews host to a link-local metadata IP so no
    real DNS/network call happens — the SSRF guard must raise before the request.
    """
    from app.services.net import UnsafeURLError

    with pytest.raises(UnsafeURLError):
        newsapi.fetch_gnews(
            "ai", "KEY123", resolver=lambda host: ["169.254.169.254"]
        )
