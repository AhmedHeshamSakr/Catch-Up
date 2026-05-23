# Plan 6 — Next.js "Signal" Console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Frontend UI tasks should also consult **frontend-design:frontend-design**.

**Goal:** Build a beautiful, production-grade web console (`frontend/`) in the "Signal" design language that reads digests and configures the agent, consuming the existing FastAPI at `http://localhost:8000`.

**Architecture:** Next.js 15 App Router + TypeScript + Tailwind v4 + shadcn/ui, sibling to `app/`. Client-side data via a typed API client + SWR (cache/revalidate/poll). Theme = Auto/system default via `next-themes`. All tests offline (mocked `fetch`, no backend, no Gemini quota). `next build` is the integration gate.

**Tech Stack:** Next.js 15, React 19, TypeScript, Tailwind CSS v4, shadcn/ui, next-themes, SWR, lucide-react, Inter + IBM Plex Mono (`next/font`), Vitest + React Testing Library + jsdom.

**Commit identity (MANDATORY):** every commit authored `AhmedHeshamSakr <a.hesham1221@gmail.com>` — NO Claude / Co-Authored-By trailers. Verify with `git log --format='%an <%ae>' -1` after each commit.

---

## Design language — "Signal" (binding contract)

- **Type:** Inter (UI), IBM Plex Mono (numerics/tabular figures — stats, counts, dates, scores).
- **Accents:** emerald `#059669` (light) / `#34D399` (dark); cyan `#0891B2`. Semantic importance: HIGH red `#DC2626`, MEDIUM amber `#A16207`, LOW cyan `#0E7490`.
- **Theme:** light + dark, **default Auto = system** (`prefers-color-scheme`); persisted user override; no flash on load.
- **Icons:** Lucide outline only — **no emoji** anywhere in the UI.
- **Grid:** 8-pt spacing; AA contrast; rounded-xl (12px) cards; 1px hairline borders.
- **Shell:** enterprise left sidebar — brand lockup ("Catch-Up") + workspace switcher (single "Default workspace" now; multi-tenant entry point) + grouped nav + profile footer with theme toggle.

### Token reference (CSS variables, mirrors `app/services/render/html.py`)

Light: `--bg:#F4F6F9 --surface:#fff --line:#E6EBF1 --ink:#0B1220 --sub:#64748B --emerald:#059669 --cyan:#0891B2`
Dark: `--bg:#0B1220 --surface:#111A2B --line:#1E2A3D --ink:#E6EBF1 --sub:#94A3B8 --emerald:#34D399 --cyan:#22D3EE`

---

## API contract (fixed — do not change the backend in this plan)

Base URL: `process.env.NEXT_PUBLIC_API_BASE` (default `http://localhost:8000`). CORS already allows `http://localhost:3000`.

| Method | Path | Returns | Notes |
|---|---|---|---|
| GET | `/api/health` | `{status:"ok"}` | liveness pill in sidebar footer |
| GET | `/api/dashboard` | `DashboardOut` | `latest_run`, `recent_runs[]`, `category_counts{}`, `total_items` |
| GET | `/api/runs?limit=` | `DigestRun[]` | |
| GET | `/api/runs/{run_id}` | `RunDetail` | `{run, items[]}`; 404 → not found |
| GET | `/api/news?category=&importance=&limit=` | `NewsItem[]` | filters optional |
| GET | `/api/sources` | `SourceConfig[]` | |
| PUT | `/api/sources` (body: `SourceConfig[]`) | `{status,count}` | full-list replace (YAML round-trip) |
| GET | `/api/watchlist` | `Watchlist` | `{entities[], keywords[]}` |
| PUT | `/api/watchlist` (body: `Watchlist`) | `{status:"ok"}` | |
| POST | `/api/runs` | `{status:"started"}` (202) | async trigger; needs Gemini quota to fully enrich |

### TypeScript types (mirror the Pydantic models exactly — field names verbatim)

```ts
// lib/types.ts
export type SourceType = "rss" | "scrape" | "api" | "search";
export type Category = "ai_tech" | "business_finance" | "world_geopolitics" | "gulf_mena";
export type Importance = "low" | "medium" | "high";
export type Sentiment = "positive" | "neutral" | "negative";
export type RunStatus = "running" | "success" | "partial" | "failed";

export interface Entity { name: string; type: string; }

export interface NewsItem {
  id: string;
  org_id: string;
  user_id: string;
  source_id: string;
  source_type: SourceType;
  source_name: string;
  url: string;
  title: string;
  excerpt: string | null;
  published_at: string | null;
  collected_at: string;
  category: Category | null;
  summary_en: string | null;
  summary_ar: string | null;
  importance: Importance | null;
  importance_score: number | null;
  entities: Entity[];
  sentiment: Sentiment | null;
  language: string | null;
  status: string;
  digest_run_id: string | null;
}

export interface DigestRun {
  run_id: string;
  org_id: string;
  started_at: string;
  finished_at: string | null;
  status: RunStatus;
  collected: number;
  new: number;
  processed: number;
  high_importance: number;
  outputs: Record<string, string>;   // {"markdown": "...path", "excel": "...", "html": "..."}
  source_errors: { [k: string]: unknown }[];
  narrative: string | null;
}

export interface DashboardOut {
  latest_run: DigestRun | null;
  recent_runs: DigestRun[];
  category_counts: Record<string, number>;
  total_items: number;
}

export interface RunDetail { run: DigestRun; items: NewsItem[]; }

export interface SourceConfig {
  id: string;
  type: SourceType;
  name: string;
  url: string | null;
  query: string | null;
  category_hint: Category | null;
  selector: string | null;
  lang: string | null;
  country: string | null;
  enabled: boolean;
}

export interface Watchlist { entities: string[]; keywords: string[]; }
```

### Display label maps (single source of truth, in `lib/labels.ts`)

```ts
export const CATEGORY_LABELS: Record<Category, string> = {
  ai_tech: "AI & Technology",
  business_finance: "Business & Finance",
  world_geopolitics: "World & Geopolitics",
  gulf_mena: "Gulf & MENA",
};
export const SOURCE_TYPE_LABELS: Record<SourceType, string> = {
  rss: "RSS", scrape: "Web Scrape", api: "News API", search: "Search Grounding",
};
export const IMPORTANCE_LABELS: Record<Importance, string> = {
  high: "High", medium: "Medium", low: "Low",
};
```

---

## File structure

```
frontend/
  package.json  tsconfig.json  next.config.ts  postcss.config.mjs
  eslint.config.mjs  vitest.config.ts  vitest.setup.ts
  components.json                    # shadcn config
  .env.local.example                 # NEXT_PUBLIC_API_BASE=http://localhost:8000
  app/
    layout.tsx                       # fonts + ThemeProvider + AppShell
    globals.css                      # Tailwind + Signal tokens (light/dark)
    page.tsx                         # Dashboard
    digests/page.tsx                 # runs list
    digests/[runId]/page.tsx         # run detail
    news/page.tsx                    # filterable news feed
    sources/page.tsx                 # sources CRUD
    watchlist/page.tsx               # watchlist editor
  components/
    ui/                              # shadcn primitives (button, card, table, badge, input, select, switch, dialog, skeleton, sonner, ...)
    layout/app-shell.tsx  sidebar.tsx  theme-provider.tsx  theme-toggle.tsx  health-pill.tsx  run-now-button.tsx  page-header.tsx
    dashboard/stat-card.tsx  category-breakdown.tsx  run-health-card.tsx
    common/importance-badge.tsx  status-badge.tsx  empty-state.tsx  error-state.tsx
  lib/
    types.ts  labels.ts  api.ts  hooks.ts  utils.ts  format.ts
  __tests__/                         # or co-located *.test.ts(x)
    api.test.ts  format.test.ts  importance-badge.test.tsx  sources-page.test.tsx
```

---

### Task 1: Scaffold Next.js + Signal foundation (shell, theme, fonts, tokens)

**Files:**
- Create: `frontend/` (via `create-next-app`), then customize `app/globals.css`, `app/layout.tsx`
- Create: `components/layout/theme-provider.tsx`, `theme-toggle.tsx`, `app-shell.tsx`, `sidebar.tsx`, `health-pill.tsx`, `page-header.tsx`
- Create: `lib/utils.ts`, `lib/types.ts`, `lib/labels.ts`, `frontend/.env.local.example`

- [ ] **Step 1: Scaffold the app** (run from repo root; do NOT pre-create `frontend/`)

```bash
cd "$(git rev-parse --show-toplevel)"
npx create-next-app@latest frontend \
  --typescript --tailwind --eslint --app --src-dir=false \
  --import-alias "@/*" --use-npm --no-turbopack --yes
```
Expected: `frontend/` created, `npm install` completes.

- [ ] **Step 2: Add deps + init shadcn/ui**

```bash
cd frontend
npm install next-themes swr lucide-react
npm install -D vitest @vitejs/plugin-react jsdom @testing-library/react @testing-library/jest-dom @testing-library/user-event
npx shadcn@latest init -d
npx shadcn@latest add button card table badge input select switch dialog skeleton sonner separator dropdown-menu tabs label
```
Expected: `components/ui/*` and `components.json` exist. (If `shadcn init` prompts despite `-d`, accept defaults: New York style, neutral base, CSS variables yes.)

- [ ] **Step 3: Write Signal tokens into `app/globals.css`**

Replace the theme layer with the Signal palette. Define CSS variables for `:root` (light) and `.dark`, mapping shadcn's `--background/--foreground/--card/--border/--muted-foreground/--primary` to the Signal tokens above; add `--emerald`, `--cyan`, `--ring` (emerald). Set `--radius: 0.75rem`. Import fonts via `next/font` (Step 4) — do NOT use `@import` from Google in CSS.

- [ ] **Step 4: Fonts + ThemeProvider + shell in `app/layout.tsx`**

```tsx
import { Inter, IBM_Plex_Mono } from "next/font/google";
const inter = Inter({ subsets: ["latin"], variable: "--font-sans" });
const mono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400","500","600"], variable: "--font-mono" });
// <html lang="en" suppressHydrationWarning className={`${inter.variable} ${mono.variable}`}>
//   <body><ThemeProvider attribute="class" defaultTheme="system" enableSystem>
//     <AppShell>{children}</AppShell><Toaster /></ThemeProvider></body>
```
`theme-provider.tsx` wraps `next-themes` `ThemeProvider` as a client component. `defaultTheme="system" enableSystem` ⇒ Auto = system default.

- [ ] **Step 5: Build the enterprise sidebar + shell** (consult frontend-design:frontend-design)

`sidebar.tsx` (client, uses `usePathname` for active state): brand lockup (a small inline SVG mark + "Catch-Up" wordmark), a workspace switcher row ("Default workspace", chevron, non-functional placeholder), grouped nav with Lucide icons —
- **Overview:** Dashboard (`LayoutDashboard`, `/`), Digests (`FileText`, `/digests`), News (`Newspaper`, `/news`)
- **Configure:** Sources (`Rss`, `/sources`), Watchlist (`Star`, `/watchlist`)

Footer: `HealthPill` (polls `/api/health`), `ThemeToggle` (Sun/Moon/Monitor via dropdown → light/dark/system), and a profile row ("Default user"). `app-shell.tsx`: fixed sidebar (w-64) + scrollable main with max-width content. Responsive: sidebar collapses to a sheet/drawer under `md`.

- [ ] **Step 6: `theme-toggle.tsx` + `health-pill.tsx` + `page-header.tsx` + `lib/utils.ts`, `lib/types.ts`, `lib/labels.ts`, `.env.local.example`**

`page-header.tsx`: title + optional subtitle + right-slot for actions. `lib/utils.ts`: keep shadcn's `cn`. `types.ts`/`labels.ts`: paste the blocks above. `.env.local.example`: `NEXT_PUBLIC_API_BASE=http://localhost:8000`. Temporarily render placeholder content in `app/page.tsx` ("Dashboard — coming up").

- [ ] **Step 7: Lint, typecheck, build**

```bash
npm run lint && npx tsc --noEmit && npm run build
```
Expected: all pass; build succeeds. Start `npm run dev`, confirm shell renders in both themes (toggle) and Auto follows the OS.

- [ ] **Step 8: Add `frontend/.gitignore` coverage + commit** (create-next-app adds one; verify `node_modules`, `.next`, `.env.local` ignored)

```bash
cd "$(git rev-parse --show-toplevel)"
git add frontend
git commit -m "feat(console): scaffold Next.js Signal shell — sidebar, theme (auto/system), fonts, tokens"
git log --format='%an <%ae>' -1   # must show AhmedHeshamSakr <a.hesham1221@gmail.com>
```

---

### Task 2: Typed API client + SWR hooks (TDD, offline)

**Files:**
- Create: `frontend/lib/api.ts`, `frontend/lib/hooks.ts`, `frontend/lib/format.ts`
- Create: `frontend/vitest.config.ts`, `frontend/vitest.setup.ts`
- Test: `frontend/lib/api.test.ts`, `frontend/lib/format.test.ts`
- Modify: `frontend/package.json` (add `"test": "vitest run"`, `"test:watch": "vitest"`)

- [ ] **Step 1: Vitest config**

`vitest.config.ts`: `@vitejs/plugin-react`, `environment: "jsdom"`, `setupFiles: ["./vitest.setup.ts"]`, alias `@` → repo `frontend` root. `vitest.setup.ts`: `import "@testing-library/jest-dom/vitest"`.

- [ ] **Step 2: Write failing tests for the API client**

```ts
// lib/api.test.ts
import { describe, it, expect, vi, beforeEach } from "vitest";
import { api } from "@/lib/api";

beforeEach(() => { vi.restoreAllMocks(); process.env.NEXT_PUBLIC_API_BASE = "http://test"; });

it("getDashboard hits /api/dashboard and returns parsed json", async () => {
  const payload = { latest_run: null, recent_runs: [], category_counts: {}, total_items: 0 };
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(payload), { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  const out = await api.getDashboard();
  expect(fetchMock).toHaveBeenCalledWith("http://test/api/dashboard", expect.any(Object));
  expect(out.total_items).toBe(0);
});

it("listNews builds query string from filters", async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response("[]", { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  await api.listNews({ category: "ai_tech", importance: "high", limit: 25 });
  expect(fetchMock.mock.calls[0][0]).toBe("http://test/api/news?category=ai_tech&importance=high&limit=25");
});

it("putSources sends PUT with JSON body", async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: "ok", count: 1 }), { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  await api.putSources([{ id: "s", type: "rss", name: "S", url: "https://x", query: null, category_hint: null, selector: null, lang: null, country: null, enabled: true }]);
  const [, opts] = fetchMock.mock.calls[0];
  expect(opts.method).toBe("PUT");
  expect(JSON.parse(opts.body)[0].id).toBe("s");
});

it("throws ApiError on non-2xx", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("nope", { status: 500 })));
  await expect(api.getDashboard()).rejects.toThrow();
});
```
Run: `npm test` → FAIL (module not found).

- [ ] **Step 3: Implement `lib/api.ts`**

A `request<T>(path, init?)` helper: `const base = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000"`; `fetch(base + path, { headers: { "Content-Type": "application/json" }, ...init })`; on `!res.ok` throw `ApiError(status, text)`; else `res.json()`. Export `api` with: `getDashboard()`, `listRuns(limit?)`, `getRun(id)`, `listNews(filters?)` (build querystring, omit undefined), `getSources()`, `putSources(list)`, `getWatchlist()`, `putWatchlist(wl)`, `triggerRun()`. Type each with the interfaces from `lib/types.ts`.

- [ ] **Step 4: Run tests → PASS** (`npm test`).

- [ ] **Step 5: Formatters + tests**

`lib/format.test.ts` then `lib/format.ts`:
```ts
formatDateTime("2026-05-24T09:30:00Z") // → "24 May 2026, 09:30 UTC"
formatRelative(isoInPast)              // → "2h ago" / "just now"
scorePct(0.42)                          // → "42%"; scorePct(null) → "—"
```
Tests assert exact outputs (use fixed ISO inputs; for `formatRelative` inject `now`). Run → PASS.

- [ ] **Step 6: SWR hooks `lib/hooks.ts`**

`useDashboard()`, `useRuns(limit?)`, `useRun(id)`, `useNews(filters)`, `useSources()`, `useWatchlist()` — thin `useSWR(key, () => api.X())` wrappers. `useDashboard` sets `refreshInterval: 15000` (live run status). Export a typed `{ data, error, isLoading, mutate }` shape.

- [ ] **Step 7: Commit**

```bash
git add frontend/lib frontend/vitest.config.ts frontend/vitest.setup.ts frontend/package.json frontend/package-lock.json
git commit -m "feat(console): typed API client + SWR hooks + formatters (offline tests)"
```

---

### Task 3: Dashboard screen

**Files:**
- Create: `app/page.tsx` (replace placeholder), `components/dashboard/stat-card.tsx`, `category-breakdown.tsx`, `run-health-card.tsx`
- Create: `components/common/status-badge.tsx`, `importance-badge.tsx`, `empty-state.tsx`, `error-state.tsx`, `components/layout/run-now-button.tsx`
- Test: `components/common/importance-badge.test.tsx`

- [ ] **Step 1: Common badges + states (consult frontend-design)**

`importance-badge.tsx`: maps `Importance` → label + semantic color (HIGH red / MEDIUM amber / LOW cyan) pill; `null` → nothing. `status-badge.tsx`: `RunStatus` → colored pill (success=emerald, partial=amber, failed=red, running=cyan w/ pulse). `empty-state.tsx` / `error-state.tsx`: centered icon + message + optional action.

- [ ] **Step 2: Failing test for ImportanceBadge**

```tsx
// components/common/importance-badge.test.tsx
import { render, screen } from "@testing-library/react";
import { ImportanceBadge } from "@/components/common/importance-badge";
it("renders High label for high importance", () => {
  render(<ImportanceBadge importance="high" />);
  expect(screen.getByText("High")).toBeInTheDocument();
});
it("renders nothing for null", () => {
  const { container } = render(<ImportanceBadge importance={null} />);
  expect(container).toBeEmptyDOMElement();
});
```
Run → FAIL, then implement → PASS.

- [ ] **Step 3: `run-now-button.tsx`** (client): button (Lucide `Play`) → `api.triggerRun()` → on success `toast.success("Run started — enrichment needs a Gemini key")` and `mutate` dashboard; disable while pending. Lives in the dashboard `PageHeader` right-slot and top of `/digests`.

- [ ] **Step 4: Dashboard page** (`"use client"`, uses `useDashboard()`)

Layout: `PageHeader title="Dashboard"` + `RunNowButton`. Then:
- Stat row (4 `StatCard`s, mono numerals): Total items (`total_items`), Latest run status (`latest_run.status` via StatusBadge), New in latest (`latest_run.new`), High-importance (`latest_run.high_importance`).
- "What matters most" lead card: `latest_run.narrative` (emerald left-border, mirrors HTML renderer) or empty hint.
- Two columns: `CategoryBreakdown` (bars from `category_counts` using `CATEGORY_LABELS`, mono counts) + `RunHealthCard` (last run: started/finished, collected→new→processed, `source_errors` count, link to detail).
- Loading → `Skeleton`s; error → `ErrorState`; no runs → `EmptyState` ("No digests yet — Run now").

- [ ] **Step 5: Verify** — `npm test`, `npx tsc --noEmit`, `npm run build`. With API running (`uv run python -m app.cli serve`) + `npm run dev`, confirm dashboard renders real data, both themes.

- [ ] **Step 6: Commit** — `git commit -m "feat(console): dashboard — stats, narrative, category breakdown, run health, run-now"`

---

### Task 4: Digests list + run detail

**Files:**
- Create: `app/digests/page.tsx`, `app/digests/[runId]/page.tsx`
- Create: `components/digests/run-row.tsx` (or inline table), `components/digests/news-card.tsx`, `components/digests/output-links.tsx`

- [ ] **Step 1: Digests list** (`useRuns()`): `PageHeader title="Digests"` + RunNowButton. shadcn `Table`: columns Started (mono datetime), Status (StatusBadge), Collected/New/Processed (mono), High (mono), Outputs (count). Row → links to `/digests/[runId]`. Empty/loading/error states.

- [ ] **Step 2: `news-card.tsx`** — reusable item card (used here + News page): title (links to `item.url`, new tab, `rel="noopener noreferrer"`), source_name, ImportanceBadge, `summary_en`, optional Arabic `summary_ar` (render with `dir="rtl"` and mono-agnostic, in a muted sub-block), entities as small chips, sentiment dot. **All text from the API is escaped by React by default — never use `dangerouslySetInnerHTML`.**

- [ ] **Step 3: `output-links.tsx`** — given `run.outputs` (`{markdown,excel,html}`), render download/open links. Outputs are server filesystem paths from the API; the console cannot read the server FS directly, so render them as **labelled, disabled-with-tooltip** entries showing the filename + a note "available on the API host" UNLESS a future download endpoint exists. (Do not invent an endpoint; show the path read-only via `basename`.)

- [ ] **Step 4: Run detail** (`app/digests/[runId]/page.tsx`, `useRun(id)`): header with run_id (mono, truncated), StatusBadge, started/finished, the four counters, `source_errors` (if any) in a small warning card listing each error dict's `source_id`/`error`. Narrative lead card. Then items grouped by category (order: ai_tech, business_finance, world_geopolitics, gulf_mena, then uncategorized) using `NewsCard`. 404 → `EmptyState` "Run not found". OutputLinks in the header.

- [ ] **Step 5: Verify + commit** — tests/typecheck/build pass; `git commit -m "feat(console): digests list + run detail with grouped items and outputs"`

---

### Task 5: Sources CRUD

**Files:**
- Create: `app/sources/page.tsx`, `components/sources/source-form-dialog.tsx`, `components/sources/source-table.tsx`
- Test: `app/sources/sources-page.test.tsx` (or `components/sources/source-form-dialog.test.tsx`)

- [ ] **Step 1: Sources table** (`useSources()`): columns Name, Type (`SOURCE_TYPE_LABELS` badge), Category hint (`CATEGORY_LABELS` or "—"), Target (url or query or selector, truncated/mono), Enabled (shadcn `Switch` — toggling persists immediately via full-list `putSources` then `mutate`). Row actions: Edit, Delete (with confirm `Dialog`).

- [ ] **Step 2: Add/Edit dialog** (`source-form-dialog.tsx`): fields id, name, type (`Select`), category_hint (`Select`, optional), and **type-conditional** fields — `rss`/`scrape`: url; `scrape` also selector; `api`: query + optional lang/country; `search`: query. enabled `Switch`. Validate required fields per type client-side. Save = mutate the in-memory list then `putSources(fullList)` (the API replaces the whole list) → toast + `mutate`.

- [ ] **Step 3: Failing test** — render the dialog, choose type "scrape", assert the `selector` field appears (and is absent for type "rss"). Run → FAIL, implement → PASS.

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SourceFormDialog } from "@/components/sources/source-form-dialog";
it("shows selector field only for scrape type", async () => {
  render(<SourceFormDialog open onOpenChange={() => {}} source={null} onSave={async () => {}} />);
  expect(screen.queryByLabelText(/selector/i)).not.toBeInTheDocument();
  await userEvent.click(screen.getByLabelText(/type/i));
  await userEvent.click(screen.getByText("Web Scrape"));
  expect(screen.getByLabelText(/selector/i)).toBeInTheDocument();
});
```
(If shadcn `Select` is hard to drive in jsdom, test the pure `fieldsForType(type)` helper instead and keep the component thin.)

- [ ] **Step 4: Verify + commit** — `git commit -m "feat(console): sources CRUD with type-aware form and live enable toggle"`

---

### Task 6: Watchlist editor + News feed

**Files:**
- Create: `app/watchlist/page.tsx`, `app/news/page.tsx`
- Create: `components/watchlist/tag-editor.tsx`

- [ ] **Step 1: `tag-editor.tsx`** — controlled tag input: list of removable chips + an input that adds on Enter/comma; dedupes case-insensitively; empty state.

- [ ] **Step 2: Watchlist page** (`useWatchlist()`): two `TagEditor`s — Entities (companies/people) and Keywords — in cards with a short explainer ("matches boost importance by +0.25"). A single "Save changes" button (dirty-tracked) → `putWatchlist({entities, keywords})` → toast + `mutate`. Loading/error states.

- [ ] **Step 3: News feed** (`app/news/page.tsx`, `useNews(filters)`): `PageHeader title="News"`. Filter bar: Category `Select` (All + 4), Importance `Select` (All + 3), limit. Grid/list of `NewsCard`. Filters update SWR key → refetch. Empty/loading/error states.

- [ ] **Step 4: Verify + commit** — `git commit -m "feat(console): watchlist editor + filterable news feed"`

---

### Task 7: Polish, docs, and final gate

**Files:**
- Modify: `README.md` (Console section), `docs/BUILD-LOG.md` (Plan 6 entry)
- Modify: any rough screens for empty/loading/error parity, responsive, a11y

- [ ] **Step 1: Consistency pass** — every screen has Skeleton loading, ErrorState, EmptyState; mono font on all numerics/dates; keyboard focus rings (emerald); `aria-label`s on icon-only buttons; sidebar drawer works under `md`; no emoji anywhere; no `dangerouslySetInnerHTML`.

- [ ] **Step 2: Full gate**

```bash
cd frontend && npm run lint && npx tsc --noEmit && npm test && npm run build
```
Expected: all green. Then manual smoke against a live API (`uv run python -m app.cli serve` in repo root) for all five screens in light, dark, and Auto.

- [ ] **Step 3: README — add a "Web Console" section**

Document: `cd frontend && npm install && cp .env.local.example .env.local && npm run dev` → http://localhost:3000 (API must run on :8000). Note Auto/system theme, the screens, and that "Run now" needs a Gemini key for enrichment.

- [ ] **Step 4: BUILD-LOG — append Plan 6 entry** (under a new `### Phase: Execution — Plan 6 (Next.js Console) ✅`): batches, commits, the API-backed scope decision (4 screens + news; Categories/Pipeline/Schedule/Settings deferred to later plans needing new endpoints), test count, and the gate results. Update `### Next`.

- [ ] **Step 5: Commit docs** — `git commit -m "docs: document the web console + log Plan 6 execution"`

- [ ] **Step 6: Final review + PR** — dispatch a final code reviewer over the whole `feat/console` diff, then use **superpowers:finishing-a-development-branch** → push + open PR #6 (`feat/console` → `main`), body summarizing screens + scope + test/gate results. All commits authored `AhmedHeshamSakr <a.hesham1221@gmail.com>`.

---

## Self-review checklist (run before execution)

- **Spec coverage:** Dashboard ✓(T3) · Digests ✓(T4) · Sources ✓(T5) · Watchlist ✓(T6) · News ✓(T6); Signal design language (fonts/colors/theme/icons/sidebar) ✓(T1). Categories/Pipeline/Schedule/Settings explicitly deferred (need new API endpoints) — noted in scope.
- **API field names** match Pydantic exactly (`summary_en/ar`, `importance_score`, `digest_run_id`, `category_counts`, `source_errors`, `high_importance`, `outputs`). ✓
- **Quota-free:** only "Run now" (`POST /api/runs`) touches Gemini; all tests mock `fetch`. ✓
- **Security:** React auto-escaping (no `dangerouslySetInnerHTML`), external links `rel="noopener noreferrer"`, read-only output paths (no invented endpoints). ✓
- **Commit identity:** AhmedHeshamSakr <a.hesham1221@gmail.com>, no AI trailers — verified per commit. ✓
- **Type consistency:** `api.*` method names match `hooks.ts` and screen usage; label maps keyed by the same string enums. ✓
