# Firestore Storage Adapter + Vertex Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. **Each task is gated by a Codex review before commit.**

**Goal:** Add a `FirestoreBackend` behind the existing `StorageBackend` port and a config-driven Vertex AI path for the LLM client — both optional, offline-tested, not live-deployed.

**Architecture:** `FirestoreBackend(client)` takes an injectable Firestore client (real `firestore.Client` in prod, an in-memory `FakeFirestoreClient` in tests); it satisfies the same `StorageContract` the SQLite backend does. `build_storage` finally honors `settings.storage_backend`. A `configure_genai(settings)` helper sets AI-Studio (default) or Vertex env vars for the genai client.

**Tech Stack:** Python 3.13, pydantic v2 / pydantic-settings, `google-cloud-firestore` (optional `[firestore]` extra, NOT a test dep), pytest, `uv`.

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-06-18-firestore-vertex-design.md` — authoritative.
- **Commit identity:** `AhmedHeshamSakr <a.hesham1221@gmail.com>`, **NO AI/Claude trailers**.
- **Offline tests only** — no network, no live GCP, no emulator. Firestore is tested via the injected `FakeFirestoreClient`. `google-cloud-firestore` is NOT installed in the test env.
- **Defaults unchanged** — with no new settings the app uses `SqliteBackend` + `GOOGLE_API_KEY` (AI Studio).
- **Do NOT change any `model` value.** Run Python via `uv`. Lint: `uv run --extra lint ruff check app tests`.
- **Verify bar (every task ends green):** `uv run pytest tests/unit tests/integration -q` and ruff clean.

---

## File Structure

- `app/core/config.py` — add `use_vertexai`, `google_cloud_project`, `google_cloud_location` (Task 1).
- `app/llm/runtime.py` — add `configure_genai`; keep `ensure_api_key` as alias (Task 1).
- `tests/unit/fake_firestore.py` — **new**; in-memory Firestore client fake (Task 2).
- `app/adapters/storage/firestore_backend.py` — **new**; `FirestoreBackend` (Task 3).
- `tests/unit/test_firestore_backend.py` — **new**; `StorageContract` subclass + fake-specific tests (Task 3).
- `app/runner.py` — `_firestore_client` + `build_storage` honoring `storage_backend` (Task 4).
- `pyproject.toml` — `[firestore]` optional extra (Task 4).
- `tests/unit/test_build_storage.py` — **new**; selection + error tests (Task 4).
- `tests/integration/test_firestore_emulator.py` — **new**; skipped emulator placeholder (Task 5).
- `docs/ADK-GUIDE.md`, `docs/BUILD-LOG.md` — document the adapter + Vertex path (Task 5).

---

### Task 1: Vertex path — settings + `configure_genai`

**Files:**
- Modify: `app/core/config.py` (Settings)
- Modify: `app/llm/runtime.py:36-39` (`ensure_api_key` → `configure_genai` + alias) and `:73`
- Test: `tests/unit/test_config.py`, `tests/unit/test_adk_runtime.py`

**Interfaces:**
- Produces: `Settings.use_vertexai: bool`, `Settings.google_cloud_project: str`, `Settings.google_cloud_location: str`; `configure_genai(settings: Settings) -> None`; `ensure_api_key = configure_genai`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_config.py`:
```python
def test_vertex_defaults(monkeypatch):
    for k in ("USE_VERTEXAI", "GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION"):
        monkeypatch.delenv(k, raising=False)
    s = Settings(_env_file=None)
    assert s.use_vertexai is False
    assert s.google_cloud_project == ""
    assert s.google_cloud_location == "global"
```
Add to `tests/unit/test_adk_runtime.py`:
```python
def test_configure_genai_vertex_sets_env(monkeypatch):
    from app.core.config import Settings
    from app.llm.runtime import configure_genai
    for k in ("GOOGLE_GENAI_USE_VERTEXAI", "GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION"):
        monkeypatch.delenv(k, raising=False)
    configure_genai(Settings(_env_file=None, use_vertexai=True, google_cloud_project="proj-x"))
    assert os.environ["GOOGLE_GENAI_USE_VERTEXAI"] == "TRUE"
    assert os.environ["GOOGLE_CLOUD_PROJECT"] == "proj-x"
    assert os.environ["GOOGLE_CLOUD_LOCATION"] == "global"


def test_configure_genai_vertex_requires_project():
    import pytest
    from app.core.config import Settings
    from app.llm.runtime import configure_genai
    with pytest.raises(ValueError, match="google_cloud_project"):
        configure_genai(Settings(_env_file=None, use_vertexai=True, google_cloud_project=""))
```
(Add `import os` to `test_adk_runtime.py` if absent.)

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_config.py::test_vertex_defaults tests/unit/test_adk_runtime.py -k "configure_genai" -v`
Expected: FAIL — fields/`configure_genai` missing.

- [ ] **Step 3: Add the settings**

In `app/core/config.py`, after the `session_db_url` field add:
```python
    # LLM provider. False (default) = Google AI Studio via GOOGLE_API_KEY. True =
    # Vertex AI (sets GOOGLE_GENAI_USE_VERTEXAI + project/location for the genai
    # client). "global" location avoids the model-404s seen on regional endpoints.
    use_vertexai: bool = False
    google_cloud_project: str = ""
    google_cloud_location: str = "global"
```

- [ ] **Step 4: Add `configure_genai`**

In `app/llm/runtime.py`, replace `ensure_api_key` (lines 36-39) with:
```python
def configure_genai(settings: Settings) -> None:
    """Configure the google-genai client env for AI Studio (default) or Vertex.

    Never overwrites a value already in os.environ (respects operator-set env).
    Uses getattr defaults so minimal test settings-stubs (which only define
    google_api_key) keep working — see tests/integration/test_pipeline_live_bridge.py.
    """
    if getattr(settings, "use_vertexai", False):
        project = getattr(settings, "google_cloud_project", "")
        if not project:
            raise ValueError("use_vertexai=True requires google_cloud_project")
        location = getattr(settings, "google_cloud_location", "global")
        os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
        os.environ.setdefault("GOOGLE_CLOUD_PROJECT", project)
        os.environ.setdefault("GOOGLE_CLOUD_LOCATION", location)
        return
    # AI Studio (unchanged): the google client reads GOOGLE_API_KEY from the env.
    if settings.google_api_key and not os.environ.get("GOOGLE_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = settings.google_api_key


# Back-compat alias — existing call-sites/tests import `ensure_api_key`.
ensure_api_key = configure_genai
```
Then update the in-module call at line ~73 (`run_agent_text`) from `ensure_api_key(settings)` to `configure_genai(settings)`. (`app/services/search.py` keeps importing `ensure_api_key` — the alias.)

- [ ] **Step 5: Run to verify they pass**

Run: `uv run pytest tests/unit/test_config.py tests/unit/test_adk_runtime.py tests/unit/test_search.py -q`
Expected: PASS (existing `ensure_api_key` tests still green via the alias).

- [ ] **Step 6: Commit**

```bash
git add app/core/config.py app/llm/runtime.py tests/unit/test_config.py tests/unit/test_adk_runtime.py
git commit -m "feat(llm): Vertex AI path via configure_genai + use_vertexai settings"
```

---

### Task 2: `FakeFirestoreClient` test helper

**Files:**
- Create: `tests/unit/fake_firestore.py`
- Test: `tests/unit/test_fake_firestore.py` (new)

**Interfaces:**
- Produces: `FakeFirestoreClient` with `.collection(name)` and `.batch()`; collections support `.document(id).set/get`, and chained `.where(field, op, value)` / `.order_by(field, direction="DESCENDING")` / `.offset(n)` / `.limit(n)` / `.stream()`. `.get()` → snapshot with `.exists`, `.id`, `.to_dict()`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_fake_firestore.py`:
```python
from tests.unit.fake_firestore import FakeFirestoreClient


def test_set_get_and_existence():
    c = FakeFirestoreClient()
    c.collection("x").document("a").set({"v": 1})
    snap = c.collection("x").document("a").get()
    assert snap.exists and snap.id == "a" and snap.to_dict() == {"v": 1}
    assert c.collection("x").document("missing").get().exists is False


def test_where_order_offset_limit():
    c = FakeFirestoreClient()
    col = c.collection("x")
    for i, k in enumerate("abcd"):
        col.document(k).set({"cat": "ai" if i < 3 else "biz", "t": f"2026-05-2{i}"})
    rows = list(
        c.collection("x").where("cat", "==", "ai")
        .order_by("t", "DESCENDING").offset(1).limit(1).stream()
    )
    assert [r.id for r in rows] == ["b"]  # ai = a,b,c (t=20,21,22) desc→c,b,a; offset1→b; limit1


def test_batch_set_commits_all():
    c = FakeFirestoreClient()
    col = c.collection("x")
    batch = c.batch()
    batch.set(col.document("a"), {"v": 1})
    batch.set(col.document("b"), {"v": 2})
    assert col.document("a").get().exists is False  # not yet committed
    batch.commit()
    assert col.document("a").get().to_dict() == {"v": 1}
    assert col.document("b").get().to_dict() == {"v": 2}
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_fake_firestore.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement the fake**

Create `tests/unit/fake_firestore.py`:
```python
"""In-memory stand-in for google.cloud.firestore.Client — only the surface
FirestoreBackend uses. Offline; no real Firestore semantics (no composite-index
or inequality-filter constraints), so it validates the adapter's logic, not
Firestore itself."""
from __future__ import annotations

import copy


class FakeSnapshot:
    def __init__(self, doc_id: str, data: dict | None) -> None:
        self.id = doc_id
        self._data = data

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self) -> dict | None:
        return copy.deepcopy(self._data) if self._data is not None else None


class FakeDocRef:
    def __init__(self, store: dict, doc_id: str) -> None:
        self._store = store
        self.id = doc_id

    def set(self, data: dict) -> None:
        self._store[self.id] = copy.deepcopy(data)

    def get(self) -> FakeSnapshot:
        return FakeSnapshot(self.id, self._store.get(self.id))


class FakeQuery:
    def __init__(self, store: dict) -> None:
        self._store = store
        self._filters: list[tuple[str, str, object]] = []
        self._order: tuple[str, bool] | None = None
        self._offset = 0
        self._limit: int | None = None

    def _clone(self) -> FakeQuery:
        q = FakeQuery(self._store)
        q._filters = list(self._filters)
        q._order = self._order
        q._offset = self._offset
        q._limit = self._limit
        return q

    def where(self, field: str, op: str, value: object) -> FakeQuery:
        if op != "==":
            raise NotImplementedError(f"fake supports only '==', got {op!r}")
        q = self._clone()
        q._filters.append((field, op, value))
        return q

    def order_by(self, field: str, direction: str = "ASCENDING") -> FakeQuery:
        q = self._clone()
        q._order = (field, direction == "DESCENDING")
        return q

    def offset(self, n: int) -> FakeQuery:
        q = self._clone()
        q._offset = n
        return q

    def limit(self, n: int) -> FakeQuery:
        q = self._clone()
        q._limit = n
        return q

    def stream(self):
        rows = list(self._store.items())
        for field, _op, value in self._filters:
            rows = [(k, v) for k, v in rows if v.get(field) == value]
        if self._order is not None:
            field, desc = self._order
            rows.sort(key=lambda kv: kv[1].get(field), reverse=desc)
        rows = rows[self._offset:]
        if self._limit is not None:
            rows = rows[: self._limit]
        return iter(FakeSnapshot(k, copy.deepcopy(v)) for k, v in rows)


class FakeCollection(FakeQuery):
    def document(self, doc_id: str) -> FakeDocRef:
        return FakeDocRef(self._store, doc_id)


class FakeBatch:
    def __init__(self) -> None:
        self._ops: list[tuple[FakeDocRef, dict]] = []

    def set(self, ref: FakeDocRef, data: dict) -> None:
        self._ops.append((ref, data))

    def commit(self) -> None:
        for ref, data in self._ops:
            ref.set(data)
        self._ops = []


class FakeFirestoreClient:
    def __init__(self) -> None:
        self._collections: dict[str, dict] = {}

    def collection(self, name: str) -> FakeCollection:
        return FakeCollection(self._collections.setdefault(name, {}))

    def batch(self) -> FakeBatch:
        return FakeBatch()
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/test_fake_firestore.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add tests/unit/fake_firestore.py tests/unit/test_fake_firestore.py
git commit -m "test: in-memory FakeFirestoreClient for offline adapter tests"
```

---

### Task 3: `FirestoreBackend` adapter

**Files:**
- Create: `app/adapters/storage/firestore_backend.py`
- Test: `tests/unit/test_firestore_backend.py`

**Interfaces:**
- Consumes: `StorageBackend` port; `FakeFirestoreClient` (Task 2); `StorageContract` (`tests/unit/storage_contract.py`).
- Produces: `FirestoreBackend(client, *, items_collection="news_items", runs_collection="digest_runs")`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_firestore_backend.py`:
```python
import pytest

from app.adapters.storage.firestore_backend import FirestoreBackend
from tests.unit.fake_firestore import FakeFirestoreClient
from tests.unit.storage_contract import StorageContract


class TestFirestoreBackend(StorageContract):
    @pytest.fixture(autouse=True)
    def _setup(self):
        self.backend = FirestoreBackend(FakeFirestoreClient())
        self.backend.init_schema()  # no-op, must not raise


def test_save_items_sets_is_flagged_field():
    from app.core.domain import NewsItem, RawItem, SourceType
    client = FakeFirestoreClient()
    be = FirestoreBackend(client)
    raw = RawItem(source_id="s", source_type=SourceType.RSS, source_name="S",
                  url="https://a/1", title="t")
    item = NewsItem.from_raw(raw, run_id="r1")
    item.status = "flagged"
    be.save_items([item])
    doc = client.collection("news_items").document(item.id).get().to_dict()
    assert doc["is_flagged"] is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_firestore_backend.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement the adapter**

Create `app/adapters/storage/firestore_backend.py`:
```python
"""Firestore StorageBackend adapter (optional [firestore] extra).

Takes an injectable client so the same code runs against a real
google.cloud.firestore.Client (prod) and an in-memory fake (tests). Queries use
positional where(field, op, value) and order_by(field, "DESCENDING") so no
google.cloud import is needed at adapter scope. (Real Firestore deprecates
positional where in favor of FieldFilter; swap that during emulator validation
before any real deploy — see tests/integration/test_firestore_emulator.py.)
Flagged-exclusion uses a derived is_flagged boolean (equality), because Firestore
can't combine an inequality filter with an order_by on a different field.
"""
from __future__ import annotations

from app.core.domain import DigestRun, NewsItem
from app.core.ports.storage import StorageBackend

_DESC = "DESCENDING"  # equals google.cloud.firestore.Query.DESCENDING
_BATCH_LIMIT = 500    # Firestore batch write cap


class FirestoreBackend(StorageBackend):
    def __init__(
        self, client, *, items_collection: str = "news_items",
        runs_collection: str = "digest_runs",
    ) -> None:
        self._client = client
        self._items_name = items_collection
        self._runs_name = runs_collection

    def _items(self):
        return self._client.collection(self._items_name)

    def _runs(self):
        return self._client.collection(self._runs_name)

    def init_schema(self) -> None:
        return None  # Firestore is schemaless

    def existing_ids(self, ids: list[str]) -> set[str]:
        if not ids:
            return set()
        col = self._items()
        return {i for i in ids if col.document(i).get().exists}

    @staticmethod
    def _item_doc(item: NewsItem) -> dict:
        data = item.model_dump(mode="json")
        data["is_flagged"] = item.status == "flagged"
        return data

    def save_items(self, items: list[NewsItem]) -> None:
        if not items:
            return
        col = self._items()
        for start in range(0, len(items), _BATCH_LIMIT):
            batch = self._client.batch()
            for item in items[start: start + _BATCH_LIMIT]:
                batch.set(col.document(item.id), self._item_doc(item))
            batch.commit()

    def get_items_for_run(
        self, run_id: str, *, include_flagged: bool = False
    ) -> list[NewsItem]:
        q = self._items().where("digest_run_id", "==", run_id)
        if not include_flagged:
            q = q.where("is_flagged", "==", False)
        return [NewsItem.model_validate(s.to_dict()) for s in q.stream()]

    def create_run(self, run: DigestRun) -> None:
        self._runs().document(run.run_id).set(run.model_dump(mode="json"))

    def finalize_run(self, run: DigestRun) -> None:
        self.create_run(run)

    def get_run(self, run_id: str) -> DigestRun | None:
        snap = self._runs().document(run_id).get()
        return DigestRun.model_validate(snap.to_dict()) if snap.exists else None

    def list_runs(self, limit: int = 20, offset: int = 0) -> list[DigestRun]:
        q = self._runs().order_by("started_at", _DESC).offset(offset).limit(limit)
        return [DigestRun.model_validate(s.to_dict()) for s in q.stream()]

    def list_news(
        self, *, category=None, importance=None, limit: int = 50, offset: int = 0,
        include_flagged: bool = False,
    ) -> list[NewsItem]:
        q = self._items()
        if category is not None:
            q = q.where("category", "==", category.value)
        if importance is not None:
            q = q.where("importance", "==", importance.value)
        if not include_flagged:
            q = q.where("is_flagged", "==", False)
        q = q.order_by("collected_at", _DESC).offset(offset).limit(limit)
        return [NewsItem.model_validate(s.to_dict()) for s in q.stream()]
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/test_firestore_backend.py -v`
Expected: PASS — all inherited `StorageContract` tests + the is_flagged test.

- [ ] **Step 5: Commit**

```bash
git add app/adapters/storage/firestore_backend.py tests/unit/test_firestore_backend.py
git commit -m "feat(storage): FirestoreBackend adapter (injectable client, contract-tested)"
```

---

### Task 4: `build_storage` honors `storage_backend` + `[firestore]` extra

**Files:**
- Modify: `app/runner.py` — `build_storage` + new `_firestore_client`
- Modify: `pyproject.toml:37-45` (optional-dependencies)
- Test: `tests/unit/test_build_storage.py`

**Interfaces:**
- Consumes: `FirestoreBackend` (Task 3), `FakeFirestoreClient` (Task 2).
- Produces: `_firestore_client(settings) -> object`; `build_storage` selecting by `settings.storage_backend`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_build_storage.py`:
```python
import pytest

from app.adapters.storage.firestore_backend import FirestoreBackend
from app.adapters.storage.sqlite_backend import SqliteBackend
from app.core.config import Settings
from app.runner import build_storage
from tests.unit.fake_firestore import FakeFirestoreClient


def test_build_storage_sqlite_default(tmp_path):
    s = Settings(_env_file=None, sqlite_path=str(tmp_path / "c.db"))
    assert isinstance(build_storage(s), SqliteBackend)


def test_build_storage_firestore(monkeypatch, tmp_path):
    import app.runner as runner_mod
    monkeypatch.setattr(runner_mod, "_firestore_client", lambda settings: FakeFirestoreClient())
    s = Settings(_env_file=None, storage_backend="firestore",
                 sqlite_path=str(tmp_path / "c.db"))
    assert isinstance(build_storage(s), FirestoreBackend)


def test_build_storage_unknown_backend(tmp_path):
    s = Settings(_env_file=None, storage_backend="mongo",
                 sqlite_path=str(tmp_path / "c.db"))
    with pytest.raises(ValueError, match="storage_backend"):
        build_storage(s)


def test_firestore_client_missing_extra_raises():
    # The [firestore] extra is not installed in the test env → actionable error.
    try:
        import google.cloud.firestore  # noqa: F401
        pytest.skip("firestore extra installed; missing-extra path not exercised")
    except ImportError:
        pass
    from app.runner import _firestore_client
    with pytest.raises(RuntimeError, match="firestore"):
        _firestore_client(Settings(_env_file=None))
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_build_storage.py -v`
Expected: FAIL — `_firestore_client` missing / `build_storage` doesn't branch.

- [ ] **Step 3: Implement selection in `app/runner.py`**

Replace `build_storage` (lines 34-37) with:
```python
def _firestore_client(settings: Settings):
    """Construct a real Firestore client; clear error if the extra is missing."""
    try:
        from google.cloud import firestore
    except ImportError as exc:  # optional [firestore] extra not installed
        raise RuntimeError(
            "storage_backend='firestore' requires the [firestore] extra: "
            "uv pip install '.[firestore]'"
        ) from exc
    return firestore.Client(project=settings.google_cloud_project or None)


def build_storage(settings: Settings) -> StorageBackend:
    backend = settings.storage_backend
    if backend == "sqlite":
        store: StorageBackend = SqliteBackend(settings.sqlite_path)
    elif backend == "firestore":
        from app.adapters.storage.firestore_backend import FirestoreBackend
        store = FirestoreBackend(_firestore_client(settings))
    else:
        raise ValueError(f"unknown storage_backend: {backend!r}")
    store.init_schema()
    return store
```

- [ ] **Step 4: Add the `[firestore]` extra**

In `pyproject.toml` under `[project.optional-dependencies]`, add:
```toml
firestore = [
    "google-cloud-firestore>=2.16.0,<3.0.0",
]
```
Then run `uv lock` (the repo tracks `uv.lock`; this resolves the new optional dep into the lock graph). Do **NOT** run `uv sync`/`uv sync --extra firestore` — the package must stay **uninstalled** in the test env so the missing-extra test exercises the error path.

- [ ] **Step 5: Run to verify they pass**

Run: `uv run pytest tests/unit/test_build_storage.py -q`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add app/runner.py pyproject.toml uv.lock tests/unit/test_build_storage.py
git commit -m "feat(storage): build_storage honors storage_backend + [firestore] extra"
```

---

### Task 5: Emulator placeholder + docs + final verification

**Files:**
- Create: `tests/integration/test_firestore_emulator.py`
- Modify: `docs/ADK-GUIDE.md`, `docs/BUILD-LOG.md`

- [ ] **Step 1: Add the skipped emulator placeholder**

Create `tests/integration/test_firestore_emulator.py`:
```python
"""Pre-deploy validation hook: run FirestoreBackend against the real Firestore
emulator. SKIPPED by default — the offline suite uses FakeFirestoreClient, which
does NOT enforce real Firestore semantics (composite indexes, inequality-filter
limits, in-query caps). Before any real GCP deploy: start the emulator
(`gcloud beta emulators firestore start`), set FIRESTORE_EMULATOR_HOST, install
the [firestore] extra, swap positional where() → FieldFilter, and un-skip."""
import pytest

pytestmark = pytest.mark.skip(
    reason="needs Firestore emulator + [firestore] extra; pre-deploy validation"
)


def test_firestore_backend_against_emulator():
    raise AssertionError("implement against the emulator before deploy")
```

- [ ] **Step 2: Verify it skips (does not error)**

Run: `uv run pytest tests/integration/test_firestore_emulator.py -v`
Expected: 1 skipped.

- [ ] **Step 3: Document the adapter + Vertex path**

In `docs/ADK-GUIDE.md` §6 (Free tier vs production), update to note `storage_backend="firestore"` (FirestoreBackend behind the port, `[firestore]` extra) and `use_vertexai=True` (`configure_genai` sets `GOOGLE_GENAI_USE_VERTEXAI`+project/location) as the now-implemented opt-in adapters, with the "not validated against live Firestore" caveat.

Append a `### Phase: Firestore adapter + Vertex path — sub-project C ✅` entry to `docs/BUILD-LOG.md` summarizing: injectable `FirestoreBackend` (positional where, `is_flagged` boolean, two collections), `StorageContract` shared across SQLite+Firestore, `FakeFirestoreClient`, `build_storage` selection + `[firestore]` extra, `configure_genai` Vertex switch, skipped emulator placeholder. Note the manual key-rotation TODO is still open.

- [ ] **Step 4: Final verification**

Run each and confirm green:
```bash
uv run pytest tests/unit tests/integration -q
uv run --extra lint ruff check app tests
```
Expected: all pass; lint clean; the emulator test shows as skipped; `build_storage(Settings())` still returns `SqliteBackend`.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_firestore_emulator.py docs/ADK-GUIDE.md docs/BUILD-LOG.md
git commit -m "docs+test: Firestore/Vertex readiness notes + skipped emulator placeholder"
```

---

## Self-Review

**1. Spec coverage:**
- FirestoreBackend behind the port (injectable client) → Task 3. ✓
- In-memory fake, offline → Task 2. ✓
- `build_storage` honors `storage_backend` + actionable missing-extra error → Task 4. ✓
- `[firestore]` optional extra, not a test dep → Task 4. ✓
- Data model (2 collections, `is_flagged` derived, `model_dump`/`model_validate`) → Task 3. ✓
- All 9 `StorageBackend` methods → Task 3 (via `StorageContract` inheritance + the is_flagged test; `init_schema` is a no-op exercised by the fixture). ✓
- Shared contract suite across both backends → Task 3 (reuses `StorageContract`). ✓
- Vertex `configure_genai` + settings + fail-fast empty project → Task 1. ✓
- `ensure_api_key` alias preserved → Task 1. ✓
- Skipped emulator placeholder → Task 5. ✓
- Defaults unchanged → covered (Task 4 default test; Task 1 alias keeps AI-Studio path). ✓

**2. Placeholder scan:** No "TBD"/"handle errors"/"similar to". The emulator placeholder intentionally `raise AssertionError` inside a module-level `skip` — it never runs.

**3. Type consistency:** `FirestoreBackend(client, *, items_collection, runs_collection)`, `_firestore_client(settings)`, `configure_genai(settings)`, `FakeFirestoreClient().collection().document().set/get`, `.where(field, op, value)`, `.order_by(field, "DESCENDING")`, `.stream()` are used consistently across Tasks 2–4. `_DESC="DESCENDING"`, `is_flagged` field name, and the `news_items`/`digest_runs` collection names match between the fake-data assertions and the adapter.
