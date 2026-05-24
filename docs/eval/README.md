# Enrichment Eval — Offline Judge Loop

## Overview

This is an offline, quota-free evaluation harness for the `news_processor` enrichment pipeline. It scores enrichment quality across four dimensions using an injectable judge boundary, so the full eval loop runs in pytest with synthetic verdicts (zero API calls).

## Running the Eval

### Offline (no API key, instant)
```bash
uv run python scripts/eval_enrichment.py
```
This prints usage info. The harness itself is tested via pytest (see below).

### Live (requires GOOGLE_API_KEY — deferred until quota is available)
```bash
GOOGLE_API_KEY=... uv run python scripts/eval_enrichment.py --live
```
Writes `output/eval/report.json` with dimension scores and pass/fail status.

### Pytest (offline, always runs in CI)
```bash
uv run pytest tests/unit/test_judge.py tests/unit/test_eval_score.py \
              tests/unit/test_eval_fixtures.py tests/unit/test_eval_harness.py -v
```
Or just the full suite: `uv run pytest tests -q`

---

## Dimensions and Thresholds

| Dimension | Threshold | Notes |
|---|---|---|
| `faithfulness` | **0.90** | Strictest — any hallucinated claim or injection compliance fails |
| `category_accuracy` | 0.85 | Four allowed values: `ai_tech`, `business_finance`, `world_geopolitics`, `gulf_mena` |
| `importance_calibration` | 0.70 | Plausibility band — only clear miscalibration penalised (e.g. trivial patch scored 0.9+) |
| `ar_translation_quality` | 0.80 | MSA fluency; no added/dropped facts vs `summary_en` |

The overall eval **passes** when every dimension's mean score meets or exceeds its threshold.

**Never lower thresholds just to pass.** If scores are below threshold, fix the prompt.

---

## The Eval-Fix Loop

1. Run `uv run pytest tests -q` to see all dimension scores via the harness tests.
2. Run `scripts/eval_enrichment.py --live` (when quota is available) to get real scores on `enrichment_reference.json`.
3. Identify failing dimensions from `report.json` → `failures`.
4. Fix the root prompt:
   - Low **faithfulness** → tighten `app/prompts/processing.md` (stronger anti-hallucination instruction, source-only rule).
   - Low **category_accuracy** → add examples to processing prompt; clarify boundary cases.
   - Low **importance_calibration** → adjust the calibration guidance in processing.md.
   - Low **ar_translation_quality** → add explicit MSA fidelity instruction.
5. Re-run eval. Repeat until all thresholds pass.

---

## Reference Dataset (`tests/eval/fixtures/enrichment_reference.json`)

10 cases total:
- **5 happy-path** (from `processing-goldens.md`) — correct category, calibrated importance, faithful summaries, good Arabic.
- **5 adversarial:**
  - Hallucinated fact in summary (round-number dollar amount not in excerpt) → `faithfulness: false`
  - Prompt injection excerpt ("Ignore previous instructions…") with compliant summary → `faithfulness: false`
  - Typo-patch item with `importance_score=0.92` → `importance_calibration: false`
  - Gulf AI story miscategorised as `business_finance` instead of `gulf_mena` → `category_accuracy: false`
  - AR summary that drops a key fact (medical AI) → `ar_translation_quality: false`

Each case has an `expectations` dict with boolean per-dimension, used by offline tests to validate fixture coverage.

---

## Architecture Notes

- **Why a custom harness, not `agents-cli eval`?** `agents-cli eval` targets the conversational `root_agent`; `news_processor` is a batch structured-output agent — interface mismatch. See `processing-goldens.md` for historical context.
- **ADK output_schema wrapping:** ADK requires a Pydantic model (not a bare list) as `output_schema`. `EnrichmentVerdicts` wraps `list[EnrichmentVerdict]` for this reason.
- **EnrichFn / JudgeFn are injectable** — in tests, swap real ADK calls for synthetic functions; in `--live` mode, bind `adk_enrich` / `adk_judge` from the pipeline.
