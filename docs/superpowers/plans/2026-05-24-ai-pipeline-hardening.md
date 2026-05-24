# AI-Pipeline Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Checkbox steps.

**Goal:** Fix every finding from the AI-engineering review (guardrail integrity, LLM-call robustness, eval rigor, orchestration, prompts) without regressing the green baseline (214 backend / 48 frontend tests). Work continues on the open branch `fix/review-remediation` (PR #15).

**Constraints:** Run Python via `uv`; lint `uv run --extra lint ruff check app tests scripts`. Commit `AhmedHeshamSakr <a.hesham1221@gmail.com>`, NO AI trailers. Do NOT change the model alias `gemini-flash-latest`. TDD; keep all existing tests green.

---

## G1 — Guardrail integrity (the 3 reds)
1. **Fail-closed critic.** Add `Settings.critic_fail_mode: Literal["open","closed"] = "closed"`. In `GuardrailCriticAgent._run_async_impl` (agents.py), on critic exception: if closed, flag+redact every `selected` item (treat as unfaithful), append a `{"stage":"critic","degraded":true,...}` error so the run is PARTIAL. If open, current behavior.
2. **API never serves flagged items.** Add a projected `status` column to `news_items` (idempotent `_ensure_columns` migration, populate in `save_items`). `get_items_for_run` and `list_news` exclude `status='flagged'` by default with an `include_flagged: bool = False` param for audit. Verify dashboard counts also exclude flagged.
3. **Redact unfaithful text.** In `apply_verdicts` (critic.py), for any item judged unfaithful (flag/downrank, and replace-fallback), redact `summary_en`/`summary_ar` to a withheld-notice constant so the hallucinated text never persists/serves. `replace` with a valid `suggested_summary_en` stays faithful (keep text, status processed).
Tests: critic-exception→items flagged+run degraded (fail-closed); API run-detail/news omit flagged; unfaithful item's summary redacted.

## G2 — LLM robustness wrapper
- New `app/llm/parse.py` `parse_model_json(text, Model)`: strip ```` ```json ```` fences, extract first balanced `{...}`/`[...]`, `Model.model_validate_json`; raise typed `LLMOutputError` on empty/garbage.
- `run_agent_text` (app/llm/runtime.py): per-call `asyncio.wait_for(timeout=settings.llm_timeout)`, bounded retry (`settings.llm_max_retries`) with exponential backoff+jitter on transient/empty; raise typed error after exhaustion.
- Apply `parse_model_json` at all parse sites: processing/critic/judge/editor.
- Per-batch isolation in `process_items` (processing.py): wrap each `enrich(batch)` in try/except → log to a returned/collected errors list, continue.
- `temperature=0` (low): `Settings.llm_temperature: float = 0.0`; pass `generate_content_config=types.GenerateContentConfig(temperature=settings.llm_temperature)` in `build_processing_agent`/`build_critic_agent`/`build_judge_agent`/`build_digest_editor_agent`.
Tests: fenced/empty/garbage JSON handling; retry/backoff (injected); one bad batch doesn't void others; temperature wired.

## G3 — Eval rigor
- `Settings.judge_model: str | None = None` (falls back to llm_model) — allow a distinct/stronger judge.
- Judge calibration: in `scripts/eval_enrichment.py` + `eval_score.py`, compare judge verdicts to the fixture's gold `expectations` (confusion matrix / accuracy per dimension); report it. The eval must validate the JUDGE, not just the enricher.
- Gate faithfulness (and other safety-critical dims) on `pass_rate`/`min`, not `mean_score`, in `eval_score.aggregate`.
- Wire `compare()` to a persisted baseline report (`tests/eval/baseline.json` or similar); `--live` diffs and fails on regression.
- Grow `tests/eval/fixtures/enrichment_reference.json` to ~30-40 balanced realistic cases: all categories, multiple AR-quality negatives, more injection/hallucination variants, truncation/empty-excerpt, near-duplicate. Keep `expectations` per case.
Tests: calibration confusion-matrix logic; pass_rate gating; compare-vs-baseline; fixture loads + schema-valid.

## G4 — Orchestration
- **Reflection loop:** wrap Processing+Critic so unfaithful items get ONE re-enrichment pass with critic feedback in context, then re-critique. Prefer ADK `LoopAgent(max_iterations=2)` with an escalation when no unfaithful items remain; if LoopAgent destabilizes the contract tests, implement an explicit bounded re-enrich loop in the stage while keeping the tree shape. Re-enriched-then-still-unfaithful items end flagged+redacted (G1).
- **Unify sync bridge:** route `search.adk_ground` (search.py) through `_run_coro_sync` (app/llm/runtime.py) — remove the bare `asyncio.run`.
- **Per-node LLM timeouts:** covered by G2's `wait_for`; also add a wall-clock cap in `run_digest` (`settings.run_timeout`, optional).
- **State contract:** derive collector `state_key` and the NormalizeDedup merge list from one `SourceType→key` map (agents.py) so adding a source can't silently drop it.
- **Plan-9 guard:** add an integration test running the tree against ADK `DatabaseSessionService` (or document + xfail if the dep isn't available) to catch the direct-`state`-mutation break before Vertex/Firestore.
Tests: re-enrichment fixes a fixably-unfaithful item (injected); search bridge works inside a running loop; SourceType→key map; (db-session test or documented skip).

## G5 — Prompt engineering
- **Shared truncation:** one helper for the excerpt sent to producer AND critic AND judge (identical text); state the truncation in `faithfulness_rubric.md` ("Source = title + first N chars of excerpt").
- **Anchor importance:** `processing.md` 4-band scale with examples (routine/notable/major/globally-critical) aligned to the threshold + judge bar; mirror the bands near the `Importance`/`importance_score` definition.
- **Govern fields:** constrain `Entity.type` to an enum (schema.py + domain.py + prompt) (company|person|org|place|product); add a brief sentiment check to judge/critic OR document why not.
- **Arabic first-class:** `processing.md`/rubric — independent MSA summary of the source (not literal EN translation), formal register, number/date/proper-noun guidance; `youtube_summary.md` summarize in transcript language (AR→MSA); consider `narrative_ar` on `DigestNarrative`.
- **Echo output contract:** judge.md/critic.md list exact JSON field + dimension names and the approximate per-dimension pass bars, so `passed` agrees with `eval_score` thresholds and names can't drift.
Tests: prompt files contain the required anchors/contract (lightweight assertions where sensible); schema/enum changes covered; existing prompt-consumer tests green.

## Final
- Full backend + frontend gates green; update `docs/BUILD-LOG.md` + memory; push to `fix/review-remediation` (joins PR #15). Final review pass.
