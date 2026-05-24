from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.core.config import SourceConfig
from app.core.domain import RawItem, SourceType
from app.services.net import is_http_url, safe_get

FetchFn = Callable[[str], str]
_HEADERS = {"User-Agent": "CatchUp/0.1 (+https://github.com/AhmedHeshamSakr/Catch-Up)"}


def fetch_page(url: str, *, timeout: float = 10.0) -> str:
    resp = safe_get(url, timeout=timeout, headers=_HEADERS)
    resp.raise_for_status()
    return resp.text


def _extract_og_image(soup: BeautifulSoup) -> str | None:
    """Page-level social image: og:image, falling back to twitter:image.

    Both apply to the whole page, so every item scraped from one page shares it.
    Returns None when absent or not a valid http(s) URL.
    """
    for attrs in ({"property": "og:image"}, {"name": "twitter:image"}):
        meta = soup.find("meta", attrs=attrs)
        if meta:
            content = meta.get("content")
            if is_http_url(content):
                return content
    return None


def parse_page(html_text: str, source: SourceConfig) -> list[RawItem]:
    if not source.selector or not source.url:
        return []
    soup = BeautifulSoup(html_text, "html.parser")
    image_url = _extract_og_image(soup)
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
                image_url=image_url,
                category_hint=source.category_hint,
            )
        )
    return items


def collect(source: SourceConfig, *, fetch: FetchFn = fetch_page) -> list[RawItem]:
    if not source.url:
        return []
    return parse_page(fetch(source.url), source)
