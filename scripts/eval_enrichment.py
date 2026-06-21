"""eval_enrichment.py — offline enrichment eval harness.

Usage (offline, no API key):
    uv run python scripts/eval_enrichment.py

Usage (live, needs GOOGLE_API_KEY):
    uv run python scripts/eval_enrichment.py --live

The offline mode does nothing useful on its own (enrich/judge must be injected).
Use the --live flag to run with real ADK agents; report is written to output/eval/report.json.

Live add-ons (all require GOOGLE_API_KEY):
    --calibrate         Run the JUDGE over the reference enrichments with KNOWN
                        gold expectations and print a per-dimension confusion
                        matrix + accuracy — surfaces whether the JUDGE is
                        trustworthy, not just whether the enricher passed.
    --check-regression  After the eval, compare against the committed baseline
                        (tests/eval/baseline.json) and EXIT NON-ZERO if any
                        dimension regressed beyond the threshold.
    --update-baseline   Overwrite tests/eval/baseline.json with the current
                        report (refresh the regression baseline).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.core.domain import Category, NewsItem, Sentiment, SourceType
from app.llm.schema import ItemEnrichment, ProcessingResult
from app.pipeline.eval_schema import EnrichmentVerdict
from app.pipeline.eval_score import EvalReport, aggregate, calibrate_judge, compare
from app.pipeline.judge import JudgeFn
from app.pipeline.processing import EnrichFn

_REFERENCE_PATH = Path(__file__).resolve().parents[1] / "tests" / "eval" / "fixtures" / "enrichment_reference.json"
_BASELINE_PATH = Path(__file__).resolve().parents[1] / "tests" / "eval" / "baseline.json"


def load_reference(path: str | Path = _REFERENCE_PATH) -> list[dict]:
    """Load the enrichment reference fixture from disk."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _build_news_item(item_dict: dict) -> NewsItem:
    """Construct a minimal NewsItem from a fixture item dict."""
    return NewsItem(
        id=item_dict["id"],
        source_id="eval",
        source_type=SourceType.RSS,
        source_name="eval",
        url=f"https://eval.local/{item_dict['id']}",
        title=item_dict["title"],
        excerpt=item_dict.get("excerpt"),
    )


def _build_item_enrichment(gold_dict: dict) -> ItemEnrichment:
    """Construct an ItemEnrichment from a fixture gold dict."""
    return ItemEnrichment(
        id=gold_dict["id"],
        category=Category(gold_dict["category"]),
        importance_score=gold_dict["importance_score"],
        summary_en=gold_dict["summary_en"],
        summary_ar=gold_dict["summary_ar"],
        entities=gold_dict.get("entities", []),
        sentiment=Sentiment(gold_dict["sentiment"]),
    )


def run_eval(
    *,
    enrich: EnrichFn,
    judge: JudgeFn,
    reference: list[dict],
) -> EvalReport:
    """Run the full eval loop and return an EvalReport.

    Args:
        enrich: callable matching EnrichFn — takes list[NewsItem], returns ProcessingResult.
        judge:  callable matching JudgeFn — takes list[tuple[NewsItem, ItemEnrichment]], returns list[EnrichmentVerdict].
        reference: list of dicts loaded from enrichment_reference.json.
    """
    # Build NewsItem list and id→gold map
    news_items: list[NewsItem] = [_build_news_item(case["item"]) for case in reference]
    gold_by_id: dict[str, ItemEnrichment] = {
        case["gold"]["id"]: _build_item_enrichment(case["gold"]) for case in reference
    }

    # Enrich all items in one batch (eval uses gold or fake enrich)
    processing_result: ProcessingResult = enrich(news_items)
    enrichment_by_id: dict[str, ItemEnrichment] = {e.id: e for e in processing_result.items}

    # Pair each NewsItem with its enrichment result (fall back to gold if missing)
    pairs: list[tuple[NewsItem, ItemEnrichment]] = []
    for item in news_items:
        enrichment = enrichment_by_id.get(item.id) or gold_by_id.get(item.id)
        if enrichment is not None:
            pairs.append((item, enrichment))

    # Judge all pairs
    verdicts: list[EnrichmentVerdict] = judge(pairs)

    # Pass the judged ids so a verdict the judge OMITTED counts as a hard failure
    # (fail-closed) instead of silently inflating the pass_rate.
    return aggregate(verdicts, expected_ids=[item.id for item, _ in pairs])


def run_calibration(*, judge: JudgeFn, reference: list[dict]) -> dict:
    """Calibrate the JUDGE against gold expectations.

    Feeds each case's reference enrichment (``reference_enrichment`` if present,
    else the ``gold`` enrichment — which the adversarial cases deliberately make
    known-BAD to match their ``expectations``) to the judge, then checks whether
    the judge's per-dimension pass/fail matches the gold ``expectations``.

    Returns the dict from :func:`app.pipeline.eval_score.calibrate_judge`.
    """
    news_items: list[NewsItem] = [_build_news_item(case["item"]) for case in reference]
    items_by_id = {item.id: item for item in news_items}

    pairs: list[tuple[NewsItem, ItemEnrichment]] = []
    expectations: dict[str, dict[str, bool]] = {}
    for case in reference:
        item = items_by_id[case["item"]["id"]]
        # reference_enrichment is optional; gold already encodes the known-good /
        # known-bad input that the judge must score, so fall back to it.
        ref_dict = case.get("reference_enrichment", case["gold"])
        pairs.append((item, _build_item_enrichment(ref_dict)))
        expectations[case["item"]["id"]] = case["expectations"]

    verdicts = judge(pairs)
    return calibrate_judge(verdicts, expectations)


def load_baseline(path: str | Path = _BASELINE_PATH) -> EvalReport:
    """Load the committed baseline EvalReport from disk."""
    return EvalReport.model_validate_json(Path(path).read_text(encoding="utf-8"))


def save_baseline(report: EvalReport, path: str | Path = _BASELINE_PATH) -> None:
    """Persist an EvalReport as the regression baseline."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(report.model_dump_json(indent=2), encoding="utf-8")


def check_regression(current: EvalReport, baseline: EvalReport) -> dict:
    """Compare the current report against a baseline.

    Returns ``{"deltas": ..., "regressions": [...], "regressed": bool}``.
    """
    result = compare(baseline, current)
    result["regressed"] = bool(result["regressions"])
    return result


def _print_calibration(calib: dict) -> None:
    print("\n=== JUDGE CALIBRATION (vs gold expectations) ===")
    print(f"items: {calib['n_items']}  overall accuracy: {calib['overall']['accuracy']:.3f}")
    print(f"overall TP/FP/FN/TN: {calib['overall']['tp']}/{calib['overall']['fp']}/"
          f"{calib['overall']['fn']}/{calib['overall']['tn']}")
    for dim, cell in calib["per_dimension"].items():
        print(f"  {dim}: acc={cell['accuracy']:.3f}  "
              f"TP={cell['tp']} FP={cell['fp']} FN={cell['fn']} TN={cell['tn']}")
    if calib["overall"]["fp"] > 0:
        print("  WARNING: judge has FALSE POSITIVES — it passed items the gold says should FAIL "
              "(lenient/untrustworthy judge).")


def _main() -> None:
    parser = argparse.ArgumentParser(description="Enrichment quality eval harness")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run with real ADK agents (requires GOOGLE_API_KEY). Writes output/eval/report.json.",
    )
    parser.add_argument(
        "--reference",
        default=str(_REFERENCE_PATH),
        help="Path to enrichment_reference.json fixture.",
    )
    parser.add_argument(
        "--calibrate",
        action="store_true",
        help="Also calibrate the JUDGE against gold expectations (confusion matrix + accuracy). Implies --live.",
    )
    parser.add_argument(
        "--check-regression",
        action="store_true",
        help="Compare against tests/eval/baseline.json and exit non-zero on regression. Implies --live.",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Overwrite tests/eval/baseline.json with the current report. Implies --live.",
    )
    args = parser.parse_args()

    live = args.live or args.calibrate or args.check_regression or args.update_baseline

    if not live:
        print("Offline mode: no live model calls. Use --live to run against the real enrichment pipeline.")
        print(f"Reference fixture: {args.reference}")
        print("Add --calibrate / --check-regression / --update-baseline (all imply --live).")
        return

    # Live mode — import real implementations
    import os

    from app.core.config import Settings
    from app.pipeline.judge import adk_judge
    from app.pipeline.processing import adk_enrich

    settings = Settings()
    if not settings.google_api_key and not os.environ.get("GOOGLE_API_KEY"):
        raise SystemExit("ERROR: GOOGLE_API_KEY is required for live mode.")
    reference = load_reference(args.reference)

    def enrich_fn(items):
        return adk_enrich(items, settings)

    def judge_fn(pairs):
        return adk_judge(pairs, settings)

    report = run_eval(enrich=enrich_fn, judge=judge_fn, reference=reference)

    out_dir = Path("output") / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "report.json"
    out_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    print(f"Eval report written to {out_path}")
    print(f"Overall passed: {report.passed}")
    print(f"n={report.n}, failures={report.failures}")
    for dim, score in report.dimension_mean_score.items():
        print(f"  {dim}: mean_score={score:.3f}  "
              f"pass_rate={report.dimension_pass_rate[dim]:.3f}  "
              f"min_score={report.dimension_min_score[dim]:.3f}")

    # --calibrate: is the JUDGE itself trustworthy?
    if args.calibrate:
        calib = run_calibration(judge=judge_fn, reference=reference)
        _print_calibration(calib)
        (out_dir / "calibration.json").write_text(
            json.dumps(calib, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # --update-baseline: refresh the committed baseline
    if args.update_baseline:
        save_baseline(report)
        print(f"\nBaseline updated: {_BASELINE_PATH}")

    # --check-regression: fail the run if any dim regressed beyond threshold
    if args.check_regression:
        if not _BASELINE_PATH.exists():
            raise SystemExit(f"ERROR: no baseline at {_BASELINE_PATH}. Run --update-baseline first.")
        baseline = load_baseline()
        result = check_regression(report, baseline)
        print("\n=== REGRESSION CHECK vs baseline ===")
        for dim, delta in result["deltas"].items():
            marker = "  <-- REGRESSION" if dim in result["regressions"] else ""
            print(f"  {dim}: delta={delta:+.3f}{marker}")
        if result["regressed"]:
            raise SystemExit(f"REGRESSION DETECTED in: {result['regressions']}")
        print("No regression.")


if __name__ == "__main__":
    _main()
