"""Evaluator and sensitivity tests. Expected flips are the hand-calculated
cases from the specification; everything else is checked for structural
correctness (n-handling, null handling, skip bookkeeping), not for a preferred
outcome."""

from fractions import Fraction as Fr

import pytest

from conftest import approx, corpus_shipment
from shipment_decision.corpus import build_corpus, build_invalid_fixtures
from shipment_decision.evaluate import (
    METHODS, _mean, aggregate, delay_sensitivity, evaluate_shipment, perturb_weights,
    render_markdown, run_evaluation, shipment_for_method, weight_sensitivity,
)
from shipment_decision.score import score_shipment
from shipment_decision.validate import validate_shipment


@pytest.fixture(scope="module")
def report():
    return run_evaluation()


def test_corpus_shape():
    corpus = build_corpus()
    assert [s["shipment_id"] for s in corpus] == [f"S{i:02d}" for i in range(1, 21)]
    assert all(1 <= len(s["routes"]) <= 4 for s in corpus)
    assert [f["shipment_id"] for f in build_invalid_fixtures()] == ["X01", "X02", "X03", "X04"]


def test_corpus_is_reproducible():
    assert build_corpus() == build_corpus()


def test_mean_excludes_none_and_reports_n():
    assert _mean([1.0, None, 3.0]) == {"mean": 2.0, "n": 2}
    assert _mean([None, None]) == {"mean": None, "n": 0}
    assert _mean([]) == {"mean": None, "n": 0}


def test_relative_gap_null_when_best_is_zero():
    s = corpus_shipment("S12")
    s["routes"][1]["delay_probability"] = 0.0  # Q becomes the zero-delay best
    ev = evaluate_shipment(s)
    for m in METHODS:
        po = ev["methods"][m]["objectives"]["delay"]
        assert po["best"] == 0.0 and po["rel_gap"] is None
        assert po["abs_gap"] is not None
    agg = aggregate([ev])
    assert agg["methods"]["min_cost"]["objectives"]["delay"]["mean_rel_gap"] == {"mean": None, "n": 0}
    assert agg["methods"]["min_cost"]["objectives"]["delay"]["mean_abs_gap"]["n"] == 1


def test_geopolitical_metrics_only_where_available(report):
    agg = report["aggregate"]
    for m in METHODS:
        assert agg["methods"][m]["objectives"]["geopolitical"]["mean_abs_gap"]["n"] == 18  # 19 scored - S12
        assert agg["methods"][m]["objectives"]["cost"]["mean_abs_gap"]["n"] == 19


def test_no_feasible_and_validation_bookkeeping(report):
    agg = report["aggregate"]
    assert agg["shipments_total"] == 20 and agg["shipments_scored"] == 19
    assert agg["no_feasible_rate"] == approx(1 / 20)
    assert all(fx["rejected"] and fx["expected_code"] in fx["codes"] for fx in report["validation_failures"])


def test_balanced_minimises_S_on_every_shipment_consistency_check(report):
    for ev in report["per_shipment"]:
        if ev["status"] != "recommended":
            continue
        s_values = {m: ev["methods"][m]["weighted_score_S"] for m in METHODS}
        assert s_values["balanced"] <= min(s_values.values()) + 1e-9, ev["shipment_id"]


def test_s15_and_s18_report_different_S_and_B_minimisers(report):
    by_id = {ev["shipment_id"]: ev for ev in report["per_shipment"]}
    assert by_id["S15"]["weighted_score_minimizer"] == "C" and by_id["S15"]["balance_gap_minimizer"] == "R"
    assert by_id["S18"]["weighted_score_minimizer"] == "Q" and by_id["S18"]["balance_gap_minimizer"] == "P"
    assert by_id["S19"]["balance_gap_minimizer_tied_with"] == ["M"]


def test_lexicographic_margins_are_null_in_report(report):
    for ev in report["per_shipment"]:
        if ev["status"] == "recommended":
            assert ev["methods"]["min_cost"]["score_margin"] is None
            assert ev["methods"]["min_time"]["score_margin"] is None
    assert report["aggregate"]["methods"]["min_cost"]["tie_rate"] == {"rate": None, "n": 0}


# --- weight perturbation rule ------------------------------------------------

def test_perturb_weights_preserves_simplex_and_zero_weights():
    w = {"cost": 0.25, "time": 0.25, "delay": 0.25, "geopolitical": 0.25}
    up, skip = perturb_weights(w, list(w), "delay", "up")
    assert skip is None
    assert up["delay"] == approx(0.35)
    for k in ("cost", "time", "geopolitical"):
        assert up[k] == approx(float(Fr(13, 60)))
    assert sum(up.values()) == approx(1.0)
    down, _ = perturb_weights(w, list(w), "delay", "down")
    assert down["delay"] == approx(0.15) and sum(down.values()) == approx(1.0)

    w0 = {"cost": 1 / 3, "time": 1 / 3, "delay": 1 - 2 / 3, "geopolitical": 0.0}
    up0, _ = perturb_weights(w0, ["cost", "time", "delay"], "cost", "up")
    assert up0["geopolitical"] == 0.0 and sum(up0.values()) == approx(1.0)


def test_perturb_weights_skip_reasons():
    assert perturb_weights({"cost": 1.0, "time": 0.0, "delay": 0.0, "geopolitical": 0.0}, ["cost"], "cost", "up") == (
        None, "weight_already_one")
    assert perturb_weights({"cost": 1.0, "time": 0.0, "delay": 0.0, "geopolitical": 0.0}, ["cost"], "cost", "down") == (
        None, "no_other_positive_weight")
    assert perturb_weights({"cost": 0.5, "time": 0.5, "delay": 0.0, "geopolitical": 0.0}, ["cost", "time"],
                           "delay", "down") == (None, "weight_already_zero")
    small = {"cost": 0.05, "time": 0.45, "delay": 0.5, "geopolitical": 0.0}
    down, skip = perturb_weights(small, ["cost", "time", "delay"], "cost", "down")
    assert skip is None and down["cost"] == 0.0 and sum(down.values()) == approx(1.0)


def test_s14_weight_perturbation_flips_as_calculated():
    v = validate_shipment(corpus_shipment("S14"))
    w = {"cost": 13 / 60, "time": 13 / 60, "delay": 0.35, "geopolitical": 13 / 60}
    res = score_shipment(v, weights_override=w)
    a = next(r for r in res["routes"] if r["route_id"] == "A")
    b = next(r for r in res["routes"] if r["route_id"] == "B")
    assert a["score"] == approx(float(Fr(119, 1800))) and b["score"] == approx(float(Fr(13, 300)))
    assert res["recommended_route_id"] == "B"


def test_weight_sensitivity_reports_s14_flip_and_margins(report):
    ws = report["weight_sensitivity"]
    assert "S14" in ws["shipments_flipped"]
    assert ws["perturbations_applied"] > 0
    assert ws["perturbations_skipped"] == sum(ws["skips_by_reason"].values())
    flipped_n = ws["mean_original_margin_flipped"]["n"]
    unflipped_n = ws["mean_original_margin_unflipped"]["n"]
    # 19 scored shipments, two (S09, S16) have null margin -> 17 contribute
    assert flipped_n + unflipped_n == 17
    s14 = [f for f in ws["flips"] if f["shipment_id"] == "S14"]
    assert {(f["objective"], f["direction"]) for f in s14} >= {("delay", "up")}


# --- delay perturbation --------------------------------------------------------

def test_uniform_shift_without_clipping_leaves_s01_unchanged():
    v = validate_shipment(corpus_shipment("S01"))
    base = score_shipment(v)
    for eps in (0.05, -0.05):
        ov = {r.route_id: r.delay_probability + eps for r in v.routes}
        res = score_shipment(v, delay_override=ov)
        assert res["recommended_route_id"] == base["recommended_route_id"]
        for rb, rr in zip(base["routes"], res["routes"]):
            assert rr["score"] == approx(rb["score"])
            assert rr["normalized"]["delay"] == approx(rb["normalized"]["delay"])


def test_s14_delay_perturbations_flip_as_calculated():
    v = validate_shipment(corpus_shipment("S14"))
    uniform = score_shipment(v, delay_override={"A": 0.32, "B": 0.15, "C": 1.0})
    a = next(r for r in uniform["routes"] if r["route_id"] == "A")
    b = next(r for r in uniform["routes"] if r["route_id"] == "B")
    assert a["score"] == approx(0.05) and b["score"] == approx(0.05)
    assert uniform["score_margin"] == 0.0 and uniform["recommended_route_id"] == "B"  # tie -> perturbed delay
    specific = score_shipment(v, delay_override={"A": 0.32})
    a = next(r for r in specific["routes"] if r["route_id"] == "A")
    assert a["score"] == approx(float(Fr(11, 180)))
    assert specific["recommended_route_id"] == "B"


def test_delay_sensitivity_structure(report):
    ds = report["delay_sensitivity"]
    for family in ("uniform", "route_specific"):
        for m in METHODS:
            s = ds[family][m]
            assert s["perturbations_applied"] > 0
            assert 0 <= s["perturbations_flipped"] <= s["perturbations_applied"]
            if m in ("min_cost", "min_time"):
                assert s["mean_original_margin_flipped"] == {"mean": None, "n": 0}
                assert s["mean_original_margin_unflipped"] == {"mean": None, "n": 0}
    assert "S14" in ds["uniform"]["balanced"]["shipments_flipped"]
    assert "S14" in ds["route_specific"]["balanced"]["shipments_flipped"]
    # S20: F at 0.15 + 0.05 exceeds the 0.15 limit -> counted, never applied to feasibility
    assert ds["uniform"]["balanced"]["limit_crossings_counted_not_applied"] >= 1


def test_shipment_for_method_strips_weights_outside_balanced():
    s = build_corpus()[14]  # S15 has explicit weights
    assert "weights" in shipment_for_method(s, "balanced")
    assert "weights" not in shipment_for_method(s, "min_cost")
    assert "_purpose" not in shipment_for_method(s, "balanced")


def test_render_markdown_contains_all_sections(report):
    md = render_markdown(report)
    for heading in ("## Winners per shipment", "## Aggregate by method", "## Validation fixtures",
                    "## Weight sensitivity", "## Delay-probability sensitivity"):
        assert heading in md
    assert "S15 |" in md and "| C | R |" in md  # S-min C, B-min R
