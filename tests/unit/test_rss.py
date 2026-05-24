import pytest

from app.core.config import SourceConfig
from app.core.domain import Category, SourceType
from app.services import rss

SAMPLE_FEED = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>Demo</title>
<item><title>First Story</title><link>https://demo.com/1</link>
<description>Summary one</description>
<pubDate>Tue, 20 May 2026 09:00:00 GMT</pubDate></item>
<item><title>Second Story</title><link>https://demo.com/2</link></item>
<item><title>No Link</title></item>
</channel></rss>"""


def _source() -> SourceConfig:
    return SourceConfig(
        id="demo", type=SourceType.RSS, name="Demo",
        url="https://demo.com/feed", category_hint=Category.AI_TECH,
    )


def test_parse_feed_extracts_valid_entries():
    items = rss.parse_feed(SAMPLE_FEED, _source())
    assert len(items) == 2  # entry with no link is skipped
    first = items[0]
    assert first.title == "First Story"
    assert first.url == "https://demo.com/1"
    assert first.source_name == "Demo"
    assert first.category_hint == Category.AI_TECH
    assert first.published_at is not None


def test_fetch_feed_rejects_private_address():
    """The DEFAULT fetch path must reject a private/loopback/link-local URL.

    Uses an IP-literal host so socket.getaddrinfo resolves to the literal
    without any real DNS/network call (stays offline).
    """
    from app.services.net import UnsafeURLError

    with pytest.raises(UnsafeURLError):
        rss.fetch_feed("http://169.254.169.254/latest/meta-data/")
