# Plan 4 — Source Breadth (GNews + Scrape) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Add two new collectors — a **GNews** API collector and a **web-scrape** collector — behind a shared **token-bucket rate limiter** and an **SSRF URL guard**, wired into `run_digest`'s per-source dispatch so digests can pull from RSS + API + scraped pages.

**Architecture:** New deterministic services in `app/services/` (`ratelimit.py`, `net.py`, `newsapi.py`, `scrape.py`). Each collector exposes `collect(...)` returning `list[RawItem]` (same contract as `rss.collect`). Network I/O is injectable for offline TDD; live GNews is smoke-validated. `run_digest._collect` dispatches by `SourceType`. Per-source failure isolation (already in `run_digest`) covers new collectors.

**Tech Stack:** httpx (existing) · beautifulsoup4 (scrape, stdlib `html.parser`) · stdlib `ipaddress`/`socket`/`urllib` (SSRF) · existing domain/config.

---

## File structure (this plan)

```
app/services/
├── ratelimit.py   # TokenBucket
├── net.py         # validate_public_url (SSRF guard)
├── newsapi.py     # GNews collector
└── scrape.py      # web-scrape collector
app/core/config.py # + SourceConfig.selector/lang/country, Settings.gnews_api_key
app/runner.py      # _collect dispatch by SourceType
config/sources.yaml# + api/scrape examples (disabled by default)
tests/unit/{test_ratelimit,test_net,test_newsapi,test_scrape}.py
tests/integration/test_run_digest_sources.py
```

---

### Task 1: Token-bucket rate limiter

**Files:** Create `app/services/ratelimit.py`; Test `tests/unit/test_ratelimit.py`.

- [ ] **Step 1: Failing test** — `tests/unit/test_ratelimit.py`:
```python
from app.services.ratelimit import TokenBucket


def test_bucket_allows_up_to_capacity_then_blocks():
    t = {"now": 0.0}
    b = TokenBucket(rate_per_sec=1.0, capacity=3, clock=lambda: t["now"])
    assert b.try_acquire() is True
    assert b.try_acquire() is True
    assert b.try_acquire() is True
    assert b.try_acquire() is False  # capacity exhausted


def test_bucket_refills_over_time():
    t = {"now": 0.0}
    b = TokenBucket(rate_per_sec=2.0, capacity=2, clock=lambda: t["now"])
    assert b.try_acquire(2) is True
    assert b.try_acquire() is False
    t["now"] = 1.0  # 1s * 2 tokens/s = 2 tokens refilled
    assert b.try_acquire() is True
    assert b.try_acquire() is True
    assert b.try_acquire() is False


def test_refill_caps_at_capacity():
    t = {"now": 0.0}
    b = TokenBucket(rate_per_sec=5.0, capacity=2, clock=lambda: t["now"])
    t["now"] = 100.0
    assert b.try_acquire(2) is True
    assert b.try_acquire() is False  # never exceeds capacity
```

- [ ] **Step 2: Run → FAIL** — `uv run pytest tests/unit/test_ratelimit.py -q`.

- [ ] **Step 3: Implement** — `app/services/ratelimit.py`:
```python
from __future__ import annotations

import threading
import time
from collections.abc import Callable


class TokenBucket:
    """Thread-safe token bucket. Inject `clock` for deterministic tests."""

    def __init__(
        self,
        rate_per_sec: float,
        capacity: float,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.rate = rate_per_sec
        self.capacity = capacity
        self._tokens = float(capacity)
        self._clock = clock
        self._last = clock()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = self._clock()
        elapsed = max(0.0, now - self._last)
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
        self._last = now

    def try_acquire(self, tokens: float = 1.0) -> bool:
        with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False
```

- [ ] **Step 4: Run → PASS** — 3 passed.

- [ ] **Step 5: Commit**
```bash
git add app/services/ratelimit.py tests/unit/test_ratelimit.py
git commit -m "feat(net): token-bucket rate limiter"
```

---

### Task 2: SSRF URL guard

**Files:** Create `app/services/net.py`; Test `tests/unit/test_net.py`.

- [ ] **Step 1: Failing test** — `tests/unit/test_net.py`:
```python
import pytest

from app.services.net import UnsafeURLError, validate_public_url


def _resolver(ips):
    return lambda host: ips


def test_rejects_non_http_scheme():
    with pytest.raises(UnsafeURLError):
        validate_public_url("file:///etc/passwd", resolver=_resolver(["1.1.1.1"]))


def test_rejects_missing_host():
    with pytest.raises(UnsafeURLError):
        validate_public_url("http://", resolver=_resolver(["1.1.1.1"]))


def test_rejects_loopback_and_private():
    for ip in ("127.0.0.1", "10.0.0.5", "192.168.1.1", "169.254.1.1"):
        with pytest.raises(UnsafeURLError):
            validate_public_url("http://internal.example", resolver=_resolver([ip]))


def test_allows_public_host():
    assert validate_public_url(
        "https://news.example.com/feed", resolver=_resolver(["93.184.216.34"])
    ) == "https://news.example.com/feed"
```

- [ ] **Step 2: Run → FAIL**.

- [ ] **Step 3: Implement** — `app/services/net.py`:
```python
from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from urllib.parse import urlparse


class UnsafeURLError(ValueError):
    """Raised when a URL is not safe to fetch (bad scheme or non-public address)."""


def _default_resolver(host: str) -> list[str]:
    return [info[4][0] for info in socket.getaddrinfo(host, None)]


def validate_public_url(
    url: str, *, resolver: Callable[[str], list[str]] = _default_resolver
) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError(f"scheme not allowed: {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise UnsafeURLError("missing host")
    try:
        addresses = resolver(host)
    except socket.gaierror as exc:
        raise UnsafeURLError(f"cannot resolve host: {host}") from exc
    for addr in addresses:
        ip = ipaddress.ip_address(addr)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise UnsafeURLError(f"{host} resolves to non-public address {ip}")
    return url
```

- [ ] **Step 4: Run → PASS** — 4 passed.

- [ ] **Step 5: Commit**
```bash
git add app/services/net.py tests/unit/test_net.py
git commit -m "feat(net): SSRF guard (scheme + private-IP rejection)"
```

---

### Task 3: Config fields + GNews collector

**Files:** Modify `app/core/config.py`; Create `app/services/newsapi.py`; Test `tests/unit/test_newsapi.py`.

- [ ] **Step 1: Failing test** — `tests/unit/test_newsapi.py`:
```python
from app.core.config import SourceConfig
from app.core.domain import Category, SourceType
from app.services import newsapi

SAMPLE = {
    "totalArticles": 2,
    "articles": [
        {"title": "AI breakthrough", "description": "desc one",
         "url": "https://news.example/1", "publishedAt": "2026-05-20T09:00:00Z",
         "source": {"name": "Example News"}},
        {"title": "", "description": "no title -> skipped",
         "url": "https://news.example/2", "publishedAt": "2026-05-20T10:00:00Z",
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
```

- [ ] **Step 2: Run → FAIL**.

- [ ] **Step 3: Implement**

Add to `app/core/config.py` `SourceConfig` (after `category_hint`):
```python
    selector: str | None = None   # CSS selector for scrape sources
    lang: str | None = None       # e.g. "en", "ar" (api sources)
    country: str | None = None    # e.g. "qa", "us" (api sources)
```
Add to `Settings` (after `llm_model`):
```python
    gnews_api_key: str = ""
```

`app/services/newsapi.py`:
```python
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
```

- [ ] **Step 4: Run → PASS** — 3 passed.

- [ ] **Step 5: Commit**
```bash
git add app/core/config.py app/services/newsapi.py tests/unit/test_newsapi.py
git commit -m "feat(sources): GNews API collector + source/api config fields"
```

---

### Task 4: Web-scrape collector

**Files:** Modify `pyproject.toml` (add beautifulsoup4); Create `app/services/scrape.py`; Test `tests/unit/test_scrape.py`.

- [ ] **Step 1: Add dependency** — `uv add beautifulsoup4`. Verify: `uv run python -c "import bs4; print(bs4.__version__)"`.

- [ ] **Step 2: Failing test** — `tests/unit/test_scrape.py`:
```python
from app.core.config import SourceConfig
from app.core.domain import Category, SourceType
from app.services import scrape

HTML = """
<html><body>
  <a class="headline" href="/news/1">First Headline</a>
  <a class="headline" href="https://site.example/news/2">Second Headline</a>
  <a class="other" href="/ignore">Ignore me</a>
  <a class="headline" href="/news/3"></a>
</body></html>
"""


def _source():
    return SourceConfig(id="site", type=SourceType.SCRAPE, name="Site",
                        url="https://site.example/news", selector="a.headline",
                        category_hint=Category.BUSINESS_FINANCE)


def test_parse_page_extracts_selected_links_and_resolves_relative():
    items = scrape.parse_page(HTML, _source())
    urls = [i.url for i in items]
    assert urls == ["https://site.example/news/1", "https://site.example/news/2"]
    assert items[0].title == "First Headline"
    assert items[0].source_name == "Site"
    assert items[0].category_hint == Category.BUSINESS_FINANCE


def test_parse_page_empty_without_selector():
    s = _source()
    s.selector = None
    assert scrape.parse_page(HTML, s) == []


def test_collect_uses_injected_fetch():
    items = scrape.collect(_source(), fetch=lambda url: HTML)
    assert len(items) == 2
```

- [ ] **Step 3: Run → FAIL**.

- [ ] **Step 4: Implement** — `app/services/scrape.py`:
```python
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
```

- [ ] **Step 5: Run → PASS** — 3 passed.

- [ ] **Step 6: Commit**
```bash
git add pyproject.toml uv.lock app/services/scrape.py tests/unit/test_scrape.py
git commit -m "feat(sources): web-scrape collector (SSRF-guarded, CSS selector)"
```

---

### Task 5: Wire collectors into `run_digest`

**Files:** Modify `app/runner.py`; Modify `config/sources.yaml`; Test `tests/integration/test_run_digest_sources.py`.

- [ ] **Step 1: Failing test** — `tests/integration/test_run_digest_sources.py`:
```python
from app.core.config import Settings
from app.core.domain import Category, RawItem, RunStatus, SourceType
from app import runner
from app.pipeline.schema import ProcessingResult


def _settings(tmp_path, sources_yaml):
    cfg = tmp_path / "config"; cfg.mkdir()
    (cfg / "sources.yaml").write_text(sources_yaml, encoding="utf-8")
    (cfg / "watchlist.yaml").write_text("entities: []\nkeywords: []\n", encoding="utf-8")
    return Settings(sqlite_path=str(tmp_path / "db.sqlite"),
                    config_dir=str(cfg), output_dir=str(tmp_path / "out"),
                    gnews_api_key="TESTKEY")


def test_dispatch_collects_from_api_and_scrape(tmp_path, monkeypatch):
    yaml = (
        "sources:\n"
        "  - id: g\n    type: api\n    name: GNews\n    query: ai\n    category_hint: ai_tech\n    enabled: true\n"
        "  - id: s\n    type: scrape\n    name: Site\n    url: https://site.example/news\n"
        "    selector: a.headline\n    category_hint: business_finance\n    enabled: true\n"
    )
    settings = _settings(tmp_path, yaml)
    monkeypatch.setattr(runner.newsapi, "collect",
                        lambda source, key, **kw: [RawItem(source_id="g", source_type=SourceType.API,
                            source_name="GNews", url="https://n/1", title="API item",
                            category_hint=Category.AI_TECH)])
    monkeypatch.setattr(runner.scrape, "collect",
                        lambda source, **kw: [RawItem(source_id="s", source_type=SourceType.SCRAPE,
                            source_name="Site", url="https://n/2", title="Scraped item",
                            category_hint=Category.BUSINESS_FINANCE)])
    run = runner.run_digest(settings=settings,
                            processor=lambda items: ProcessingResult(items=[]),
                            narrator=lambda items: "")
    assert run.status == RunStatus.SUCCESS
    assert run.collected == 2  # one from api, one from scrape
```

- [ ] **Step 2: Run → FAIL** — `_collect` doesn't dispatch api/scrape (and `runner.newsapi`/`runner.scrape` not imported).

- [ ] **Step 3: Implement** — in `app/runner.py`:

Update imports:
```python
from app.services import newsapi, normalize, rss, scrape
```
Replace `_collect` and its call site:
```python
def _collect(source: SourceConfig, settings: Settings) -> list[RawItem]:
    if source.type == SourceType.RSS:
        return rss.collect(source)
    if source.type == SourceType.API:
        return newsapi.collect(source, settings.gnews_api_key)
    if source.type == SourceType.SCRAPE:
        return scrape.collect(source)
    return []  # SEARCH grounding arrives in Plan 5
```
In `run_digest`, change the collection call to pass settings:
```python
                raws.extend(_collect(source, settings))
```

- [ ] **Step 4: Add example sources** — append to `config/sources.yaml` (disabled by default so live runs don't fail without keys/selectors):
```yaml
  - id: gnews_ai
    type: api
    name: GNews — AI
    query: artificial intelligence
    lang: en
    category_hint: ai_tech
    enabled: false
  - id: gnews_gulf
    type: api
    name: GNews — Gulf
    query: Qatar OR Gulf economy
    lang: en
    country: qa
    category_hint: gulf_mena
    enabled: false
  # Example scrape source — set a real selector before enabling.
  - id: example_scrape
    type: scrape
    name: Example Announcements
    url: https://example.com/news
    selector: a.headline
    category_hint: business_finance
    enabled: false
```

- [ ] **Step 5: Run → PASS + full suite + lint**
`uv run pytest tests -q` (all green) and `uv run --extra lint ruff check app tests scripts` (clean).

- [ ] **Step 6: Commit**
```bash
git add app/runner.py config/sources.yaml tests/integration/test_run_digest_sources.py
git commit -m "feat(sources): dispatch RSS/API/scrape in run_digest + example sources"
```

---

### Task 6: Live smoke + docs

**Files:** Modify `README.md`.

- [ ] **Step 1: GNews key** — ensure `GNEWS_API_KEY` is set (env or `.env`, gitignored). If absent, report NEEDS_CONTEXT — do not commit a key. (Settings field is `gnews_api_key`; pydantic-settings reads `GNEWS_API_KEY` from `.env`/env case-insensitively.)

- [ ] **Step 2: Live smoke** — temporarily enable a GNews source (e.g. `gnews_ai`) in `config/sources.yaml` (or a temp copy), run `uv run python -m app.cli run` with both `GOOGLE_API_KEY` and `GNEWS_API_KEY` set, and confirm API-sourced items appear in the digest. Revert the `enabled: true` change after (keep examples disabled by default). Report what was collected.

- [ ] **Step 3: README** — under "Running locally", document `GNEWS_API_KEY` and that sources support `type: rss | api | scrape` (with `selector` for scrape, `lang`/`country` for api).

- [ ] **Step 4: Commit**
```bash
git add README.md
git commit -m "docs(sources): GNews key + source types in README"
```

---

## Self-Review (completed)

- **Spec coverage:** news-API source §8 (GNews) ✓; web-scrape source §8 ✓; rate limiting §14 (TokenBucket) ✓; SSRF protection §15 ✓; per-source isolation §13 (existing, now covers new collectors) ✓; config-driven sources §18 ✓. Search grounding §8 + async migration → Plan 5 (documented).
- **Placeholder scan:** none — full code; live smoke concrete.
- **Type consistency:** every `collect(...)` returns `list[RawItem]`; `_collect(source, settings)` dispatch matches; `SourceConfig` gains `selector`/`lang`/`country`; `Settings.gnews_api_key` referenced consistently.

## Notes for executor
- TokenBucket is delivered + unit-tested; it is used by collectors in a later hardening pass (kept out of the hot path here to stay simple) — do NOT block on wiring it into every collector.
- Run Python via `uv`; lint via `uv run --extra lint ruff check app tests scripts`. Append a BUILD-LOG entry per task. Commit identity AhmedHeshamSakr, **no AI trailers**. Live smoke needs `GNEWS_API_KEY` (+ `GOOGLE_API_KEY` for enrichment); if absent, report NEEDS_CONTEXT — never commit a key.
