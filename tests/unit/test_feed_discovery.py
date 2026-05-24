from __future__ import annotations

import pytest

from app.services.feed_discovery import discover_feed

# ---------------------------------------------------------------------------
# Fixture HTML bodies
# ---------------------------------------------------------------------------

_RSS_HTML = b"""<!DOCTYPE html>
<html>
<head>
  <title>Paper</title>
  <link rel="alternate" type="application/rss+xml" href="/feed.xml" title="RSS Feed">
</head>
<body><p>Hello</p></body>
</html>
"""

_ATOM_HTML = b"""<!DOCTYPE html>
<html>
<head>
  <title>Paper</title>
  <link rel="alternate" type="application/atom+xml" href="/atom.xml" title="Atom Feed">
</head>
<body><p>Hello</p></body>
</html>
"""

_ABSOLUTE_RSS_HTML = b"""<!DOCTYPE html>
<html>
<head>
  <link rel="alternate" type="application/rss+xml" href="https://cdn.paper.com/feed.xml">
</head>
<body></body>
</html>
"""

_NO_FEED_HTML = b"""<!DOCTYPE html>
<html>
<head><title>No Feed Here</title></head>
<body><p>Nothing</p></body>
</html>
"""

_MIXED_LINKS_HTML = b"""<!DOCTYPE html>
<html>
<head>
  <link rel="stylesheet" type="text/css" href="/style.css">
  <link rel="icon" href="/favicon.ico">
  <link rel="alternate" type="application/rss+xml" href="/rss.xml">
</head>
<body></body>
</html>
"""


def _fake_fetch(response: bytes):
    """Return a fetch callable that always returns the given bytes."""
    def _fetch(url: str) -> bytes:
        return response
    return _fetch


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_rss_link_returns_absolute_url():
    """Relative RSS href is resolved against base URL."""
    result = discover_feed("https://paper.com/", fetch=_fake_fetch(_RSS_HTML))
    assert result == "https://paper.com/feed.xml"


def test_atom_link_works():
    """Atom+xml type is also accepted."""
    result = discover_feed("https://paper.com/", fetch=_fake_fetch(_ATOM_HTML))
    assert result == "https://paper.com/atom.xml"


def test_relative_href_is_made_absolute():
    """A relative href like /rss.xml is resolved against the base URL."""
    result = discover_feed("https://blog.example.com/", fetch=_fake_fetch(_MIXED_LINKS_HTML))
    assert result == "https://blog.example.com/rss.xml"


def test_absolute_href_is_preserved():
    """An already-absolute href is returned as-is (urljoin keeps it)."""
    result = discover_feed("https://paper.com/", fetch=_fake_fetch(_ABSOLUTE_RSS_HTML))
    assert result == "https://cdn.paper.com/feed.xml"


def test_no_feed_returns_none():
    """HTML with no alternate feed link returns None."""
    result = discover_feed("https://paper.com/", fetch=_fake_fetch(_NO_FEED_HTML))
    assert result is None


def test_non_feed_link_types_ignored():
    """stylesheet/icon links are not returned even if rel=alternate-like."""
    # Page with only non-feed link types
    html = b"""<html><head>
    <link rel="stylesheet" type="text/css" href="/style.css">
    </head><body></body></html>"""
    result = discover_feed("https://paper.com/", fetch=_fake_fetch(html))
    assert result is None


def test_fetch_called_with_given_url():
    """The injected fetch receives exactly the URL passed to discover_feed."""
    called_with = []

    def spy_fetch(url: str) -> bytes:
        called_with.append(url)
        return _NO_FEED_HTML

    discover_feed("https://example.com/page", fetch=spy_fetch)
    assert called_with == ["https://example.com/page"]


def test_ssrf_guard_on_real_fetch():
    """_fetch calls validate_public_url; a private-IP URL raises UnsafeURLError."""
    from app.services.feed_discovery import _fetch as real_fetch
    from app.services.net import UnsafeURLError

    with pytest.raises(UnsafeURLError):
        real_fetch("http://192.168.1.1/feed.xml")
