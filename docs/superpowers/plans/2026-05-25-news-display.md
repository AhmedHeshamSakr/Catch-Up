# News Display Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Checkbox steps. **frontend/AGENTS.md applies: read the relevant guide in `node_modules/next/dist/docs/` before writing any frontend code** (this Next.js has breaking changes vs training data).

**Goal:** Make collected articles clean, scannable, and triage-first ("info on the go"): a **Prioritized Briefing** layout, with an optional **per-article image**, and EN/AR display by **user language preference (English default)**. Applies to the News page and Digest detail (shared `NewsCard`).

**Branch:** `feat/news-display` off `main`. Constraints: commit `AhmedHeshamSakr <a.hesham1221@gmail.com>`, NO AI trailers. Backend via `uv`; frontend `npm` from `frontend/`. Keep baselines green (backend 293+1skip, frontend 48). Do NOT change the model alias.

---

## UI/UX principles this design applies (think-before-execution)
1. **Visual hierarchy** — the eye lands on priority then headline then takeaway. Since items have **no reliable image**, hierarchy comes from importance grouping + category color + typographic contrast (research: hierarchy via size/contrast/position).
2. **Triage-first / glanceability** — group by importance (Top → Notable → More), so "what matters" is at the top; LOW collapsed by default.
3. **Make the information the hero** — promote the summary/takeaway from muted-gray to primary text, clamped (~2–3 lines) so cards stay even and scannable.
4. **Progressive disclosure** — card shows the takeaway; expand reveals full summary, the other-language summary, all entities, score. Reduces clutter without losing depth.
5. **Minimal chrome** — subtle ring/border, generous whitespace, 8px rhythm; no heavy shadows (research: heavy chrome = noise).
6. **Graceful media** — image only if present AND a valid http(s) URL; lazy-loaded, fixed aspect box (no layout shift / CLS), **hidden on load error** (news hotlinks 404 often). Plain `<img>` (not Next `<Image>`) because images come from arbitrary domains we can't whitelist and we must not make our server proxy/fetch them.
7. **Bilingual, first-class** — EN/AR by preference (default EN); AR rendered `dir="rtl" lang="ar"`; fall back to the other language (then excerpt) if the preferred one is missing.
8. **Accessibility** — `focus-visible` rings on interactive rows; non-color cues kept (sentiment icon, importance text); `alt` on images; expand control is a real `<button>` with `aria-expanded`; AA contrast (reuse `--link`, importance tokens).
9. **Responsive** — single column + large tap targets on mobile; comfortable max width on desktop; image scales/hides sensibly on narrow screens.
10. **Performance** — `loading="lazy"` + `decoding="async"` on images; clamp via CSS line-clamp; no per-card effects (use `useSyncExternalStore` for the pref to satisfy the repo's `react-hooks/set-state-in-effect: error`).

---

## N1 — Backend: per-article image extraction
**Files:** `app/core/domain.py` (RawItem/NewsItem `image_url`), `app/services/{rss,scrape,newsapi,youtube}.py`, `app/services/normalize.py` (carry image_url onto NewsItem), `app/services/net.py` or a helper for `is_http_url` validation; tests in `tests/unit/`.

- [ ] Add `image_url: str | None = None` to `RawItem` and `NewsItem` (and `NewsItem.from_raw` carries it). Validate it's `http(s)` when set (reuse the scheme check used by the API URL validators; non-http(s) → store None).
- [ ] **RSS** (`rss.py` parse): extract from feedparser `entry.media_thumbnail` / `entry.media_content` (image types) / `entry.enclosures` (type startswith `image/`) / `<link rel="enclosure">`. First valid http(s) wins.
- [ ] **YouTube** (`youtube.py` parse): channel feed entries carry `media_thumbnail` (video thumbnail) — almost always present; extract it.
- [ ] **GNews** (`newsapi.py`): the API item's `image` field.
- [ ] **Scrape** (`scrape.py`): parse `<meta property="og:image">` (and `twitter:image` fallback) from the fetched page (BeautifulSoup already in use).
- [ ] Search grounding: no image (leave None).
- [ ] Thread `image_url` through normalize/dedup → storage (it's in the NewsItem JSON `data`, so storage/API already serialize it — confirm `NewsItem` round-trips). No projected column needed.
- [ ] Tests (offline, fixtures): each collector extracts image_url from a fixture with media/og:image, and yields None when absent or non-http(s). Keep existing collector tests green.

## N2 — Frontend: language preference (EN default)
**Files:** `frontend/lib/use-language.ts` (new), a toggle control component, wire into header or news page; `frontend/lib/types.ts` (`image_url` on NewsItem type + zod schema in `lib/schemas.ts`).
- [ ] Add `image_url?: string | null` to the `NewsItem` TS type and the zod `newsItemSchema` (so validation doesn't strip/reject it).
- [ ] `useLanguage()` hook backed by **`useSyncExternalStore`** reading `localStorage["catchup.lang"]` (`"en" | "ar"`, default `"en"`, `getServerSnapshot` → `"en"` to avoid hydration mismatch). Setter writes localStorage + notifies subscribers (storage event / custom event). NO `useEffect` setState (respects the lint).
- [ ] A small **EN | AR** segmented toggle (accessible: `role="group"`, `aria-pressed`), placed in the app header (so it's global) or the News PageHeader actions. Default EN highlighted.
- [ ] Unit tests: hook returns "en" by default, persists/reads a set value; toggle renders + switches.

## N3 — Frontend: Prioritized-Briefing NewsCard + image + grouping
**Files:** `frontend/components/digests/news-card.tsx` (redesign), `frontend/app/news/page.tsx` (grouping), `frontend/app/digests/[runId]/page.tsx` (use grouped layout), maybe `frontend/components/digests/news-group.tsx` (new), `frontend/lib/labels.ts` (category colors), tests.
- [ ] **Category color** map (token-based, light/dark safe) for a left accent + category chip.
- [ ] **Card layout:** [optional thumbnail] | { importance chip + category chip + sentiment icon · headline link (bold) · **takeaway (primary text, line-clamp ~3)** in the preferred language (EN default; fall back) · compact `source · time` · score subtle }. Expand button (`aria-expanded`) reveals: full summary, the other-language summary (RTL for AR), all entities, score.
- [ ] **Image:** render only if `item.image_url` is a valid http(s) string; fixed box (e.g. `h-16 w-16` mobile / `h-20 w-28` desktop, `object-cover rounded-lg`), `loading="lazy"`, `decoding="async"`, `alt={item.title}`; on `onError` set local `imageError` state → hide (no broken-image icon). Plain `<img>`.
- [ ] **Grouping** in `news/page.tsx`: client-side group items into HIGH (Top stories) / MEDIUM (Notable) / LOW (More, collapsed `<details>` or toggle), each sorted by `importance_score` desc; section headers in the Signal style. Keep the existing filters working (filtering then grouping). Empty/loading/error via existing `AsyncBoundary`.
- [ ] Apply the same `NewsCard` (and ideally grouping) in the Digest detail page.
- [ ] **Visual styling pass:** spacing rhythm, category accents, hover/focus states, even card heights via clamp; keep it on-brand (Signal tokens, emerald/cyan, Inter/IBM Plex Mono).
- [ ] Update the `NewsCardSkeleton` to match the new layout (incl. optional thumb block).
- [ ] Tests (Vitest+RTL): renders EN by default; switches to AR on preference; shows image when present, hides when absent/onError; groups by importance; expand reveals detail; keys stable. Keep all existing FE tests green.

## Final
- Backend gate (`uv run pytest tests -q`, ruff) + frontend gate (`npm run lint && npx tsc --noEmit && npm test`) all green. Update `docs/BUILD-LOG.md` + memory. PR `feat/news-display → main` (delete branch on merge). Follow-up (noted): server-side `og:image` for RSS items that only have it on the article page (currently only scrape reads og:image).
