# Firestore Storage Adapter + Vertex Path — Design

**Date:** 2026-06-18
**Sub-project:** C (second of the 4-subsystem post-remediation milestone: D durable state ✅ → **C Firestore/Vertex** → B scheduler → A console screens)
**Status:** Design — awaiting user spec review before plan.

## Goal

Add a `FirestoreBackend` behind the existing `StorageBackend` port and a config-driven **Vertex AI** path for the LLM client — both built as **optional, offline-tested adapters** (the chosen deploy target is local/self-hosted; these are GCP-prod readiness, **not live-deployed**). `build_storage` finally honors `settings.storage_backend`.

## Constraints (from the milestone decisions)

- **Local/self-hosted is the live target.** SQLite + AI Studio stay the defaults; Firestore + Vertex are opt-in.
- **Offline test suite preserved.** No network, no live GCP, no emulator required to run `pytest`. Firestore is tested via an injected **in-memory fake client**.
- **Honest caveat:** the Firestore adapter is structurally complete and unit-tested against the fake, but **not validated against real Firestore** (composite-index requirements, inequality-filter limits, `in`-query caps). A documented, skipped emulator test is left as the pre-deploy validation hook.

---

## C1 — FirestoreBackend

### Dependency & wiring

- `google-cloud-firestore` is an **optional `[firestore]` extra** in `pyproject.toml` — NOT a base runtime dep and NOT a test dep (tests use the fake).
- `FirestoreBackend.__init__(self, client, *, items_collection="news_items", runs_collection="digest_runs")` takes an **injectable client** — production passes a real `google.cloud.firestore.Client`; tests pass `FakeFirestoreClient`. The adapter imports nothing from `google.cloud` itself.
- `build_storage(settings)` (in `app/runner.py`) honors `settings.storage_backend`:
  - `"sqlite"` (default) → `SqliteBackend(settings.sqlite_path)` (unchanged).
  - `"firestore"` → lazily `from google.cloud import firestore`, build `firestore.Client(project=settings.google_cloud_project or None)`, return `FirestoreBackend(client)`. If the import fails, raise a clear `RuntimeError("storage_backend='firestore' requires the [firestore] extra: uv pip install '.[firestore]'")`.
  - Unknown value → `ValueError`.

### Query API choice (keeps tests dependency-free)

The adapter builds queries with **positional** `collection.where(field, op, value)` / `collection.order_by(field, direction="DESCENDING")` — so the `FakeFirestoreClient` needs no real `google.cloud` import. The descending direction is passed as the literal string `"DESCENDING"`, which **equals** `google.cloud.firestore.Query.DESCENDING` (the real client's constant is that string), so the same call works on the real client and the fake. (Real Firestore deprecates positional `where` in favor of `FieldFilter`; that swap is part of the pre-deploy emulator-validation step, noted in code + the emulator-test placeholder.)

### Data model

Two collections, document id = entity id:

| Collection | Doc id | Stored fields |
|---|---|---|
| `news_items` | `item.id` | `item.model_dump(mode="json")` **plus** a derived `is_flagged: bool` (`item.status == "flagged"`) |
| `digest_runs` | `run.run_id` | `run.model_dump(mode="json")` |

On read, reconstruct via `NewsItem.model_validate(doc)` / `DigestRun.model_validate(doc)`. The extra `is_flagged` key is ignored (pydantic v2 BaseModel default `extra="ignore"`). `init_schema()` is a **no-op** (Firestore is schemaless).

**Why `is_flagged`:** SQLite excludes flagged items with `status != 'flagged'` (an inequality) while ordering by `collected_at`. Firestore cannot combine an inequality filter with an `order_by` on a different field, so the adapter stores a boolean and filters by **equality** `where("is_flagged", "==", False)`, which composes with `order_by("collected_at", DESCENDING)` (requires a composite index in real Firestore — documented).

### Method mapping (all 10 `StorageBackend` methods)

- `init_schema()` — no-op.
- `existing_ids(ids)` — for each id, `items_collection.document(id).get().exists`; return the set that exist. (Chunked `get_all`/`in` is a real-Firestore optimization left for the pre-deploy step; per-id existence is correct against the fake.)
- `save_items(items)` — chunked `client.batch()` of ≤500 `batch.set(items_collection.document(i.id), {**i.model_dump(mode="json"), "is_flagged": i.status == "flagged"})`, `batch.commit()` per chunk (upsert semantics, matching SQLite `INSERT OR REPLACE`).
- `get_items_for_run(run_id, *, include_flagged=False)` — `where("digest_run_id","==",run_id)`; add `where("is_flagged","==",False)` unless `include_flagged`; `model_validate` each.
- `create_run(run)` — `runs_collection.document(run.run_id).set(run.model_dump(mode="json"))` (upsert).
- `finalize_run(run)` — delegates to `create_run` (matches SQLite).
- `get_run(run_id)` — `runs_collection.document(run_id).get()`; `model_validate` or `None`.
- `list_runs(limit=20, offset=0)` — `order_by("started_at", DESCENDING).offset(offset).limit(limit)`.
- `list_news(*, category=None, importance=None, limit=50, offset=0, include_flagged=False)` — `where("category","==",category.value)` / `where("importance","==",importance.value)` when given; `where("is_flagged","==",False)` unless `include_flagged`; `order_by("collected_at", DESCENDING).offset(offset).limit(limit)`.

### FakeFirestoreClient (test helper)

A small in-memory fake under `tests/` implementing only the surface the adapter uses:
- `client.collection(name)` → `FakeCollection` (dict of doc_id → data).
- `FakeCollection.document(id)` → `FakeDocRef` with `.set(data)` (upsert), `.get()` → `FakeSnapshot(.exists, .id, .to_dict())`.
- `FakeCollection.where(field, op, value)` (supports `==`), `.order_by(field, direction)`, `.offset(n)`, `.limit(n)`, `.stream()` → iterator of snapshots. Query is a chained immutable builder applied at `stream()`.
- `client.batch()` → `FakeBatch` with `.set(ref, data)` and `.commit()`.

### Tests

- A **shared `StorageBackend` contract test suite** parametrized over both backends (`SqliteBackend` in tmp_path, `FirestoreBackend(FakeFirestoreClient())`), asserting identical behavior for: save/dedup (`existing_ids`), `get_items_for_run` flagged-exclusion, run create/finalize/get, `list_runs` ordering+pagination, `list_news` category/importance filters + flagged-exclusion + ordering + pagination. This proves both adapters satisfy one contract.
- `build_storage` selection tests: `sqlite`→`SqliteBackend`; `firestore` (with firestore importable) → `FirestoreBackend`; unknown → `ValueError`; missing-extra → actionable `RuntimeError` (simulated by monkeypatching the import).
- A **skipped** `@pytest.mark.skip(reason="needs Firestore emulator; pre-deploy validation")` placeholder documenting the emulator test to run before any real deploy.

---

## C2 — Vertex AI path

### Settings (`app/core/config.py`)

```python
use_vertexai: bool = False
google_cloud_project: str = ""
# "global" avoids the model-404s seen with regional endpoints (see CLAUDE.md).
google_cloud_location: str = "global"
```

### Behavior (`app/llm/runtime.py`)

Add `configure_genai(settings)` and update its call-sites (`run_agent_text`, and any other `ensure_api_key` caller — search first); keep `ensure_api_key = configure_genai` as a thin back-compat alias so existing imports/tests don't break. `configure_genai`:
- `use_vertexai=True`: set `os.environ["GOOGLE_GENAI_USE_VERTEXAI"]="TRUE"`, `GOOGLE_CLOUD_PROJECT=settings.google_cloud_project`, `GOOGLE_CLOUD_LOCATION=settings.google_cloud_location`; do **not** require `GOOGLE_API_KEY`. Fail fast with `ValueError` if `google_cloud_project` is empty.
- `use_vertexai=False` (default): today's behavior — export `GOOGLE_API_KEY` from `settings.google_api_key` if set and not already in env.
- Never overwrite a value already present in `os.environ` (respects an operator-set env).

`build_storage`/Vertex are independent; the Vertex switch only touches the LLM credential path, not storage.

### Tests

- `configure_genai` with `use_vertexai=True` sets the three Vertex env vars (project/location/flag) and does not require an API key; empty project → `ValueError`.
- `use_vertexai=False` keeps the existing `GOOGLE_API_KEY` behavior (existing `ensure_api_key` tests preserved).
- Offline — asserts env configuration only; no real Vertex/genai call.

---

## Out of scope (this sub-project)

- Live GCP deploy / running against real Firestore or Vertex (the milestone target is local/self-hosted).
- Firestore session service for ADK (sub-project D used `DatabaseSessionService`; a Firestore session service is a separate future step).
- Real-Firestore query optimization (`in`/`get_all` batching, composite-index provisioning) — left as the documented pre-deploy step.
- Scheduler (B) and console screens (A).

## Acceptance

1. `build_storage(Settings(storage_backend="firestore"))` returns a `FirestoreBackend` (with the extra installed) and raises an actionable error without it.
2. The shared `StorageBackend` contract suite passes against **both** `SqliteBackend` and `FirestoreBackend(FakeFirestoreClient())`.
3. `configure_genai` sets Vertex env vars when `use_vertexai=True` (project required) and preserves the AI-Studio path otherwise.
4. Full backend suite green: `uv run pytest tests/unit tests/integration -q`; ruff clean: `uv run --extra lint ruff check app tests`.
5. Defaults unchanged: with no new settings, the app still uses `SqliteBackend` + `GOOGLE_API_KEY` (AI Studio).
