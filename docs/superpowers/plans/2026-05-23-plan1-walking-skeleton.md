# Plan 1 — Walking Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up an end-to-end ADK project that collects RSS news, normalizes + dedups it, stores it in SQLite, and renders a real Markdown digest via a `run_digest()` job and a CLI — no LLM yet.

**Architecture:** Hexagonal core under the agents-cli `app/` package. Plain, independently-testable Python services (RSS, normalize, render) orchestrated by `run_digest()`. Storage is behind a `StorageBackend` port with a SQLite adapter (Firestore later). The ADK `SequentialAgent`/`ParallelAgent` wrapping and LLM stages come in later plans; this plan delivers a deterministic, fully-working vertical slice.

**Tech Stack:** Python 3.11+ · google-adk · pydantic / pydantic-settings · feedparser · httpx · PyYAML · sqlite3 (stdlib) · pytest · uv · ruff.

---

## Repo Layout (target after Task 0)

```
<repo root>/
├── app/
│   ├── __init__.py              # scaffolded — exports `app`
│   ├── agent.py                 # scaffolded demo — PRESERVED (evolves in Plan 4)
│   ├── app_utils/               # scaffolded telemetry/typing
│   ├── fast_api_app.py          # scaffolded — used in Plan 4
│   ├── core/
│   │   ├── __init__.py
│   │   ├── domain.py            # enums, Entity, RawItem, NewsItem, DigestRun, make_item_id
│   │   ├── config.py            # Settings, SourceConfig, load_sources()
│   │   └── ports/
│   │       ├── __init__.py
│   │       └── storage.py       # StorageBackend (ABC)
│   ├── adapters/
│   │   ├── __init__.py
│   │   └── storage/
│   │       ├── __init__.py
│   │       └── sqlite_backend.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── rss.py
│   │   ├── normalize.py
│   │   └── render/
│   │       ├── __init__.py
│   │       └── markdown.py
│   ├── runner.py                # run_digest()
│   └── cli.py                   # `python -m app.cli run`
├── config/
│   ├── sources.yaml             # seed RSS sources
│   └── watchlist.yaml           # placeholder for Plan 2
├── tests/
│   ├── unit/{test_domain,test_config,storage_contract,test_sqlite_backend,test_rss,test_normalize,test_markdown}.py
│   └── integration/test_run_digest.py
├── pyproject.toml  Dockerfile  agents-cli-manifest.yaml  CLAUDE.md  README.md  .gitignore  docs/
```

---

### Task 0: Scaffold the ADK project and relocate to repo root

**Files:**
- Create (via CLI, into `/tmp` then move): `app/`, `tests/`, `pyproject.toml`, `Dockerfile`, `agents-cli-manifest.yaml`, `CLAUDE.md`
- Keep ours: `README.md`, `.gitignore`, `docs/`
- Delete: scaffolded demo tests that target the weather agent / need GCP

- [ ] **Step 1: Scaffold into a temp dir**

Run:
```bash
rm -rf /tmp/catchup-build
agents-cli scaffold create catch-up -o /tmp -a adk --prototype -k -s -y --agent-guidance-filename CLAUDE.md
```
Expected: `✅ Success! Your agent project is ready.` at `/tmp/catch-up`.

- [ ] **Step 2: Relocate into the repo root (preserve our README/.gitignore/docs)**

Run (from repo root):
```bash
cp -R /tmp/catch-up/app ./app
cp -R /tmp/catch-up/tests ./tests
cp /tmp/catch-up/pyproject.toml ./pyproject.toml
cp /tmp/catch-up/Dockerfile ./Dockerfile
cp /tmp/catch-up/agents-cli-manifest.yaml ./agents-cli-manifest.yaml
cp /tmp/catch-up/CLAUDE.md ./CLAUDE.md
rm -rf /tmp/catch-up
```

- [ ] **Step 3: Remove scaffolded demo tests (weather agent / GCP-coupled)**

Run:
```bash
rm -f tests/unit/test_dummy.py tests/integration/test_agent.py tests/integration/test_server_e2e.py
```
Rationale: these target the demo `root_agent` and `fast_api_app` (which needs GCP ADC at import). Real tests replace them. `tests/eval/` is kept for Plan 2.

- [ ] **Step 4: Set project identity in pyproject.toml**

In `pyproject.toml`, change:
```toml
name = "catch-up"
version = "0.1.0"
description = ""
authors = [
    {name = "Your Name", email = "your@email.com"},
]
```
to:
```toml
name = "catch-up"
version = "0.1.0"
description = "Multi-agent news monitoring & catch-up platform on Google ADK"
authors = [
    {name = "Ahmed Hesham", email = "a.hesham1221@gmail.com"},
]
```

- [ ] **Step 5: Install dependencies**

Run: `uv sync`
Expected: resolves google-adk + dev deps, creates `.venv` and `uv.lock`. (Uses Python 3.11–3.13 via uv.)

- [ ] **Step 6: Verify the harness runs (collect-only, no failures from missing tests)**

Run: `uv run pytest tests -q`
Expected: `no tests ran` (or 0 failures). This confirms pytest + imports work.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "chore: scaffold ADK project at repo root (prototype, AI Studio)"
```

---

### Task 1: Add project dependencies

**Files:**
- Modify: `pyproject.toml` (via `uv add`)

- [ ] **Step 1: Add runtime deps**

Run: `uv add feedparser httpx pyyaml pydantic-settings`
Expected: deps appended to `[project.dependencies]`, `uv.lock` updated, installed.

- [ ] **Step 2: Verify imports resolve**

Run: `uv run python -c "import feedparser, httpx, yaml, pydantic_settings; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "build: add feedparser, httpx, pyyaml, pydantic-settings"
```

---

### Task 2: Domain model

**Files:**
- Create: `app/core/__init__.py` (empty), `app/core/domain.py`
- Test: `tests/unit/test_domain.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/test_domain.py`:
```python
from app.core.domain import (
    Category, NewsItem, RawItem, SourceType, make_item_id,
)


def test_make_item_id_is_stable_and_url_normalized():
    assert make_item_id("https://A.com/x ") == make_item_id("https://a.com/x")
    assert len(make_item_id("https://a.com/x")) == 16


def test_newsitem_from_raw_sets_id_category_and_status():
    raw = RawItem(
        source_id="tc", source_type=SourceType.RSS, source_name="TechCrunch",
        url="https://x.com/a", title="Hello", category_hint=Category.AI_TECH,
    )
    item = NewsItem.from_raw(raw, run_id="r1")
    assert item.id == make_item_id("https://x.com/a")
    assert item.category == Category.AI_TECH
    assert item.status == "raw"
    assert item.digest_run_id == "r1"
    assert item.org_id == "default"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_domain.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.domain'`

- [ ] **Step 3: Write minimal implementation**

`app/core/__init__.py`: (empty file)

`app/core/domain.py`:
```python
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

DEFAULT_ORG = "default"
DEFAULT_USER = "default"


class SourceType(str, Enum):
    RSS = "rss"
    SCRAPE = "scrape"
    API = "api"
    SEARCH = "search"


class Category(str, Enum):
    AI_TECH = "ai_tech"
    BUSINESS_FINANCE = "business_finance"
    WORLD_GEOPOLITICS = "world_geopolitics"
    GULF_MENA = "gulf_mena"


class Importance(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Sentiment(str, Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class RunStatus(str, Enum):
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


def make_item_id(url: str) -> str:
    return hashlib.sha256(url.strip().lower().encode("utf-8")).hexdigest()[:16]


class Entity(BaseModel):
    name: str
    type: str = "org"


class RawItem(BaseModel):
    source_id: str
    source_type: SourceType
    source_name: str
    url: str
    title: str
    excerpt: str | None = None
    published_at: datetime | None = None
    category_hint: Category | None = None


class NewsItem(BaseModel):
    id: str
    org_id: str = DEFAULT_ORG
    user_id: str = DEFAULT_USER
    source_id: str
    source_type: SourceType
    source_name: str
    url: str
    title: str
    excerpt: str | None = None
    published_at: datetime | None = None
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    category: Category | None = None
    summary_en: str | None = None
    summary_ar: str | None = None
    importance: Importance | None = None
    importance_score: float | None = None
    entities: list[Entity] = Field(default_factory=list)
    sentiment: Sentiment | None = None
    language: str | None = None
    status: str = "raw"
    digest_run_id: str | None = None

    @classmethod
    def from_raw(cls, raw: RawItem, run_id: str | None = None) -> "NewsItem":
        return cls(
            id=make_item_id(raw.url),
            source_id=raw.source_id,
            source_type=raw.source_type,
            source_name=raw.source_name,
            url=raw.url,
            title=raw.title,
            excerpt=raw.excerpt,
            published_at=raw.published_at,
            category=raw.category_hint,
            digest_run_id=run_id,
        )


class DigestRun(BaseModel):
    run_id: str
    org_id: str = DEFAULT_ORG
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    status: RunStatus = RunStatus.RUNNING
    collected: int = 0
    new: int = 0
    processed: int = 0
    high_importance: int = 0
    outputs: dict[str, str] = Field(default_factory=dict)
    source_errors: list[dict] = Field(default_factory=list)
    narrative: str | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_domain.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add app/core/__init__.py app/core/domain.py tests/unit/test_domain.py
git commit -m "feat(core): domain model (NewsItem, RawItem, DigestRun, enums)"
```

---

### Task 3: Settings and source config loader

**Files:**
- Create: `app/core/config.py`, `config/sources.yaml`, `config/watchlist.yaml`
- Test: `tests/unit/test_config.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/test_config.py`:
```python
from app.core.config import SourceConfig, load_sources
from app.core.domain import Category, SourceType


def test_load_sources_parses_yaml(tmp_path):
    (tmp_path / "sources.yaml").write_text(
        "sources:\n"
        "  - id: techcrunch\n"
        "    type: rss\n"
        "    name: TechCrunch\n"
        "    url: https://techcrunch.com/feed/\n"
        "    category_hint: ai_tech\n"
        "    enabled: true\n",
        encoding="utf-8",
    )
    sources = load_sources(tmp_path)
    assert len(sources) == 1
    s = sources[0]
    assert isinstance(s, SourceConfig)
    assert s.id == "techcrunch"
    assert s.type == SourceType.RSS
    assert s.category_hint == Category.AI_TECH
    assert s.enabled is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_config.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.config'`

- [ ] **Step 3: Write minimal implementation**

`app/core/config.py`:
```python
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.domain import Category, SourceType

REPO_ROOT = Path(__file__).resolve().parents[2]


class SourceConfig(BaseModel):
    id: str
    type: SourceType
    name: str
    url: str | None = None
    query: str | None = None
    category_hint: Category | None = None
    enabled: bool = True


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    google_api_key: str = ""
    storage_backend: str = "sqlite"
    sqlite_path: str = str(REPO_ROOT / "data" / "catchup.db")
    config_dir: str = str(REPO_ROOT / "config")
    output_dir: str = str(REPO_ROOT / "output")


def load_sources(config_dir: str | Path) -> list[SourceConfig]:
    path = Path(config_dir) / "sources.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [SourceConfig(**raw) for raw in data.get("sources", [])]
```

`config/sources.yaml` (seed defaults — Ahmed will curate later):
```yaml
# Seed sources. Replace with your curated list anytime.
sources:
  - id: techcrunch
    type: rss
    name: TechCrunch
    url: https://techcrunch.com/feed/
    category_hint: ai_tech
    enabled: true
  - id: the_verge
    type: rss
    name: The Verge
    url: https://www.theverge.com/rss/index.xml
    category_hint: ai_tech
    enabled: true
  - id: ft_companies
    type: rss
    name: Financial Times — Companies
    url: https://www.ft.com/companies?format=rss
    category_hint: business_finance
    enabled: true
  - id: aljazeera_all
    type: rss
    name: Al Jazeera
    url: https://www.aljazeera.com/xml/rss/all.xml
    category_hint: world_geopolitics
    enabled: true
  - id: arab_news
    type: rss
    name: Arab News
    url: https://www.arabnews.com/rss.xml
    category_hint: gulf_mena
    enabled: true
```

`config/watchlist.yaml`:
```yaml
# Entities/keywords that boost importance (used from Plan 2).
entities: []
keywords: []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_config.py -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add app/core/config.py config/sources.yaml config/watchlist.yaml tests/unit/test_config.py
git commit -m "feat(core): Settings + source config loader and seed sources"
```

---

### Task 4: Storage port + reusable contract test

**Files:**
- Create: `app/core/ports/__init__.py` (empty), `app/core/ports/storage.py`
- Create: `tests/unit/storage_contract.py` (reused by SQLite now, Firestore in Plan 6)

- [ ] **Step 1: Write the storage port (interface)**

`app/core/ports/__init__.py`: (empty file)

`app/core/ports/storage.py`:
```python
from __future__ import annotations

from abc import ABC, abstractmethod

from app.core.domain import DigestRun, NewsItem


class StorageBackend(ABC):
    """Persistence port. Adapters: SQLite (v1), Firestore (prod)."""

    @abstractmethod
    def init_schema(self) -> None: ...

    @abstractmethod
    def existing_ids(self, ids: list[str]) -> set[str]: ...

    @abstractmethod
    def save_items(self, items: list[NewsItem]) -> None: ...

    @abstractmethod
    def get_items_for_run(self, run_id: str) -> list[NewsItem]: ...

    @abstractmethod
    def create_run(self, run: DigestRun) -> None: ...

    @abstractmethod
    def finalize_run(self, run: DigestRun) -> None: ...

    @abstractmethod
    def get_run(self, run_id: str) -> DigestRun | None: ...
```

- [ ] **Step 2: Write the reusable contract test**

`tests/unit/storage_contract.py`:
```python
from datetime import datetime, timezone

from app.core.domain import (
    Category, DigestRun, NewsItem, RawItem, RunStatus, SourceType,
)


class StorageContract:
    """Reusable contract. Subclasses set self.backend (fresh, schema-inited)."""

    backend = None  # set by subclass fixture

    def _item(self, url: str = "https://x.com/a", title: str = "t") -> NewsItem:
        raw = RawItem(
            source_id="s", source_type=SourceType.RSS, source_name="S",
            url=url, title=title, category_hint=Category.AI_TECH,
        )
        return NewsItem.from_raw(raw, run_id="r1")

    def test_save_and_get_items_for_run(self):
        self.backend.save_items([self._item()])
        items = self.backend.get_items_for_run("r1")
        assert len(items) == 1
        assert items[0].url == "https://x.com/a"

    def test_existing_ids_detects_only_saved(self):
        item = self._item()
        self.backend.save_items([item])
        assert self.backend.existing_ids([item.id, "missing"]) == {item.id}

    def test_existing_ids_empty_input(self):
        assert self.backend.existing_ids([]) == set()

    def test_create_and_finalize_run_roundtrip(self):
        run = DigestRun(run_id="r1")
        self.backend.create_run(run)
        run.status = RunStatus.SUCCESS
        run.finished_at = datetime.now(timezone.utc)
        run.collected = 5
        self.backend.finalize_run(run)
        got = self.backend.get_run("r1")
        assert got is not None
        assert got.status == RunStatus.SUCCESS
        assert got.collected == 5

    def test_get_missing_run_returns_none(self):
        assert self.backend.get_run("nope") is None
```

- [ ] **Step 3: Commit (no behavior to run yet)**

```bash
git add app/core/ports/__init__.py app/core/ports/storage.py tests/unit/storage_contract.py
git commit -m "feat(core): StorageBackend port + reusable contract tests"
```

---

### Task 5: SQLite storage adapter

**Files:**
- Create: `app/adapters/__init__.py` (empty), `app/adapters/storage/__init__.py` (empty), `app/adapters/storage/sqlite_backend.py`
- Test: `tests/unit/test_sqlite_backend.py`

- [ ] **Step 1: Write the failing test (binds SQLite to the contract)**

`tests/unit/test_sqlite_backend.py`:
```python
import pytest

from app.adapters.storage.sqlite_backend import SqliteBackend
from tests.unit.storage_contract import StorageContract


class TestSqliteBackend(StorageContract):
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        self.backend = SqliteBackend(str(tmp_path / "t.db"))
        self.backend.init_schema()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_sqlite_backend.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.adapters.storage.sqlite_backend'`

- [ ] **Step 3: Write minimal implementation**

`app/adapters/__init__.py`: (empty)
`app/adapters/storage/__init__.py`: (empty)

`app/adapters/storage/sqlite_backend.py`:
```python
from __future__ import annotations

import sqlite3
from pathlib import Path

from app.core.domain import DigestRun, NewsItem
from app.core.ports.storage import StorageBackend


class SqliteBackend(StorageBackend):
    def __init__(self, path: str) -> None:
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_schema(self) -> None:
        with self._conn() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS news_items ("
                "id TEXT PRIMARY KEY, run_id TEXT, org_id TEXT, data TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS digest_runs ("
                "run_id TEXT PRIMARY KEY, org_id TEXT, status TEXT, data TEXT NOT NULL)"
            )

    def existing_ids(self, ids: list[str]) -> set[str]:
        if not ids:
            return set()
        placeholders = ",".join("?" * len(ids))
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT id FROM news_items WHERE id IN ({placeholders})", ids
            ).fetchall()
        return {row["id"] for row in rows}

    def save_items(self, items: list[NewsItem]) -> None:
        with self._conn() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO news_items (id, run_id, org_id, data) "
                "VALUES (?, ?, ?, ?)",
                [(i.id, i.digest_run_id, i.org_id, i.model_dump_json()) for i in items],
            )

    def get_items_for_run(self, run_id: str) -> list[NewsItem]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT data FROM news_items WHERE run_id = ?", (run_id,)
            ).fetchall()
        return [NewsItem.model_validate_json(row["data"]) for row in rows]

    def create_run(self, run: DigestRun) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO digest_runs (run_id, org_id, status, data) "
                "VALUES (?, ?, ?, ?)",
                (run.run_id, run.org_id, run.status.value, run.model_dump_json()),
            )

    def finalize_run(self, run: DigestRun) -> None:
        self.create_run(run)

    def get_run(self, run_id: str) -> DigestRun | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT data FROM digest_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        return DigestRun.model_validate_json(row["data"]) if row else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_sqlite_backend.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add app/adapters tests/unit/test_sqlite_backend.py
git commit -m "feat(storage): SQLite adapter passing the storage contract"
```

---

### Task 6: RSS collector service

**Files:**
- Create: `app/services/__init__.py` (empty), `app/services/rss.py`
- Test: `tests/unit/test_rss.py`

- [ ] **Step 1: Write the failing test (parse a fixture feed — no network)**

`tests/unit/test_rss.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_rss.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services'` / `app.services.rss`

- [ ] **Step 3: Write minimal implementation**

`app/services/__init__.py`: (empty)

`app/services/rss.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_rss.py -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add app/services/__init__.py app/services/rss.py tests/unit/test_rss.py
git commit -m "feat(services): RSS collector (fetch + parse)"
```

---

### Task 7: Normalize + dedup

**Files:**
- Create: `app/services/normalize.py`
- Test: `tests/unit/test_normalize.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/test_normalize.py`:
```python
import pytest

from app.adapters.storage.sqlite_backend import SqliteBackend
from app.core.domain import Category, NewsItem, RawItem, SourceType
from app.services import normalize


@pytest.fixture
def storage(tmp_path):
    backend = SqliteBackend(str(tmp_path / "t.db"))
    backend.init_schema()
    return backend


def _raw(url: str, title: str) -> RawItem:
    return RawItem(
        source_id="s", source_type=SourceType.RSS, source_name="S",
        url=url, title=title, category_hint=Category.AI_TECH,
    )


def test_dedups_within_batch_by_url_and_title(storage):
    raws = [
        _raw("https://a.com/1", "Same Title"),
        _raw("https://a.com/1", "Same Title"),           # dup url
        _raw("https://a.com/2", "same   title"),          # dup title (normalized)
        _raw("https://a.com/3", "Different"),
    ]
    out = normalize.normalize_and_dedup(raws, storage, run_id="r1")
    urls = {i.url for i in out}
    assert urls == {"https://a.com/1", "https://a.com/3"}


def test_filters_items_already_in_storage(storage):
    existing = NewsItem.from_raw(_raw("https://a.com/1", "Old"), run_id="r0")
    storage.save_items([existing])
    out = normalize.normalize_and_dedup(
        [_raw("https://a.com/1", "Old"), _raw("https://a.com/9", "New")],
        storage, run_id="r1",
    )
    assert [i.url for i in out] == ["https://a.com/9"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_normalize.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.normalize'`

- [ ] **Step 3: Write minimal implementation**

`app/services/normalize.py`:
```python
from __future__ import annotations

from app.core.domain import NewsItem, RawItem
from app.core.ports.storage import StorageBackend


def _norm_title(title: str) -> str:
    return " ".join(title.lower().split())


def normalize_and_dedup(
    raws: list[RawItem], storage: StorageBackend, run_id: str
) -> list[NewsItem]:
    seen_ids: set[str] = set()
    seen_titles: set[str] = set()
    candidates: list[NewsItem] = []
    for raw in raws:
        item = NewsItem.from_raw(raw, run_id=run_id)
        title_key = _norm_title(raw.title)
        if item.id in seen_ids or title_key in seen_titles:
            continue
        seen_ids.add(item.id)
        seen_titles.add(title_key)
        candidates.append(item)
    already = storage.existing_ids([c.id for c in candidates])
    return [c for c in candidates if c.id not in already]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_normalize.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add app/services/normalize.py tests/unit/test_normalize.py
git commit -m "feat(services): normalize raw items + dedup (batch + storage)"
```

---

### Task 8: Markdown renderer

**Files:**
- Create: `app/services/render/__init__.py` (empty), `app/services/render/markdown.py`
- Test: `tests/unit/test_markdown.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/test_markdown.py`:
```python
from app.core.domain import Category, DigestRun, NewsItem, RawItem, SourceType
from app.services.render import markdown


def _item(title: str, url: str, cat: Category) -> NewsItem:
    raw = RawItem(
        source_id="s", source_type=SourceType.RSS, source_name="Src",
        url=url, title=title, category_hint=cat,
    )
    return NewsItem.from_raw(raw, run_id="r1")


def test_render_markdown_groups_by_category():
    run = DigestRun(run_id="r1")
    items = [
        _item("AI thing", "https://a.com/1", Category.AI_TECH),
        _item("Gulf thing", "https://a.com/2", Category.GULF_MENA),
    ]
    out = markdown.render_markdown(run, items)
    assert "# News Catch-Up" in out
    assert "## AI & Technology" in out
    assert "## Gulf & MENA" in out
    assert "[AI thing](https://a.com/1)" in out
    assert "Src" in out


def test_write_markdown_creates_file(tmp_path):
    run = DigestRun(run_id="rX")
    path = markdown.write_markdown(run, [_item("t", "https://a.com/9", Category.AI_TECH)], str(tmp_path))
    assert path.endswith("digest-rX.md")
    from pathlib import Path
    assert "AI & Technology" in Path(path).read_text(encoding="utf-8")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_markdown.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.render'`

- [ ] **Step 3: Write minimal implementation**

`app/services/render/__init__.py`: (empty)

`app/services/render/markdown.py`:
```python
from __future__ import annotations

from pathlib import Path

from app.core.domain import Category, DigestRun, NewsItem

CATEGORY_TITLES: dict[Category, str] = {
    Category.AI_TECH: "AI & Technology",
    Category.BUSINESS_FINANCE: "Business & Finance",
    Category.WORLD_GEOPOLITICS: "World & Geopolitics",
    Category.GULF_MENA: "Gulf & MENA",
}


def render_markdown(run: DigestRun, items: list[NewsItem]) -> str:
    n_categories = len({i.category for i in items if i.category})
    lines: list[str] = [
        f"# News Catch-Up — {run.started_at:%Y-%m-%d %H:%M UTC}",
        "",
        f"*{len(items)} items across {n_categories} categories.*",
        "",
    ]
    grouped: dict[Category | None, list[NewsItem]] = {}
    for item in items:
        grouped.setdefault(item.category, []).append(item)

    ordered_keys: list[Category | None] = list(CATEGORY_TITLES.keys()) + [None]
    for cat in ordered_keys:
        group = grouped.get(cat)
        if not group:
            continue
        lines.append(f"## {CATEGORY_TITLES.get(cat, 'Uncategorized')}")
        lines.append("")
        for item in group:
            lines.append(f"- [{item.title}]({item.url}) — *{item.source_name}*")
        lines.append("")
    return "\n".join(lines)


def write_markdown(run: DigestRun, items: list[NewsItem], output_dir: str) -> str:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"digest-{run.run_id}.md"
    path.write_text(render_markdown(run, items), encoding="utf-8")
    return str(path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_markdown.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add app/services/render tests/unit/test_markdown.py
git commit -m "feat(render): Markdown digest renderer grouped by category"
```

---

### Task 9: `run_digest()` orchestrator

**Files:**
- Create: `app/runner.py`
- Test: `tests/integration/test_run_digest.py`

- [ ] **Step 1: Write the failing test (monkeypatch RSS — no network)**

`tests/integration/test_run_digest.py`:
```python
from app.adapters.storage.sqlite_backend import SqliteBackend
from app.core.config import Settings
from app.core.domain import Category, RawItem, RunStatus, SourceType
from app import runner


def _raw(url: str, title: str) -> RawItem:
    return RawItem(
        source_id="techcrunch", source_type=SourceType.RSS, source_name="TechCrunch",
        url=url, title=title, category_hint=Category.AI_TECH,
    )


def test_run_digest_end_to_end(tmp_path, monkeypatch):
    # Config dir with a single enabled RSS source
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "sources.yaml").write_text(
        "sources:\n"
        "  - id: techcrunch\n    type: rss\n    name: TechCrunch\n"
        "    url: https://demo/feed\n    category_hint: ai_tech\n    enabled: true\n",
        encoding="utf-8",
    )
    settings = Settings(
        sqlite_path=str(tmp_path / "db.sqlite"),
        config_dir=str(config_dir),
        output_dir=str(tmp_path / "out"),
    )

    monkeypatch.setattr(
        runner.rss, "collect",
        lambda source: [_raw("https://x.com/1", "A"), _raw("https://x.com/2", "B")],
    )

    run = runner.run_digest(settings=settings)

    assert run.status == RunStatus.SUCCESS
    assert run.collected == 2
    assert run.new == 2
    assert run.outputs["md"].endswith(f"digest-{run.run_id}.md")

    from pathlib import Path
    assert Path(run.outputs["md"]).exists()

    storage = SqliteBackend(settings.sqlite_path)
    assert len(storage.get_items_for_run(run.run_id)) == 2
    assert storage.get_run(run.run_id).status == RunStatus.SUCCESS


def test_run_digest_isolates_source_failure(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "sources.yaml").write_text(
        "sources:\n"
        "  - id: techcrunch\n    type: rss\n    name: TechCrunch\n"
        "    url: https://demo/feed\n    category_hint: ai_tech\n    enabled: true\n",
        encoding="utf-8",
    )
    settings = Settings(
        sqlite_path=str(tmp_path / "db.sqlite"),
        config_dir=str(config_dir),
        output_dir=str(tmp_path / "out"),
    )

    def boom(source):
        raise RuntimeError("feed down")

    monkeypatch.setattr(runner.rss, "collect", boom)
    run = runner.run_digest(settings=settings)

    assert run.status == RunStatus.PARTIAL
    assert run.collected == 0
    assert len(run.source_errors) == 1
    assert run.source_errors[0]["source_id"] == "techcrunch"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_run_digest.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.runner'`

- [ ] **Step 3: Write minimal implementation**

`app/runner.py`:
```python
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.adapters.storage.sqlite_backend import SqliteBackend
from app.core.config import Settings, SourceConfig, load_sources
from app.core.domain import DigestRun, RawItem, RunStatus, SourceType
from app.core.ports.storage import StorageBackend
from app.services import normalize, rss
from app.services.render import markdown


def build_storage(settings: Settings) -> StorageBackend:
    backend = SqliteBackend(settings.sqlite_path)
    backend.init_schema()
    return backend


def _collect(source: SourceConfig) -> list[RawItem]:
    if source.type == SourceType.RSS:
        return rss.collect(source)
    return []  # SCRAPE / API / SEARCH arrive in Plan 3


def run_digest(
    settings: Settings | None = None, storage: StorageBackend | None = None
) -> DigestRun:
    settings = settings or Settings()
    storage = storage or build_storage(settings)

    run = DigestRun(run_id=uuid.uuid4().hex[:12])
    storage.create_run(run)

    raws: list[RawItem] = []
    for source in load_sources(settings.config_dir):
        if not source.enabled:
            continue
        try:
            raws.extend(_collect(source))
        except Exception as exc:  # per-source isolation
            run.source_errors.append(
                {
                    "source_id": source.id,
                    "error": str(exc),
                    "ts": datetime.now(timezone.utc).isoformat(),
                }
            )

    run.collected = len(raws)
    new_items = normalize.normalize_and_dedup(raws, storage, run.run_id)
    for item in new_items:
        item.status = "processed"  # skeleton: real LLM processing in Plan 2
    run.new = len(new_items)
    run.processed = len(new_items)
    storage.save_items(new_items)

    run.outputs["md"] = markdown.write_markdown(run, new_items, settings.output_dir)
    run.status = RunStatus.PARTIAL if run.source_errors else RunStatus.SUCCESS
    run.finished_at = datetime.now(timezone.utc)
    storage.finalize_run(run)
    return run
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_run_digest.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add app/runner.py tests/integration/test_run_digest.py
git commit -m "feat(runner): run_digest() orchestrator with per-source isolation"
```

---

### Task 10: CLI + full suite + manual end-to-end run

**Files:**
- Create: `app/cli.py`
- Modify: `pyproject.toml` (add console script)

- [ ] **Step 1: Write the CLI**

`app/cli.py`:
```python
from __future__ import annotations

import argparse

from app.runner import run_digest


def main() -> None:
    parser = argparse.ArgumentParser(prog="catchup", description="Catch-Up news digest")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("run", help="Run a digest now")
    args = parser.parse_args()

    if args.command == "run":
        run = run_digest()
        print(
            f"Run {run.run_id}: status={run.status.value} "
            f"collected={run.collected} new={run.new} -> {run.outputs.get('md')}"
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Register the console script**

In `pyproject.toml`, after the `[project]` table's dependencies block, add:
```toml
[project.scripts]
catchup = "app.cli:main"
```
Then run: `uv sync`

- [ ] **Step 3: Run the full test suite**

Run: `uv run pytest tests -q`
Expected: PASS — all unit + integration tests green (≈14 tests, 0 failures).

- [ ] **Step 4: Lint**

Run: `uv run ruff check app tests`
Expected: no errors (fix any with `uv run ruff check --fix app tests`).

- [ ] **Step 5: Manual end-to-end smoke (live RSS — needs internet)**

Run: `uv run python -m app.cli run`
Expected: prints `Run <id>: status=success collected=<N> new=<N> -> output/digest-<id>.md`, and `output/digest-<id>.md` exists with grouped headlines. (If a feed URL is down, status may be `partial` — that's the isolation working.)

- [ ] **Step 6: Commit**

```bash
git add app/cli.py pyproject.toml uv.lock
git commit -m "feat(cli): catchup run command + console script"
```

---

## Self-Review (completed)

- **Spec coverage (skeleton subset):** domain model §7 ✓, SQLite storage + port §12 ✓, RSS source §8 ✓, normalize/dedup §9 ✓, Markdown render §6 ✓, run_digest orchestration §11 ✓, per-source isolation §13 ✓, config-driven sources §18 ✓. Deferred to later plans (by design): LLM processing/digest editor (Plan 2), other collectors + Excel/HTML (Plan 3), ADK agent tree + scheduler + API (Plan 4), UI (Plan 5), security/prod (Plan 6).
- **Placeholder scan:** none — every step has runnable code or exact commands.
- **Type consistency:** `StorageBackend` method names (`existing_ids`, `save_items`, `get_items_for_run`, `create_run`, `finalize_run`, `get_run`) are identical across the port, the SQLite adapter, the contract test, normalize, and runner. `NewsItem.from_raw`, `make_item_id`, `RunStatus` values consistent throughout.

## Notes for the executor

- Run all Python via `uv run …` (project venv). Tests assume repo-root CWD (`pythonpath = "."`).
- Preserve `app/agent.py` (scaffolded demo) and its `Gemini(model="gemini-flash-latest")` — Plan 4 replaces it with the real pipeline. Do not change the model.
- After each task, append a one-line entry to `docs/BUILD-LOG.md` referencing the commit.
- Commit identity is repo-local (AhmedHeshamSakr / a.hesham1221@gmail.com). **No Claude trailers.**
