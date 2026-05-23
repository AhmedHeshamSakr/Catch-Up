from __future__ import annotations

import time
from datetime import datetime, timezone

import feedparser
import httpx

from app.core.config import SourceConfig
from app.core.domain import RawItem, SourceType

_HEADERS = {"User-Agent": "CatchUp/0.1 (+https://github.com/AhmedHeshamSakr/Catch-Up)"}


def fetch_feed(url: str, timeout: float = 10.0) -> bytes:
    resp = httpx.get(url, timeout=timeout, follow_redirects=True, headers=_HEADERS)
    resp.raise_for_status()
    return resp.content


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
                time.mktime(entry.published_parsed), tz=timezone.utc
            )
        items.append(
            RawItem(
                source_id=source.id,
                source_type=SourceType.RSS,
                source_name=source.name,
                url=link,
                title=title.strip(),
                excerpt=getattr(entry, "summary", None) or None,
                published_at=published,
                category_hint=source.category_hint,
            )
        )
    return items


def collect(source: SourceConfig) -> list[RawItem]:
    if not source.url:
        return []
    return parse_feed(fetch_feed(source.url), source)
