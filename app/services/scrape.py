from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.core.config import SourceConfig
from app.core.domain import RawItem, SourceType
from app.services.net import validate_public_url

FetchFn = Callable[[str], str]
_HEADERS = {"User-Agent": "CatchUp/0.1 (+https://github.com/AhmedHeshamSakr/Catch-Up)"}


def fetch_page(url: str, *, timeout: float = 10.0) -> str:
    validate_public_url(url)
    resp = httpx.get(url, timeout=timeout, follow_redirects=True, headers=_HEADERS)
    resp.raise_for_status()
    return resp.text


def parse_page(html_text: str, source: SourceConfig) -> list[RawItem]:
    if not source.selector or not source.url:
        return []
    soup = BeautifulSoup(html_text, "html.parser")
    items: list[RawItem] = []
    for el in soup.select(source.selector):
        href = el.get("href")
        title = el.get_text(strip=True)
        if not href or not title:
            continue
        items.append(
            RawItem(
                source_id=source.id,
                source_type=SourceType.SCRAPE,
                source_name=source.name,
                url=urljoin(source.url, href),
                title=title,
                category_hint=source.category_hint,
            )
        )
    return items


def collect(source: SourceConfig, *, fetch: FetchFn = fetch_page) -> list[RawItem]:
    if not source.url:
        return []
    return parse_page(fetch(source.url), source)
