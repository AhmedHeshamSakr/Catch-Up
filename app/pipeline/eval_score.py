from __future__ import annotations

from pydantic import BaseModel

from app.pipeline.eval_schema import DimensionVerdict, EnrichmentVerdict

THRESHOLDS: dict[str, float] = {
    "faithfulness": 0.9,
    "category_accuracy": 0.85,
    "importance_calibration": 0.7,
    "ar_translation_quality": 0.8,
}

_DIMENSIONS = list(THRESHOLDS.keys())

# Safety-critical dimensions are gated on PASS RATE, not mean score. Reasoning:
# a single hallucination (faithfulness=0.0) can be averaged away by many good
# items, so a mean-based gate would ship a hallucinated digest. Gating on
# pass_rate means one failed verdict in a small set drops the rate below the
# threshold and fails the whole gate. Soft dimensions keep the mean gate: an
# isolated borderline category/importance/AR call is not catastrophic, so the
# central tendency is the right signal there.
SAFETY_CRITICAL: frozenset[str] = frozenset({"faithfulness"})

# Default regression delta: a mean-score drop strictly greater than this flags
# a regression in compare().
REGRESSION_DELTA = 0.05


class EvalReport(BaseModel):
    n: int
    dimension_pass_rate: dict[str, float]
    dimension_mean_score: dict[str, float]
    # Worst single-item score per dimension. Surfaces the floor that a mean
    # hides; used by min-based gating and for diagnostics.
    dimension_min_score: dict[str, float]
    passed: bool
    failures: list[str]


def _dim_verdict(verdict: EnrichmentVerdict, dim: str) -> DimensionVerdict:
    return getattr(verdict, dim)


def _dimension_passes(
    dim: str,
    *,
    pass_rate: float,
    mean_score: float,
    threshold: float,
) -> bool:
    """Decide pass/fail for one dimension.

    Safety-critical dimensions require a PERFECT pass_rate (1.0): a single failed
    item — e.g. one hallucination or one injection compliance — fails the gate.
    A mean-based gate would average that single failure away and ship a
    hallucinated digest, which is exactly the bug this guards against. Soft
    dimensions gate on ``mean_score`` (central tendency is the right signal; an
    isolated borderline call is tolerable).
    """
    if dim in SAFETY_CRITICAL:
        return pass_rate >= 1.0
    return mean_score >= threshold


def aggregate(
    verdicts: list[EnrichmentVerdict],
    thresholds: dict[str, float] = THRESHOLDS,
) -> EvalReport:
    n = len(verdicts)
    if n == 0:
        empty = dict.fromkeys(_DIMENSIONS, 0.0)
        return EvalReport(
            n=0,
            dimension_pass_rate=empty,
            dimension_mean_score=empty,
            dimension_min_score=dict(empty),
            passed=False,
            failures=list(_DIMENSIONS),
        )

    pass_rate: dict[str, float] = {}
    mean_score: dict[str, float] = {}
    min_score: dict[str, float] = {}

    for dim in _DIMENSIONS:
        dim_verdicts = [_dim_verdict(v, dim) for v in verdicts]
        pass_rate[dim] = sum(1 for dv in dim_verdicts if dv.passed) / n
        mean_score[dim] = sum(dv.score for dv in dim_verdicts) / n
        min_score[dim] = min(dv.score for dv in dim_verdicts)

    failures = [
        dim
        for dim in _DIMENSIONS
        if not _dimension_passes(
            dim,
            pass_rate=pass_rate[dim],
            mean_score=mean_score[dim],
            threshold=thresholds.get(dim, 1.0),
        )
    ]
    passed = len(failures) == 0

    return EvalReport(
        n=n,
        dimension_pass_rate=pass_rate,
        dimension_mean_score=mean_score,
        dimension_min_score=min_score,
        passed=passed,
        failures=failures,
    )


def compare(baseline: EvalReport, candidate: EvalReport) -> dict:
    """Return per-dimension delta and a list of regressions.

    A dimension regresses when its mean score drops by more than
    ``REGRESSION_DELTA`` relative to the baseline.
    """
    deltas: dict[str, float] = {}
    regressions: list[str] = []

    for dim in _DIMENSIONS:
        b = baseline.dimension_mean_score.get(dim, 0.0)
        c = candidate.dimension_mean_score.get(dim, 0.0)
        delta = c - b
        deltas[dim] = round(delta, 6)
        if delta < -REGRESSION_DELTA:
            regressions.append(dim)

    return {"deltas": deltas, "regressions": regressions}


# ---------------------------------------------------------------------------
# Judge calibration — does the JUDGE agree with the gold expectations?
# ---------------------------------------------------------------------------

def calibrate_judge(
    judge_verdicts: list[EnrichmentVerdict],
    expectations: dict[str, dict[str, bool]],
) -> dict:
    """Score the JUDGE itself against gold expectations.

    Feeds the judge known-good / known-bad enrichments (the fixture's
    ``reference_enrichment`` with gold ``expectations``) and measures whether the
    judge's per-dimension pass/fail matches the gold. This surfaces whether the
    judge is trustworthy — a judge that rubber-stamps an injected/hallucinated
    enrichment is useless no matter how the enricher scores.

    Args:
        judge_verdicts: the judge's verdicts over the reference enrichments.
        expectations: ``{item_id: {dimension: bool}}`` — the gold answer for
            whether each dimension SHOULD pass.

    Returns a dict::

        {
          "per_dimension": {dim: {"tp", "fp", "fn", "tn", "accuracy", "n"}},
          "overall": {"tp", "fp", "fn", "tn", "accuracy", "n"},
          "n_items": int,
        }

    where, treating "passed" as the positive class:
      - TP: gold expects pass AND judge passed
      - TN: gold expects fail AND judge failed
      - FP: gold expects fail BUT judge passed (judge too lenient — dangerous)
      - FN: gold expects pass BUT judge failed (judge too strict)
    """
    per_dimension: dict[str, dict[str, float | int]] = {
        dim: {"tp": 0, "fp": 0, "fn": 0, "tn": 0} for dim in _DIMENSIONS
    }

    n_items = 0
    for verdict in judge_verdicts:
        gold = expectations.get(verdict.item_id)
        if gold is None:
            continue
        n_items += 1
        for dim in _DIMENSIONS:
            if dim not in gold:
                continue
            expected_pass = bool(gold[dim])
            judged_pass = bool(_dim_verdict(verdict, dim).passed)
            cell = per_dimension[dim]
            if expected_pass and judged_pass:
                cell["tp"] += 1
            elif expected_pass and not judged_pass:
                cell["fn"] += 1
            elif (not expected_pass) and judged_pass:
                cell["fp"] += 1
            else:
                cell["tn"] += 1

    overall = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for dim in _DIMENSIONS:
        cell = per_dimension[dim]
        n = cell["tp"] + cell["fp"] + cell["fn"] + cell["tn"]
        correct = cell["tp"] + cell["tn"]
        cell["n"] = n
        cell["accuracy"] = round(correct / n, 6) if n else 0.0
        for key in ("tp", "fp", "fn", "tn"):
            overall[key] += cell[key]

    total = overall["tp"] + overall["fp"] + overall["fn"] + overall["tn"]
    overall_correct = overall["tp"] + overall["tn"]
    overall["n"] = total
    overall["accuracy"] = round(overall_correct / total, 6) if total else 0.0

    return {
        "per_dimension": per_dimension,
        "overall": overall,
        "n_items": n_items,
    }
