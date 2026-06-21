# Codex Independent Review — Deep Audit (2026-06-21)

> Produced by `codex-cli 0.140.0` (read-only sandbox) reviewing `docs/AUDIT-2026-06-21.md` + findings JSON against the live code. 195,924 tokens.

**Independent Audit Review**

I did not rubber-stamp the report. Most core recommendations are sound, but several claims are overstated or need narrower wording.

**Required Finding Verification**

| Finding | Verdict | Evidence |
|---|---:|---|
| Pipeline screen missing | **AGREE, with caveats** | Spec promises Pipeline screen/API at `docs/superpowers/specs/2026-05-23-adk-catchup-agent-design.md:237-248`; sidebar has only Dashboard/Digests/News/Sources/Watchlist/Settings at `frontend/components/layout/sidebar.tsx:32-49`; no `frontend/app/pipeline`; API decorators stop at existing routes in `app/api/app.py:164-283`. Caveat: API does serialize full `DigestRun` via `RunDetail` at `app/api/schemas.py:17-19`; the frontend strips `flagged`/`critic_verdicts` because `frontend/lib/schemas.ts:59-72` omits them. |
| API open by default ships to container | **AGREE** | `api_key` defaults `None` at `app/core/config.py:137-138`; `_require_api_key` returns when unset at `app/api/app.py:93-105`; routes are registered into Cloud Run entrypoint at `app/fast_api_app.py:50,77`; Docker runs that app on `0.0.0.0:8080` at `Dockerfile:39`. Settings routes are separately loopback-guarded at `app/api/app.py:63-78`. |
| No CI anywhere | **AGREE** | No workflow/hook dirs found; only YAML files are manifest/config. Manifest says `cicd_runner: "skip"` at `agents-cli-manifest.yaml:8-14`; frontend has manual `test`/`build` scripts at `frontend/package.json:5-11`; eval regression CLI exists at `scripts/eval_enrichment.py:186-188,251-258` but nothing invokes it. |
| Plaintext API keys in `app/.env` | **PARTIAL** | Key-shaped values exist at `app/.env:2-3`; `.gitignore:2-4` ignores `.env` files. I cannot verify from static review that they are live/active. Rotation is still the right precaution. |
| SSRF guard lacks response-size cap | **AGREE** | `safe_get` validates scheme/IP/redirects but calls non-streaming `client.send(request)` at `app/services/net.py:120-125`; callers read full `.content`, `.text`, or `.json()` in `app/services/rss.py:16-18`, `scrape.py:17-19`, `feed_discovery.py:16-18`, `youtube.py:54-56`, `newsapi.py:32-34`. |
| Rate limiting is global and narrow | **AGREE** | `TokenBucket` has no client key at `app/services/ratelimit.py:8-37`; one shared bucket is created at `app/api/app.py:143-149`; applied only to `POST /runs` and `POST /sources/resolve` at `app/api/app.py:273-284`. Collectors use `safe_get` directly. |
| Markdown injection | **AGREE, scoped low** | Markdown interpolates raw title/url/source/summary at `app/services/render/markdown.py:39-41`. The app’s HTML renderer does escape and href-filter at `app/services/render/html.py:37-49,59-61`, so this is only dangerous when the generated Markdown is rendered by an unsafe Markdown-to-HTML consumer. |

**Load-Bearing Claims**

- **Open-by-default API:** **AGREE.** The default is intentionally open and the Docker entrypoint includes product `/api/*`. The report is right to make this P0 for any non-loopback deployment.

- **Two ASGI entrypoints / Docker ships no UI:** **AGREE, but wording should be “no product console.”** `create_app()` mounts the Next static console when `frontend/out` exists at `app/api/app.py:316-367`; Docker runs `app.fast_api_app:app` at `Dockerfile:39`; `fast_api_app.py` enables ADK web UI with `web=True` at `app/fast_api_app.py:62-68` and registers product routes at `:77`, but Docker copies only `app/` and `config/` at `Dockerfile:23-27`, never builds/copies `frontend/out`.

- **Firestore would fail on first real query:** **PARTIAL / OVERSTATED.** Real risks are present: positional `where()` is used at `app/adapters/storage/firestore_backend.py:65-67,90-95`; fake explicitly lacks real index semantics at `tests/unit/fake_firestore.py:1-4`; emulator test is permanently skipped and raises at `tests/integration/test_firestore_emulator.py:23-29`; no `firestore.indexes.json` exists. But “first real query” is too broad: doc reads/writes and `list_runs()` likely work; missing composite indexes primarily break filtered+ordered `list_news()`. Also, README/ADK guide openly caveat Firestore as not live-validated at `README.md:16-19` and `docs/ADK-GUIDE.md:158`.

- **Import-time SQLite side effects:** **AGREE.** `app/__init__.py:15` imports `.agent`; `app/agent.py:24-25` builds the pipeline and calls `build_storage()`; `app/runner.py:61` calls `init_schema()`; SQLite creates/migrates at `app/adapters/storage/sqlite_backend.py:42-63`. In this read-only workspace, `import app.core.domain` crashed trying to open the DB, confirming the side effect.

- **Layering inversion:** **AGREE.** `app/pipeline/agents.py:47-54` imports `_collect`, default factories, and `select_rendered` from `app.runner`; `app/runner.py:26-27` imports pipeline modules and defers `build_pipeline` at `app/runner.py:156-158` specifically to avoid a load-time cycle.

- **Render output-key mismatch:** **AGREE.** Backend writes `md/xlsx/html` at `app/pipeline/agents.py:438-440`; frontend expects `html/excel/markdown` at `frontend/components/digests/output-links.tsx:8-19`; `run-detail.tsx:108` passes outputs through unchanged.

**False Positives / Overstatements**

- “Live active keys” is not provable statically. Say “key-shaped plaintext secrets are present on disk.”
- “Firestore fails on first real query” should be “filtered+ordered Firestore news queries likely fail without composite indexes; backend is not live-validated.”
- “Docker ships no UI” should be “ships no Next.js product console”; ADK web UI is enabled.
- “No API serializer for flagged/verdicts” is wrong; API includes `DigestRun`, but frontend schema drops those fields.
- “No per-agent override anywhere” is too broad: `judge_model` exists for offline eval at `app/core/config.py:88-92` and `app/pipeline/judge.py:60-68`. Runtime pipeline stages still use global model/temp.
- Output mismatch affects display badges, not downloads; the component explicitly says files are not served at `frontend/components/digests/output-links.tsx:43-45`.

**Important Misses**

- **Cloud/Docker Firestore cannot work as shipped without installing the optional extra.** `google-cloud-firestore` is optional at `pyproject.toml:42-43`, while Docker runs plain `uv sync --frozen` at `Dockerfile:29`. In this environment `google.cloud.firestore` is not importable, so `STORAGE_BACKEND=firestore` would fail before the missing-index query path unless the image build changes.

- **Browser-exposed API key is not real public-user auth.** Frontend sends `NEXT_PUBLIC_API_KEY` at `frontend/lib/api.ts:49-57`; anything `NEXT_PUBLIC_*` is visible to browser users. Fine for trusted/internal single-user use, not a public web auth model.

- **Local CSRF/run-trigger gap.** The settings surface has Origin/Host loopback checks, but product routes do not. With default open auth, `POST /api/runs` at `app/api/app.py:273-281` requires no body/header, so a malicious web page can likely trigger a local digest run even if CORS prevents reading the response.

- **Unauthenticated feedback logging on deployed entrypoint.** `app/fast_api_app.py:80-91` accepts `/feedback` and writes to Cloud Logging with no API key or rate limit; model fields allow arbitrary `text` at `app/app_utils/typing.py:26-34`.

**Final Verdict**

The report is **mostly trustworthy on direction and prioritization**, but not always calibrated. I endorse these P0/P1 items: fail API closed for non-loopback/deployed entrypoints, add CI, cap response size in `safe_get`, fix import-time side effects, break the runner/pipeline cycle, pick one deploy story, and fix output keys.

I would revise, not reject, the Firestore recommendation: label it experimental now, install extras in any Firestore-capable image, add emulator-backed contract tests, and add indexes before claiming config-only production support. I would also revise the API-key recommendation to say shared API key is a stopgap, not public web authentication.
