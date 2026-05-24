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


class EvalReport(BaseModel):
    n: int
    dimension_pass_rate: dict[str, float]
    dimension_mean_score: dict[str, float]
    passed: bool
    failures: list[str]


def _dim_verdict(verdict: EnrichmentVerdict, dim: str) -> DimensionVerdict:
    return getattr(verdict, dim)


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
            passed=False,
            failures=list(_DIMENSIONS),
        )

    pass_rate: dict[str, float] = {}
    mean_score: dict[str, float] = {}

    for dim in _DIMENSIONS:
        dim_verdicts = [_dim_verdict(v, dim) for v in verdicts]
        pass_rate[dim] = sum(1 for dv in dim_verdicts if dv.passed) / n
        mean_score[dim] = sum(dv.score for dv in dim_verdicts) / n

    failures = [
        dim
        for dim in _DIMENSIONS
        if mean_score[dim] < thresholds.get(dim, 1.0)
    ]
    passed = len(failures) == 0

    return EvalReport(
        n=n,
        dimension_pass_rate=pass_rate,
        dimension_mean_score=mean_score,
        passed=passed,
        failures=failures,
    )


def compare(baseline: EvalReport, candidate: EvalReport) -> dict:
    """Return per-dimension delta and a list of regressions (dropped > 0.05)."""
    deltas: dict[str, float] = {}
    regressions: list[str] = []

    for dim in _DIMENSIONS:
        b = baseline.dimension_mean_score.get(dim, 0.0)
        c = candidate.dimension_mean_score.get(dim, 0.0)
        delta = c - b
        deltas[dim] = round(delta, 6)
        if delta < -0.05:
            regressions.append(dim)

    return {"deltas": deltas, "regressions": regressions}
