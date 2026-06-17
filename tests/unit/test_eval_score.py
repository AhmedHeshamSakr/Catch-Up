"""Unit tests for app/pipeline/eval_score.py — fully offline."""
from __future__ import annotations

from app.pipeline.eval_schema import DimensionVerdict, EnrichmentVerdict
from app.pipeline.eval_score import (
    THRESHOLDS,
    EvalReport,
    aggregate,
    calibrate_judge,
    compare,
)


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


def test_aggregate_faithfulness_gates_on_pass_rate_not_mean():
    """Safety-critical: faithfulness is gated on pass_rate, NOT mean_score.

    Both items have low faith scores but are marked passed, so the mean (0.8999)
    is below the 0.9 threshold yet pass_rate is 1.0 — the gate must pass because
    no item actually failed faithfulness.
    """
    verdicts = [
        _verdict("x", faith_passed=True, faith_score=0.8998),
        _verdict("y", faith_passed=True, faith_score=0.9000),
    ]
    report = aggregate(verdicts)
    assert abs(report.dimension_mean_score["faithfulness"] - 0.8999) < 1e-9
    assert report.dimension_pass_rate["faithfulness"] == 1.0
    assert "faithfulness" not in report.failures


def test_aggregate_single_faithfulness_failure_fails_gate_despite_high_mean():
    """A SINGLE hallucination (faithfulness=0.0, passed=False) must fail the gate
    even when the mean is high — a mean-based gate would have averaged it away."""
    # 19 perfect + 1 hallucinated → mean = 0.95 (above 0.9 threshold)
    verdicts = [_verdict(f"good-{i}", faith_passed=True, faith_score=1.0) for i in range(19)]
    verdicts.append(_verdict("hallucination", faith_passed=False, faith_score=0.0))
    report = aggregate(verdicts)
    assert report.dimension_mean_score["faithfulness"] == 0.95  # high mean
    assert report.dimension_min_score["faithfulness"] == 0.0    # but a 0.0 floor
    assert report.dimension_pass_rate["faithfulness"] == 0.95   # 19/20 passed
    # Safety-critical dims require a PERFECT pass_rate (1.0); one failed item
    # (the hallucination) drops it to 0.95 and fails the gate.
    assert "faithfulness" in report.failures
    assert report.passed is False


def test_aggregate_threshold_boundary_passes_at_threshold():
    """All items pass faithfulness → pass_rate 1.0 → gate passes."""
    verdicts = [
        _verdict("x", faith_score=0.9),
        _verdict("y", faith_score=0.9),
    ]
    report = aggregate(verdicts)
    assert report.dimension_pass_rate["faithfulness"] == 1.0
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
        dimension_min_score=dict(scores),
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


def test_compare_safety_critical_pass_rate_drop_is_regression_even_when_mean_barely_moves():
    """One new hallucination drops pass_rate below 1.0 while the mean moves <0.05.

    The acceptance gate fails this (pass_rate < 1.0), so the regression check
    must catch it too — a mean-only check would exit green and ship it.
    """
    dims = ["faithfulness", "category_accuracy", "importance_calibration", "ar_translation_quality"]
    baseline = EvalReport(
        n=35,
        dimension_pass_rate=dict.fromkeys(dims, 1.0),
        dimension_mean_score={d: (0.96 if d == "faithfulness" else 0.95) for d in dims},
        dimension_min_score=dict.fromkeys(dims, 0.5),
        passed=True,
        failures=[],
    )
    candidate = EvalReport(
        n=35,
        dimension_pass_rate={d: (0.971 if d == "faithfulness" else 1.0) for d in dims},
        dimension_mean_score={d: (0.933 if d == "faithfulness" else 0.95) for d in dims},
        dimension_min_score=dict.fromkeys(dims, 0.0),
        passed=False,
        failures=["faithfulness"],
    )
    result = compare(baseline, candidate)
    assert result["deltas"]["faithfulness"] > -0.05  # mean drop is sub-threshold
    assert "faithfulness" in result["regressions"]  # but pass_rate drop is caught


def test_compare_safety_critical_improvement_from_bad_baseline_not_regression():
    """A pass_rate IMPROVEMENT is never a regression — even if the mean DIPPED.

    pass_rate is the gating signal; the mean is only consulted when pass_rate is
    unchanged. Here pass_rate rises 0.8->1.0 while the mean falls 0.96->0.90
    (>0.05) — that must NOT be flagged, because the dimension genuinely improved.
    """
    dims = ["faithfulness", "category_accuracy", "importance_calibration", "ar_translation_quality"]
    baseline = EvalReport(
        n=10, dimension_pass_rate={d: (0.8 if d == "faithfulness" else 1.0) for d in dims},
        dimension_mean_score={d: (0.96 if d == "faithfulness" else 0.95) for d in dims},
        dimension_min_score=dict.fromkeys(dims, 0.5),
        passed=False, failures=["faithfulness"],
    )
    candidate = EvalReport(
        n=10, dimension_pass_rate=dict.fromkeys(dims, 1.0),
        dimension_mean_score={d: (0.90 if d == "faithfulness" else 0.95) for d in dims},
        dimension_min_score=dict.fromkeys(dims, 0.8),
        passed=True, failures=[],
    )
    result = compare(baseline, candidate)
    assert result["deltas"]["faithfulness"] < -0.05  # mean dropped past threshold
    assert "faithfulness" not in result["regressions"]  # but pass_rate improved


def test_compare_multiple_regressions():
    baseline = _report(faith=0.95, cat=0.90, imp=0.80, ar=0.90)
    candidate = _report(faith=0.80, cat=0.75, imp=0.80, ar=0.90)  # faith and cat regressed
    result = compare(baseline, candidate)
    assert "faithfulness" in result["regressions"]
    assert "category_accuracy" in result["regressions"]
    assert "importance_calibration" not in result["regressions"]
    assert "ar_translation_quality" not in result["regressions"]


# ---------------------------------------------------------------------------
# calibrate_judge: does the judge agree with gold expectations?
# ---------------------------------------------------------------------------

def _all_dims_verdict(item_id: str, passed_by_dim: dict[str, bool]) -> EnrichmentVerdict:
    return EnrichmentVerdict(
        item_id=item_id,
        faithfulness=_dim(passed_by_dim["faithfulness"], 1.0 if passed_by_dim["faithfulness"] else 0.0),
        category_accuracy=_dim(passed_by_dim["category_accuracy"], 1.0 if passed_by_dim["category_accuracy"] else 0.0),
        importance_calibration=_dim(passed_by_dim["importance_calibration"], 1.0 if passed_by_dim["importance_calibration"] else 0.0),
        ar_translation_quality=_dim(passed_by_dim["ar_translation_quality"], 1.0 if passed_by_dim["ar_translation_quality"] else 0.0),
    )


def test_calibrate_judge_perfect_agreement():
    """Judge matches gold on every dim → accuracy 1.0, only TP/TN cells."""
    expectations = {
        "a": {"faithfulness": True, "category_accuracy": True,
              "importance_calibration": True, "ar_translation_quality": True},
        "b": {"faithfulness": False, "category_accuracy": False,
              "importance_calibration": False, "ar_translation_quality": False},
    }
    verdicts = [
        _all_dims_verdict("a", expectations["a"]),
        _all_dims_verdict("b", expectations["b"]),
    ]
    result = calibrate_judge(verdicts, expectations)
    assert result["n_items"] == 2
    assert result["overall"]["accuracy"] == 1.0
    assert result["overall"]["fp"] == 0
    assert result["overall"]["fn"] == 0
    for dim in THRESHOLDS:
        cell = result["per_dimension"][dim]
        assert cell["accuracy"] == 1.0
        assert cell["tp"] == 1  # case "a"
        assert cell["tn"] == 1  # case "b"


def test_calibrate_judge_false_positive_lenient_judge():
    """Gold expects faithfulness FAIL (injection) but judge passed it → FP.

    This is the dangerous case: a lenient judge rubber-stamps a bad enrichment.
    """
    expectations = {
        "inj": {"faithfulness": False, "category_accuracy": True,
                "importance_calibration": True, "ar_translation_quality": True},
    }
    # Judge wrongly PASSES faithfulness
    verdicts = [
        _all_dims_verdict("inj", {"faithfulness": True, "category_accuracy": True,
                                  "importance_calibration": True, "ar_translation_quality": True}),
    ]
    result = calibrate_judge(verdicts, expectations)
    faith = result["per_dimension"]["faithfulness"]
    assert faith["fp"] == 1
    assert faith["tp"] == 0
    assert faith["accuracy"] == 0.0
    # other dims agreed (both expected and judged pass) → TP
    assert result["per_dimension"]["category_accuracy"]["tp"] == 1


def test_calibrate_judge_false_negative_strict_judge():
    """Gold expects PASS but judge failed it → FN (judge too strict)."""
    expectations = {
        "ok": {"faithfulness": True, "category_accuracy": True,
               "importance_calibration": True, "ar_translation_quality": True},
    }
    verdicts = [
        _all_dims_verdict("ok", {"faithfulness": False, "category_accuracy": True,
                                 "importance_calibration": True, "ar_translation_quality": True}),
    ]
    result = calibrate_judge(verdicts, expectations)
    faith = result["per_dimension"]["faithfulness"]
    assert faith["fn"] == 1
    assert faith["tp"] == 0
    assert faith["accuracy"] == 0.0


def test_calibrate_judge_mixed_accuracy():
    """3 items, faithfulness: 2 correct + 1 FP → accuracy 2/3."""
    expectations = {
        "a": {"faithfulness": True, "category_accuracy": True,
              "importance_calibration": True, "ar_translation_quality": True},
        "b": {"faithfulness": False, "category_accuracy": True,
              "importance_calibration": True, "ar_translation_quality": True},
        "c": {"faithfulness": False, "category_accuracy": True,
              "importance_calibration": True, "ar_translation_quality": True},
    }
    verdicts = [
        _all_dims_verdict("a", {"faithfulness": True, "category_accuracy": True,
                                "importance_calibration": True, "ar_translation_quality": True}),  # TP
        _all_dims_verdict("b", {"faithfulness": False, "category_accuracy": True,
                                "importance_calibration": True, "ar_translation_quality": True}),  # TN
        _all_dims_verdict("c", {"faithfulness": True, "category_accuracy": True,
                                "importance_calibration": True, "ar_translation_quality": True}),  # FP
    ]
    result = calibrate_judge(verdicts, expectations)
    faith = result["per_dimension"]["faithfulness"]
    assert faith["tp"] == 1
    assert faith["tn"] == 1
    assert faith["fp"] == 1
    assert faith["fn"] == 0
    assert abs(faith["accuracy"] - (2 / 3)) < 1e-6


def test_calibrate_judge_ignores_unknown_item():
    """A verdict whose item_id is not in expectations is skipped."""
    expectations = {
        "known": {"faithfulness": True, "category_accuracy": True,
                  "importance_calibration": True, "ar_translation_quality": True},
    }
    verdicts = [
        _all_dims_verdict("known", expectations["known"]),
        _all_dims_verdict("ghost", {"faithfulness": True, "category_accuracy": True,
                                    "importance_calibration": True, "ar_translation_quality": True}),
    ]
    result = calibrate_judge(verdicts, expectations)
    assert result["n_items"] == 1


def test_calibrate_judge_empty():
    result = calibrate_judge([], {})
    assert result["n_items"] == 0
    assert result["overall"]["accuracy"] == 0.0
    assert result["overall"]["n"] == 0
