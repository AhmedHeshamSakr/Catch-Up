# Plan: "Paste a link" source resolution

> Subagent-driven. Builds offline (network behind injectable boundaries). Branch `feat/source-resolve` (stacked on `feat/quality-safety-net`/PR #9).

**Goal:** Let users add sources by pasting a plain link in the console, instead of needing the exact RSS feed URL or the `UC…` channel id:
- **YouTube:** paste a channel URL or `@handle` → resolve to `channel_id` (resolver already exists).
- **Newspaper:** paste a homepage URL → auto-discover its RSS feed URL.

**Commit identity `AhmedHeshamSakr <a.hesham1221@gmail.com>`, no AI trailers.** `uv` for Python; explicit `git add <paths>` (an untracked Plan 8 doc is parked in the tree — do NOT commit it).

## Approach
A small backend resolver service + one API endpoint the console calls when the user pastes a link; the resolved value pre-fills the existing form field. Both fetches are **SSRF-guarded** (`validate_public_url`) and **injectable** for offline tests.

---

### Task L1 — Backend: feed discovery + resolve endpoint (TDD)
**Files:** create `app/services/feed_discovery.py`; modify `app/api/app.py` + `app/api/schemas.py`; tests `tests/unit/test_feed_discovery.py`, extend `tests/integration/test_api.py` (or wherever API tests live).
- `feed_discovery.discover_feed(url, *, fetch=_fetch) -> str | None`: `validate_public_url(url)` (SSRF), fetch HTML (httpx, the `_HEADERS` UA), parse with BeautifulSoup (already a dep) for `<link rel="alternate" type="application/rss+xml">` OR `type="application/atom+xml"`, return the `href` made absolute via `urljoin(url, href)`; None if no feed link. Injectable `fetch` for tests.
- `app/api/schemas.py`: `ResolveIn{type: str, url: str}`, `ResolveOut{channel_id: str | None = None, url: str | None = None, name: str | None = None}`.
- `app/api/app.py`: `POST /api/sources/resolve` →
  - `type == "youtube"`: `cid = youtube_resolve.resolve_channel_id(body.url)`; if None → `HTTPException(422, "Could not resolve a YouTube channel from that link")`; else `ResolveOut(channel_id=cid)`.
  - `type == "rss"`: `feed = feed_discovery.discover_feed(body.url)`; if None → `HTTPException(422, "No RSS feed found at that URL")`; else `ResolveOut(url=feed)`.
  - else → `HTTPException(400, "resolve not supported for this type")`.
  Make the two service calls injectable into `create_app` (add `resolve_channel_id_fn=...`, `discover_feed_fn=...` params defaulting to the real fns) so API tests run offline with fakes — mirror the existing `run_digest_fn` injection pattern.
- Tests: `discover_feed` parses an `<link rel=alternate rss>` from fixture HTML (injected fetch), handles atom, returns None when absent, SSRF rejects a bad URL; API `POST /api/sources/resolve` for youtube (fake resolver→channel_id), rss (fake discover→url), 422 on None, 400 on bad type. Offline.
- Verify: `uv run pytest tests -q` green; `uv run --extra lint ruff check app tests` clean.

### Task L2 — Frontend: paste-link UX in the Sources form (TDD-light)
**Files:** modify `frontend/lib/api.ts` (+ `frontend/lib/api.test.ts`), `frontend/components/sources/source-form-dialog.tsx`.
- `api.resolveSource(type, url): Promise<{channel_id?: string|null; url?: string|null; name?: string|null}>` → `POST /api/sources/resolve`. Test it (mock fetch) like the other api methods.
- In `source-form-dialog.tsx`, for **youtube** and **rss** types, add a small "paste a link" row: an input (placeholder "Channel URL or @handle" / "Site or feed URL") + a **Resolve** button. On click: `setResolving(true)` → `api.resolveSource(type, link)` → on success fill `channel_id` (youtube) or `url` (rss), and `name` if empty and returned; `toast.success`; on `ApiError` `toast.error(e.message)`; always `setResolving(false)`. Keep the existing channel_id/url field visible (shows the resolved value, still editable).
- Verify: `cd frontend && npm test && npx tsc --noEmit && npm run lint && npm run build` green.

### Task L3 — Docs, final review, PR
- README sources paragraph: note you can paste a channel link/@handle or a site URL and click **Resolve**. BUILD-LOG entry. Final reviewer over the branch. Push + PR (stacked on #9). All commits AhmedHeshamSakr.

## Deferred / notes
- `resolve` endpoint makes outbound fetches on demand (SSRF-guarded); no rate-limit for v1 (admin console). Live resolution validated when used; tests are offline.
- Config-store YAML round-trip drops comments (known); unrelated to this feature.
