# Codex Pre-Execution Review — Audit Remediation Plan

> codex-cli read-only review of docs/superpowers/plans/2026-06-21-audit-remediation.md against live code.

# Pre-Execution Review

I do **not** think the plan is safe to execute as written. It is directionally good, but several steps need tightening before implementation.

## Blocking Findings

1. **Task 0.3 / 3.1 has a real Cloud Run auth hole.**  
   `create_app()` guards using `settings.app_host` ([app/api/app.py:344](<app/api/app.py:344>), [app/api/app.py:347](<app/api/app.py:347>)), but Docker/Cloud Run binds via uvicorn `--host 0.0.0.0` while `Settings.app_host` defaults to `127.0.0.1` ([app/core/config.py:144](<app/core/config.py:144>)). The planned `app.web_app:app = create_app()` would therefore not fail closed unless `APP_HOST=0.0.0.0` is also set. Fix: make `app/web_app.py` explicitly require `API_KEY`, or pass an actual `bind_host="0.0.0.0"` into a revised `create_app(..., bind_host=...)`.

2. **`fast_api_app.py` should check `API_KEY` before GCP auth/logging side effects.**  
   The current/proposed guard is after `google.auth.default()` and `google_cloud_logging.Client()` ([app/fast_api_app.py:43](<app/fast_api_app.py:43>), [app/fast_api_app.py:50](<app/fast_api_app.py:50>)). Without credentials, import can fail before the intended `API_KEY` error. Move `_settings = Settings()` and the key guard above GCP auth/client creation, or make telemetry/logging lazy. This matters for tests and for clean fail-closed semantics.

3. **Task 1.2 will break tests unless compatibility is explicit.**  
   The cycle is real: `pipeline/agents.py` imports helper functions from `runner.py` ([app/pipeline/agents.py:47](<app/pipeline/agents.py:47>)), while `runner.py` defers `build_pipeline` to avoid the cycle ([app/runner.py:156](<app/runner.py:156>)). Moving helpers to `pipeline/wiring.py` is correct, but `wiring.py` must **not** import `runner` or `build_storage`. Also preserve/update monkeypatch targets: tests patch `app.pipeline.agents._collect` and `runner.rss`/`runner.markdown` ([tests/integration/test_run_digest_database_session.py:47](<tests/integration/test_run_digest_database_session.py:47>), [tests/integration/test_run_digest.py:115](<tests/integration/test_run_digest.py:115>)).

4. **Task 2.1 FieldFilter needs a no-extra fallback or CI must install Firestore.**  
   `google-cloud-firestore` is optional ([pyproject.toml:42](<pyproject.toml:42>)), and current unit tests run without it ([tests/unit/test_build_storage.py:30](<tests/unit/test_build_storage.py:30>)). If production code unconditionally constructs `FieldFilter` inside fake-backed unit tests, default CI breaks. Implement `_where()` with `try ImportError` fallback, or install `--extra firestore` in the backend CI job.

## Focus-Point Answers

1. **Task 1.1 lazy `root_agent`: mostly correct.**  
   ADK uses `AgentLoader(agents_dir)` ([fast_api.py:172](<.venv/lib/python3.13/site-packages/google/adk/cli/fast_api.py:172>)). It first imports package `app`, checks `app`, then `root_agent`, then imports `app.agent` and checks again ([agent_loader.py:74](<.venv/lib/python3.13/site-packages/google/adk/cli/utils/agent_loader.py:74>), [agent_loader.py:123](<.venv/lib/python3.13/site-packages/google/adk/cli/utils/agent_loader.py:123>)). Module `__getattr__` will be triggered by `hasattr()`. Dropping `from .agent import app` from [app/__init__.py:15](<app/__init__.py:15>) is safe for ADK discovery and removes package import DB creation. I found no current test importing `from app import app`.

2. **Task 1.2 breaks the cycle if `wiring.py` stays independent.**  
   `build_storage` can stay in `runner.py`; `wiring.py` does not need it. The phrase “wiring may import it lazily if needed” should be removed.

3. **Task 0.4 `safe_get` streaming rewrite is technically sound.**  
   `continue` inside the redirect branch still runs `finally: resp.close()`. Returning a new fully-read `httpx.Response(content=..., request=resp.request)` is valid for callers using `.text/.json/.content`. Redirect bodies are not read, so size cap applies to the final body only, which is acceptable.

4. **Task 0.3 tests are mostly fine, but the signal is wrong for Docker.**  
   Existing tests use loopback settings, so they should survive. The planned test around `settings.app_host="0.0.0.0"` is useful, but it does not prove Cloud Run safety because uvicorn’s bind host is external to `Settings`.

5. **Task 2.x Firestore is directionally right but under-specified.**  
   `get_all(refs)` is the right primitive for `existing_ids` ([firestore_backend.py:40](<app/adapters/storage/firestore_backend.py:40>)). The fake needs `get_all` and `where(filter=...)`. The `is_flagged` reasoning holds: missing fields will not match `== False` ([test_firestore_emulator.py:14](<tests/integration/test_firestore_emulator.py:14>)). But the backfill task must be concrete: scan documents, batch-update missing `is_flagged`, and document/emulator-test it.

6. **Task 4.5 dropping tenancy fields is feasible with one correction.**  
   Keeping old SQLite physical columns is acceptable because current DDL columns are nullable ([sqlite_backend.py:44](<app/adapters/storage/sqlite_backend.py:44>)). Do **not** “write NULL” by naming the column if fresh DDL omits it. Omit `org_id` from `INSERT` column lists entirely so old and new schemas both work.

## Missing Tasks / Gaps

- Update `docs/ADK-GUIDE.md`; it still documents eager `app = App(...)` and `build_pipeline(..., run_id=...)`.
- Add explicit `app/web_app.py` deployed-entrypoint key enforcement.
- Move `fast_api_app.py` key guard before GCP auth/logging.
- Preserve or update runner monkeypatch compatibility during Task 1.2.
- Decide whether Firestore emulator runs in CI before claiming “Firestore swap real.”
- Make `/feedback` rate limit concrete; “reuse a token bucket” is too vague.

## Open Decisions

1. **Output keys:** confirm frontend change to `md/xlsx/html`. Safer because backend and existing DB rows already use those keys ([app/pipeline/agents.py:438](<app/pipeline/agents.py:438>)).

2. **SQLite tenancy columns:** keep old physical columns, omit from new DDL and new INSERTs. Do not rebuild tables for this cleanup.

3. **Firestore emulator in CI:** if the plan claims Firestore is “real,” run emulator in CI, even as a separate/manual workflow. `skipif` is acceptable only if docs still label Firestore pre-deploy validation as not continuously enforced.

## Ordering Risks

- Move the deployed product key guard into Task 3.1 or add a `bind_host` parameter in Task 0.3 before relying on `create_app()`.
- Install/test Firestore extra before declaring Phase 2 complete, or explicitly defer deploy readiness until Task 3.1.
- Do Task 1.1 before 1.2 is okay, but Task 1.2 must include test-path migration.
- Task 0.6 tests may require refactoring `fast_api_app.py` import side effects first.

## Verdict

Do not execute as written. Make the auth/bind-host fix, `fast_api_app` guard-order fix, Task 1.2 compatibility plan, and Firestore FieldFilter fallback/CI decision first. I did not run the test suite; `uv run` was blocked by the read-only sandbox trying to initialize its cache.
