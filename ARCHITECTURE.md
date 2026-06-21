# Catch-Up — Architecture

A multi-agent news catch-up platform on the **Google Agent Development Kit (ADK)**.
It collects news from many sources, uses **Gemini** to categorize / score / summarize
(EN + AR) and fact-check, then renders catch-up digests — served through a **Next.js**
console and a **FastAPI** backend. Built to run **free locally** and scale to **Google
Cloud** by configuration, not a rewrite.

---

## System at a glance

Each layer talks to the next through a narrow interface, so any one can change without
breaking the others — swap **SQLite → Firestore** (the one real storage port), flip
**AI Studio → Vertex AI** (env toggle `GOOGLE_GENAI_USE_VERTEXAI`), or drive runs from
**Cloud Scheduler → `POST /api/runs`** instead of in-process APScheduler.

```mermaid
%%{init: {'theme':'base','themeVariables':{'fontFamily':'Inter, system-ui, sans-serif','fontSize':'14px','lineColor':'#94a3b8','primaryTextColor':'#0f172a'}}}%%
flowchart TB
    L1["🖥️&nbsp;&nbsp;CLIENT<br/><br/>Next.js console&nbsp;·&nbsp;Desktop app (Catch-Up.app · PWA · launcher)"]
    L2["⚡&nbsp;&nbsp;API&nbsp;·&nbsp;FastAPI<br/><br/>Product REST API /api/*&nbsp;·&nbsp;ADK deploy surface"]
    L3["🧠&nbsp;&nbsp;ORCHESTRATION&nbsp;·&nbsp;Google ADK<br/><br/>Runner + run_digest()&nbsp;·&nbsp;NewsCatchUpPipeline&nbsp;·&nbsp;Scheduler"]
    L4["🔧&nbsp;&nbsp;SERVICES &amp; DOMAIN<br/><br/>Collectors&nbsp;·&nbsp;Enrichment (LLM)&nbsp;·&nbsp;Render&nbsp;·&nbsp;SSRF / rate guards"]
    G{{"Gemini<br/>AI Studio → Vertex AI"}}
    DB[("Storage<br/>SQLite → Firestore")]
    SS[("ADK sessions<br/>SQLite")]

    L1 -->|HTTP /api| L2
    L2 -->|build &amp; run| L3
    L3 -->|execute stages| L4
    L4 -->|LLM| G
    L4 -->|persist| DB
    L3 -.->|state| SS

    classDef client fill:#eff6ff,stroke:#3b82f6,stroke-width:1.5px,color:#1e3a8a;
    classDef api fill:#f5f3ff,stroke:#8b5cf6,stroke-width:1.5px,color:#5b21b6;
    classDef orch fill:#ecfdf5,stroke:#10b981,stroke-width:1.5px,color:#065f46;
    classDef svc fill:#fffbeb,stroke:#f59e0b,stroke-width:1.5px,color:#92400e;
    classDef model fill:#f0fdfa,stroke:#0d9488,stroke-width:1.5px,color:#115e59;
    classDef store fill:#eef2ff,stroke:#6366f1,stroke-width:1.5px,color:#3730a3;
    class L1 client;
    class L2 api;
    class L3 orch;
    class L4 svc;
    class G model;
    class DB,SS store;
```

<sub>**Shapes** — ▭ layer · ⬡ external model · ⛁ datastore &nbsp;·&nbsp; **Edges** — solid = data flow · dashed = session state. Each layer talks to the next through a narrow interface.</sub>

---

## The agent pipeline

A run is triggered by the **console** (`POST /api/runs`), the **scheduler**, or the
**CLI**. `run_digest()` builds the agent tree and executes it on an **ADK Runner**;
every stage reads and writes shared run state via `EventActions.state_delta`.

```mermaid
%%{init: {'theme':'base','themeVariables':{'fontFamily':'Inter, system-ui, sans-serif','fontSize':'13px','lineColor':'#94a3b8'}}}%%
flowchart TB
    START(["▶&nbsp; run_digest()<br/>ADK Runner"])
    P1(["1 · PipelineInit<br/>create DigestRun"])
    subgraph CS["2 · CollectSources — ParallelAgent · concurrent"]
        direction LR
        C_RSS(["CollectRss"])
        C_SCRAPE(["CollectScrape"])
        C_API(["CollectApi · GNews"])
        C_SEARCH(["CollectSearch · grounding"])
        C_YT(["CollectYoutube"])
    end
    P3(["3 · NormalizeDedup<br/>merge · normalize · dedup"])
    P4(["4 · Processing<br/>category · importance · EN/AR · entities"])
    P5(["5 · GuardrailCritic<br/>faithfulness · flag/redact · reflection"])
    P6(["6 · DigestEditor<br/>narrative — what matters most"])
    P7(["7 · Render<br/>xlsx · HTML · Markdown · finalize"])

    START --> P1
    P1 --> C_RSS & C_SCRAPE & C_API & C_SEARCH & C_YT
    C_RSS & C_SCRAPE & C_API & C_SEARCH & C_YT --> P3
    P3 --> P4 --> P5 --> P6 --> P7

    classDef entry fill:#0f172a,stroke:#0f172a,color:#ffffff,stroke-width:1px;
    classDef stage fill:#ffffff,stroke:#64748b,stroke-width:1.5px,color:#0f172a;
    classDef coll fill:#eff6ff,stroke:#3b82f6,stroke-width:1.2px,color:#1e3a8a;
    classDef llm fill:#ecfdf5,stroke:#10b981,stroke-width:2px,color:#065f46;
    class START entry;
    class P1,P3,P7 stage;
    class C_RSS,C_SCRAPE,C_API,C_SEARCH,C_YT coll;
    class P4,P5,P6 llm;

    style CS fill:#f8fafc,stroke:#cbd5e1,color:#334155
```

<sub>🟩 **green = LLM-backed** (Gemini) &nbsp;·&nbsp; ⚪ white = deterministic stage &nbsp;·&nbsp; 🔵 blue = concurrent collector</sub>

> **At a glance:** one root `SequentialAgent` runs **7 stages** in order. Stage 2 is a
> `ParallelAgent` that fans out to **up to 5 source collectors** concurrently. **3 stages
> are LLM-backed** (Gemini).

---

## Agents at a glance

| # | Agent | ADK type | What it does |
|---|-------|----------|--------------|
| 1 | **PipelineInit** | `BaseAgent` | Creates the `DigestRun` and seeds run state (`run_id`). |
| 2 | **CollectSources** | `ParallelAgent` | Fans out one collector per enabled source type, run concurrently. |
| ↳ | **SourceCollector ×N** | `BaseAgent` | Collects raw items from **one** source type (RSS · Scrape · GNews · Search · YouTube) into its own state key. |
| 3 | **NormalizeDedup** | `BaseAgent` | Merges all collected items, normalizes them, removes duplicates. |
| 4 | **Processing** 🟩 | `BaseAgent` (LLM) | Gemini enrichment: category, importance score, EN + AR summaries, entities, watchlist boosts. |
| 5 | **GuardrailCritic** 🟩 | `BaseAgent` (LLM) | Faithfulness fact-check of high-importance / watchlisted items; flags + redacts unfaithful summaries; bounded re-summarize (reflection). |
| 6 | **DigestEditor** 🟩 | `BaseAgent` (LLM) | Generates the narrative "what matters most" digest summary. |
| 7 | **Render** | `BaseAgent` | Writes Excel / HTML / Markdown outputs and finalizes the run. |

---

## Components by layer

| Layer | Key components |
|-------|----------------|
| **Client** | Next.js 16 console (React 19, Tailwind v4, shadcn/base-ui, SWR), PWA, `Catch-Up.app` single-port desktop launcher. |
| **API** | FastAPI product API `/api/*` (runs, news, sources, watchlist, settings, health, resolve) + the ADK deploy surface. |
| **Orchestration** | ADK `Runner` + `run_digest()` → `NewsCatchUpPipeline`; single-flight run trigger; APScheduler. |
| **Services & domain** | Collectors (`rss`, `scrape`, `newsapi`, `youtube`, `search`, `feed_discovery`), LLM runtime (`app/llm`), enrichment (`processing`, `critic`, `judge`, `digest_editor`), render (Excel/HTML/Markdown), SSRF-guarded `net`, rate limiter, config store. |
| **Models** | Gemini via `google-genai` (AI Studio → Vertex AI). |
| **Storage** | `StorageBackend` port → SQLite (default) / Firestore adapter; ADK sessions via `DatabaseSessionService` (SQLite). |
| **Cross-cutting** | Settings/config, telemetry/observability, security (API key, localhost write-guard, SSRF guard, rate limit), eval + runtime faithfulness guardrail. |

---

## Quality guardrails

Two LLM-as-judge safeguards protect summary quality, sharing one rubric
(`app/prompts/faithfulness_rubric.md`):

- **Offline eval loop** — scores enrichment against a reference dataset on faithfulness,
  category accuracy, importance calibration, and Arabic translation quality.
- **Runtime critic** (stage 5) — fact-checks high-importance / watchlisted items at digest
  time; unfaithful summaries are **never shown** (flagged + redacted), with bounded
  self-correction.

See **[docs/ADK-GUIDE.md](docs/ADK-GUIDE.md)** for the full ADK architecture & integration guide.
