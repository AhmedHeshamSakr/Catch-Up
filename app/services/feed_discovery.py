from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.services.net import safe_get

_HEADERS = {"User-Agent": "CatchUp/0.1 (+https://github.com/AhmedHeshamSakr/Catch-Up)"}

_FEED_TYPES = {"application/rss+xml", "application/atom+xml"}


def _fetch(url: str) -> bytes:
    resp = safe_get(url, timeout=10.0, headers=_HEADERS)  # SSRF guard (per-hop)
    resp.raise_for_status()
    return resp.content


def discover_feed(url: str, *, fetch: Callable[[str], bytes] = _fetch) -> str | None:
    """Find an RSS/Atom feed link in a page's HTML. Returns an absolute feed URL or None.

    Searches for ``<link rel="alternate" type="application/rss+xml">`` and
    ``<link rel="alternate" type="application/atom+xml">`` tags.  BeautifulSoup
    stores the ``rel`` attribute as a list, so we iterate all ``<link>`` tags and
    check ``"alternate" in (link.get("rel") or [])`` rather than relying on the
    ``find_all(rel="alternate")`` keyword argument, which can silently miss tags
    depending on the parser.
    """
    html = fetch(url)
    soup = BeautifulSoup(html, "html.parser")
    for link in soup.find_all("link"):
        rel = link.get("rel") or []
        # rel is stored as a list by BeautifulSoup
        if "alternate" not in rel:
            continue
        t = (link.get("type") or "").lower()
        href = link.get("href")
        if href and t in _FEED_TYPES:
            return urljoin(url, href)
    return None
