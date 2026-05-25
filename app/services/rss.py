from __future__ import annotations

import calendar
from datetime import UTC, datetime

import feedparser

from app.core.config import SourceConfig
from app.core.domain import RawItem, SourceType
from app.services.net import is_http_url, safe_get

_HEADERS = {"User-Agent": "CatchUp/0.1 (+https://github.com/AhmedHeshamSakr/Catch-Up)"}


def fetch_feed(url: str, timeout: float = 10.0) -> bytes:
    resp = safe_get(url, timeout=timeout, headers=_HEADERS)
    resp.raise_for_status()
    return resp.content


def _extract_image_url(entry) -> str | None:
    """First valid http(s) image among media:thumbnail, media:content, enclosures.

    feedparser surfaces the mediarss extension as media_thumbnail / media_content
    (lists of dicts with a ``url`` key) and image enclosures via
    enclosures/links (dicts with an image ``type`` and an ``href``/``url``).
    Returns None when no valid http(s) candidate is present.
    """
    for thumb in entry.get("media_thumbnail") or []:
        url = thumb.get("url")
        if is_http_url(url):
            return url
    for content in entry.get("media_content") or []:
        ctype = (content.get("type") or "")
        url = content.get("url")
        if ctype.startswith("image") and is_http_url(url):
            return url
    for enc in (entry.get("enclosures") or []) + (entry.get("links") or []):
        if (enc.get("type") or "").startswith("image/"):
            url = enc.get("href") or enc.get("url")
            if is_http_url(url):
                return url
    return None


def parse_feed(content: bytes, source: SourceConfig) -> list[RawItem]:
    parsed = feedparser.parse(content)
    items: list[RawItem] = []
    for entry in parsed.entries:
        link = getattr(entry, "link", None)
        title = getattr(entry, "title", None)
        if not link or not title:
            continue
        published: datetime | None = None
        if getattr(entry, "published_parsed", None):
            published = datetime.fromtimestamp(
                calendar.timegm(entry.published_parsed), tz=UTC
            )
        items.append(
            RawItem(
                source_id=source.id,
                source_type=SourceType.RSS,
                source_name=source.name,
                url=link,
                title=title.strip(),
                excerpt=getattr(entry, "summary", None) or None,
                image_url=_extract_image_url(entry),
                published_at=published,
                category_hint=source.category_hint,
            )
        )
    return items


def collect(source: SourceConfig) -> list[RawItem]:
    if not source.url:
        return []
    return parse_feed(fetch_feed(source.url), source)
