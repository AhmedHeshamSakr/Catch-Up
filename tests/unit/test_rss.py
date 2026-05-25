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

# Feed with image variants: media:thumbnail, media:content, enclosure, and a
# bad (non-http) media value plus an entry with no image at all.
IMAGE_FEED = b"""<?xml version="1.0"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/"><channel><title>Demo</title>
<item><title>Thumb</title><link>https://demo.com/thumb</link>
<media:thumbnail url="https://img.demo.com/thumb.jpg" /></item>
<item><title>Content</title><link>https://demo.com/content</link>
<media:content url="https://img.demo.com/content.jpg" type="image/jpeg" /></item>
<item><title>Enclosure</title><link>https://demo.com/enc</link>
<enclosure url="https://img.demo.com/enc.jpg" type="image/jpeg" /></item>
<item><title>Bad Scheme</title><link>https://demo.com/bad</link>
<media:thumbnail url="data:image/png;base64,AAAA" /></item>
<item><title>No Image</title><link>https://demo.com/none</link></item>
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


def test_parse_feed_extracts_image_from_media_thumbnail_content_enclosure():
    items = rss.parse_feed(IMAGE_FEED, _source())
    by_url = {i.url: i for i in items}
    assert by_url["https://demo.com/thumb"].image_url == "https://img.demo.com/thumb.jpg"
    assert by_url["https://demo.com/content"].image_url == "https://img.demo.com/content.jpg"
    assert by_url["https://demo.com/enc"].image_url == "https://img.demo.com/enc.jpg"


def test_parse_feed_image_none_when_absent_or_non_http():
    items = rss.parse_feed(IMAGE_FEED, _source())
    by_url = {i.url: i for i in items}
    assert by_url["https://demo.com/none"].image_url is None
    assert by_url["https://demo.com/bad"].image_url is None  # data: rejected


def test_fetch_feed_rejects_private_address():
    """The DEFAULT fetch path must reject a private/loopback/link-local URL.

    Uses an IP-literal host so socket.getaddrinfo resolves to the literal
    without any real DNS/network call (stays offline).
    """
    from app.services.net import UnsafeURLError

    with pytest.raises(UnsafeURLError):
        rss.fetch_feed("http://169.254.169.254/latest/meta-data/")
