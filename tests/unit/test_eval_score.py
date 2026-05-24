"""Unit tests for app/pipeline/eval_score.py — fully offline."""
from __future__ import annotations

from app.pipeline.eval_schema import DimensionVerdict, EnrichmentVerdict
from app.pipeline.eval_score import THRESHOLDS, EvalReport, aggregate, compare


def _dim(passed: bool, score: float) -> DimensionVerdict:
    return DimensionVerdict(passed=passed, score=score, reason="test")


def _verdict(
    item_id: str,
    faith_passed: bool = True,
    faith_score: float = 1.0,
    cat_passed: bool = True,
    cat_score: float = 1.0,
    imp_passed: bool = True,
    imp_score: float = 1.0,
    ar_passed: bool = True,
    ar_score: float = 1.0,
) -> EnrichmentVerdict:
    return EnrichmentVerdict(
        item_id=item_id,
        faithfulness=_dim(faith_passed, faith_score),
        category_accuracy=_dim(cat_passed, cat_score),
        importance_calibration=_dim(imp_passed, imp_score),
        ar_translation_quality=_dim(ar_passed, ar_score),
    )


# ---------------------------------------------------------------------------
# aggregate: basic correctness
# ---------------------------------------------------------------------------

def test_aggregate_all_pass():
    verdicts = [_verdict(f"v{i}") for i in range(4)]
    report = aggregate(verdicts)
    assert report.n == 4
    assert report.passed is True
    assert report.failures == []
    for dim in ["faithfulness", "category_accuracy", "importance_calibration", "ar_translation_quality"]:
        assert report.dimension_pass_rate[dim] == 1.0
        assert report.dimension_mean_score[dim] == 1.0


def test_aggregate_exact_pass_rate():
    verdicts = [
        _verdict("a", faith_passed=True, faith_score=1.0),
        _verdict("b", faith_passed=False, faith_score=0.0),
        _verdict("c", faith_passed=True, faith_score=0.8),
        _verdict("d", faith_passed=False, faith_score=0.6),
    ]
    report = aggregate(verdicts)
    assert report.n == 4
    assert report.dimension_pass_rate["faithfulness"] == 0.5  # 2/4 passed
    # mean_score = (1.0 + 0.0 + 0.8 + 0.6) / 4 = 0.6
    assert abs(report.dimension_mean_score["faithfulness"] - 0.6) < 1e-9


def test_aggregate_threshold_boundary_fails_just_below():
    """faithfulness threshold is 0.9; a mean_score of 0.8999 should fail."""
    # Two verdicts with mean faith score = 0.8999
    verdicts = [
        _verdict("x", faith_score=0.8998),
        _verdict("y", faith_score=0.9000),
    ]
    report = aggregate(verdicts)
    assert abs(report.dimension_mean_score["faithfulness"] - 0.8999) < 1e-9
    assert "faithfulness" in report.failures
    assert report.passed is False


def test_aggregate_threshold_boundary_passes_at_threshold():
    """A mean_score exactly at the threshold should pass."""
    verdicts = [
        _verdict("x", faith_score=0.9),
        _verdict("y", faith_score=0.9),
    ]
    report = aggregate(verdicts)
    assert abs(report.dimension_mean_score["faithfulness"] - 0.9) < 1e-9
    assert "faithfulness" not in report.failures


def test_aggregate_single_dimension_failure():
    """Only ar_translation_quality below threshold."""
    verdicts = [
        _verdict("a", ar_score=0.5),
        _verdict("b", ar_score=0.6),
    ]
    report = aggregate(verdicts)
    assert "ar_translation_quality" in report.failures
    # All other dimensions are at 1.0 (default), should pass
    for dim in ["faithfulness", "category_accuracy", "importance_calibration"]:
        assert dim not in report.failures
    assert report.passed is False


def test_aggregate_empty_verdicts():
    report = aggregate([])
    assert report.n == 0
    assert report.passed is False
    assert set(report.failures) == {
        "faithfulness", "category_accuracy", "importance_calibration", "ar_translation_quality"
    }


def test_aggregate_custom_thresholds():
    verdicts = [_verdict("a", faith_score=0.5)]
    # Lenient threshold: faith only needs 0.4
    report = aggregate(verdicts, thresholds={"faithfulness": 0.4, "category_accuracy": 0.4,
                                              "importance_calibration": 0.4, "ar_translation_quality": 0.4})
    assert report.passed is True


# ---------------------------------------------------------------------------
# compare: regression detection
# ---------------------------------------------------------------------------

def _report(faith: float = 1.0, cat: float = 1.0, imp: float = 1.0, ar: float = 1.0) -> EvalReport:
    scores = {
        "faithfulness": faith,
        "category_accuracy": cat,
        "importance_calibration": imp,
        "ar_translation_quality": ar,
    }
    pass_rates = dict.fromkeys(scores, 1.0)
    failures = [k for k, v in scores.items() if v < THRESHOLDS.get(k, 1.0)]
    return EvalReport(
        n=4,
        dimension_pass_rate=pass_rates,
        dimension_mean_score=scores,
        passed=len(failures) == 0,
        failures=failures,
    )


def test_compare_no_regression():
    baseline = _report(faith=0.95, cat=0.9, imp=0.8, ar=0.85)
    candidate = _report(faith=0.95, cat=0.9, imp=0.8, ar=0.85)
    result = compare(baseline, candidate)
    assert result["regressions"] == []
    for delta in result["deltas"].values():
        assert delta == 0.0


def test_compare_improvement():
    baseline = _report(faith=0.80, cat=0.80, imp=0.70, ar=0.75)
    candidate = _report(faith=0.95, cat=0.90, imp=0.80, ar=0.85)
    result = compare(baseline, candidate)
    assert result["regressions"] == []
    assert result["deltas"]["faithfulness"] > 0


def test_compare_flags_regression():
    """A drop of more than 0.05 in faithfulness must appear in regressions."""
    baseline = _report(faith=0.95)
    candidate = _report(faith=0.85)  # drop of 0.10
    result = compare(baseline, candidate)
    assert "faithfulness" in result["regressions"]


def test_compare_small_drop_not_regression():
    """A drop of exactly 0.05 is NOT a regression (threshold is > 0.05)."""
    baseline = _report(faith=0.95)
    candidate = _report(faith=0.90)  # drop of 0.05
    result = compare(baseline, candidate)
    assert "faithfulness" not in result["regressions"]


def test_compare_multiple_regressions():
    baseline = _report(faith=0.95, cat=0.90, imp=0.80, ar=0.90)
    candidate = _report(faith=0.80, cat=0.75, imp=0.80, ar=0.90)  # faith and cat regressed
    result = compare(baseline, candidate)
    assert "faithfulness" in result["regressions"]
    assert "category_accuracy" in result["regressions"]
    assert "importance_calibration" not in result["regressions"]
    assert "ar_translation_quality" not in result["regressions"]
