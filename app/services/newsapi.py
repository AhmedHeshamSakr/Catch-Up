from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

import httpx

from app.core.config import SourceConfig
from app.core.domain import RawItem, SourceType

GNEWS_SEARCH_URL = "https://gnews.io/api/v4/search"
FetchFn = Callable[..., dict]


def fetch_gnews(
    query: str,
    api_key: str,
    *,
    lang: str | None = None,
    country: str | None = None,
    max_articles: int = 10,
    timeout: float = 10.0,
) -> dict:
    params = {"q": query, "apikey": api_key, "max": max_articles}
    if lang:
        params["lang"] = lang
    if country:
        params["country"] = country
    resp = httpx.get(GNEWS_SEARCH_URL, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_gnews(data: dict, source: SourceConfig) -> list[RawItem]:
    items: list[RawItem] = []
    for article in data.get("articles", []):
        title = (article.get("title") or "").strip()
        url = article.get("url")
        if not title or not url:
            continue
        items.append(
            RawItem(
                source_id=source.id,
                source_type=SourceType.API,
                source_name=(article.get("source") or {}).get("name") or source.name,
                url=url,
                title=title,
                excerpt=article.get("description") or None,
                published_at=_parse_dt(article.get("publishedAt")),
                category_hint=source.category_hint,
            )
        )
    return items


def collect(source: SourceConfig, api_key: str, *, fetch: FetchFn = fetch_gnews) -> list[RawItem]:
    if not api_key or not source.query:
        return []
    data = fetch(source.query, api_key, lang=source.lang, country=source.country)
    return parse_gnews(data, source)
