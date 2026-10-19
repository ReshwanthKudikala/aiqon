"""Numerical checks against the hand-derived (exact rational) expectations in
the approved specification. All float comparisons use ABS_TOL = 1e-9."""

from fractions import Fraction as Fr

import pytest

from conftest import approx, corpus_shipment, route, run
from shipment_decision.constants import SCORE_TIE_TOL
from shipment_decision.score import _cmp_tol, normalize, score_shipment
from shipment_decision.validate import validate_shipment

THIRD = 1 / 3

# sid -> (balanced winner, min_cost, min_time, min_risk)
WINNERS = {
    "S01": ("M", "C", "F", "M"),
    "S02": ("C", "C", "F", "M"),
    "S03": ("R", "C", "F", "R"),
    "S04": ("A", "A", "A", "B"),
    "S05": ("B", "A", "A", "B"),
    "S06": ("G", "G", "G", "G"),
    "S07": ("C", "C", "F", "C"),
    "S08": ("R_A", "R_B", "R_C", "R_B"),
    "S09": ("A", "A", "A", "A"),
    "S11": ("P", "Q", "Q", "P"),
    "S12": ("Q", "Q", "Q", "Q"),
    "S13": ("R1", "R1", "R1", "R1"),
    "S14": ("A", "A", "B", "B"),
    "S15": ("C", "C", "F", "R"),
    "S16": ("X", "X", "X", "X"),
    "S17": ("R_A", "R_A", "R_A", "R_A"),
    "S18": ("Q", "Q", "Q", "P"),
    "S19": ("M", "C", "M", "C"),
    "S20": ("R", "R", "F", "R"),
}

# sid -> {route: balanced S} for feasible routes (exact fractions from the spec)
BALANCED_SCORES = {
    "S01": {"C": Fr(377, 888), "F": Fr(1787, 3330), "M": Fr(61, 240), "D": Fr(1)},
    "S02": {"C": Fr(37, 176), "M": Fr(45, 112), "F": Fr(841, 1848), "D": Fr(1)},
    "S03": {"C": Fr(53, 168), "R": Fr(5, 24), "F": Fr(125, 336), "D": Fr(1)},
    "S04": {"A": Fr(1, 4), "B": Fr(1, 2)},
    "S05": {"A": Fr(1, 4), "B": Fr(1, 800), "Z": Fr(3, 4)},
    "S06": {"G": Fr(0), "H": Fr(11, 60), "I": Fr(21, 40), "J": Fr(1)},
    "S07": {"C": Fr(1, 4), "F": Fr(1, 2), "M": Fr(83, 280)},
    "S08": {"R_A": Fr(3, 10), "R_B": Fr(1, 3), "R_C": Fr(1, 2)},
    "S09": {"A": Fr(0)},
    "S11": {"P": Fr(71, 988), "Q": Fr(17, 72), "R": Fr(1)},
    "S12": {"P": Fr(71, 741), "Q": Fr(0), "R": Fr(1)},
    "S13": {"R1": Fr(0), "R2": Fr(0)},
    "S14": {"A": Fr(17, 360), "B": Fr(1, 20), "C": Fr(1, 2)},
    "S15": {"C": Fr(53, 420), "R": Fr(7, 30), "F": Fr(503, 840), "D": Fr(1)},
    "S16": {"X": Fr(0)},
    "S17": {"R_A": Fr(0), "R_B": Fr(0)},
    "S18": {"P": Fr(71, 741), "Q": Fr(0), "R": Fr(1)},
    "S19": {"C": Fr(1, 2), "M": Fr(1, 2)},
    "S20": {"R": Fr(1, 4), "F": Fr(3, 4)},
}

MARGINS = {
    "S01": Fr(377, 888) - Fr(61, 240),  # runner-up C
    "S03": Fr(53, 168) - Fr(5, 24),
    "S04": Fr(1, 4), "S05": Fr(1, 4) - Fr(1, 800), "S06": Fr(11, 60),
    "S07": Fr(83, 280) - Fr(1, 4), "S08": Fr(1, 30), "S11": Fr(17, 72) - Fr(71, 988),
    "S12": Fr(71, 741), "S13": Fr(0), "S14": Fr(1, 360), "S15": Fr(7, 30) - Fr(53, 420),
    "S17": Fr(0), "S18": Fr(71, 741), "S19": Fr(0), "S20": Fr(1, 2),
}


@pytest.mark.parametrize("sid", sorted(WINNERS))
def test_winners_all_four_modes(sid):
    expected = WINNERS[sid]
    for mode, want in zip(("balanced", "min_cost", "min_time", "min_risk"), expected):
        res = run(sid, mode)
        assert res["status"] == "recommended", (sid, mode)
        assert res["recommended_route_id"] == want, (sid, mode, res["recommended_route_id"])


@pytest.mark.parametrize("sid", sorted(BALANCED_SCORES))
def test_balanced_scores_exact(sid):
    res = run(sid, "balanced")
    for rid, want in BALANCED_SCORES[sid].items():
        assert route(res, rid)["score"] == approx(float(want)), (sid, rid)
    # balanced recommendation minimises S among feasible routes (consistency check only)
    feasible = [r for r in res["routes"] if r["feasible"]]
    smin = min(r["score"] for r in feasible)
    assert route(res, res["recommended_route_id"])["score"] <= smin + SCORE_TIE_TOL


@pytest.mark.parametrize("sid", sorted(MARGINS))
def test_balanced_margins(sid):
    res = run(sid, "balanced")
    assert res["score_margin"] == approx(float(MARGINS[sid]))


def test_margin_null_rules():
    for sid in ("S09", "S16"):
        for mode in ("balanced", "min_risk", "min_cost", "min_time"):
            res = run(sid, mode)
            assert res["score_margin"] is None and res["runner_up_route_id"] is None
    for sid in ("S01", "S03", "S19"):
        for mode in ("min_cost", "min_time"):
            res = run(sid, mode)
            assert res["score_margin"] is None
            assert res["runner_up_route_id"] is not None
            assert all(r["score"] is None and r["contributions"] is None for r in res["routes"])


def test_s10_no_feasible_route_everywhere():
    for mode in ("balanced", "min_cost", "min_time", "min_risk"):
        res = run("S10", mode)
        assert res["status"] == "no_feasible_route"
        assert res["recommended_route_id"] is None and res["runner_up_route_id"] is None
        assert res["score_margin"] is None and res["comparison"] is None
        assert res["normalization_notes"] == []
        for r in res["routes"]:
            assert r["feasible"] is False and r["failed_constraints"] == ["max_cost"]
            for key in ("normalized", "contributions", "score", "rank", "balance_gap",
                        "non_dominated_all_available", "non_dominated_selection"):
                assert r[key] is None, key
        assert res["effective_weights"] is not None or mode in ("min_cost", "min_time")


def test_s19_limit_applied_before_normalization():
    res = run("S19")
    assert [r["route_id"] for r in res["routes"] if r["feasible"]] == ["C", "M"]
    assert route(res, "F")["failed_constraints"] == ["max_cost"]
    assert route(res, "C")["score"] == approx(0.5) and route(res, "M")["score"] == approx(0.5)
    assert res["score_margin"] == 0.0 and res["recommended_route_id"] == "M"  # tie -> lower delay


def test_s20_equality_with_limit_is_feasible_and_delay_normalises_to_one():
    res = run("S20")
    assert route(res, "F")["feasible"] is True  # 0.15 <= 0.15
    assert route(res, "F")["normalized"]["delay"] == approx(1.0)
    assert route(res, "R")["normalized"]["delay"] == approx(0.0)
    assert route(res, "C")["failed_constraints"] == ["max_delay_probability"]


def test_s07_zero_range_note_and_no_division():
    res = run("S07")
    assert res["normalization_notes"] == ["delay"]
    assert all(r["normalized"]["delay"] == 0.0 for r in res["routes"])


def test_s09_single_feasible_route_all_normalised_zero():
    res = run("S09")
    a = route(res, "A")
    assert a["normalized"] == {"cost": 0.0, "time": 0.0, "delay": 0.0, "geopolitical": 0.0}
    assert a["score"] == 0.0 and a["balance_gap"] == 0.0 and a["rank"] == 1
    assert route(res, "B")["failed_constraints"] == ["max_transit_hours"]
    assert res["normalization_notes"] == []


def test_s13_congestion_never_matters_and_order_is_by_id():
    base = run("S13")
    assert base["recommended_route_id"] == "R1" and base["score_margin"] == 0.0
    swapped = corpus_shipment("S13")
    swapped["routes"][0]["risks"]["congestion"], swapped["routes"][1]["risks"]["congestion"] = (
        swapped["routes"][1]["risks"]["congestion"], swapped["routes"][0]["risks"]["congestion"])
    res = score_shipment(validate_shipment(swapped))
    assert res["recommended_route_id"] == "R1"
    assert [r["score"] for r in res["routes"]] == [r["score"] for r in base["routes"]]
    removed = corpus_shipment("S13")
    for r in removed["routes"]:
        del r["risks"]["congestion"]
    assert score_shipment(validate_shipment(removed))["recommended_route_id"] == "R1"


def test_reversed_input_order_does_not_change_tied_recommendation():
    s = corpus_shipment("S17")
    s["routes"].reverse()
    assert score_shipment(validate_shipment(s))["recommended_route_id"] == "R_A"


def test_s08_cost_tie_breaks_on_delay_under_min_cost():
    res = run("S08", "min_cost")
    assert res["recommended_route_id"] == "R_B" and res["runner_up_route_id"] == "R_A"
    assert [route(res, rid)["rank"] for rid in ("R_A", "R_B", "R_C")] == [2, 1, 3]


def test_s14_min_time_hours_tie_breaks_on_delay():
    res = run("S14", "min_time")
    assert res["recommended_route_id"] == "B"


def test_dominance_flags():
    res = run("S01")
    assert route(res, "D")["non_dominated_all_available"] is False
    assert route(res, "D")["non_dominated_selection"] is False
    for rid in ("C", "F", "M"):
        assert route(res, rid)["non_dominated_all_available"] is True
    res6 = run("S06")
    assert [route(res6, rid)["non_dominated_all_available"] for rid in ("G", "H", "I", "J")] == [True, False, False, False]
    # min_risk selection set is {delay, geopolitical}: C and F are dominated by R on that set in S03
    res3 = run("S03", "min_risk")
    assert route(res3, "C")["non_dominated_selection"] is False
    assert route(res3, "C")["non_dominated_all_available"] is True


def test_balanced_recommendation_non_dominated_on_active_set_for_all_corpus(corpus):
    for s in corpus:
        res = run(s["shipment_id"])
        if res["status"] != "recommended":
            continue
        assert route(res, res["recommended_route_id"])["non_dominated_selection"] is True, s["shipment_id"]


def test_s18_zero_weight_keeps_raw_geopolitical_and_balance_gap():
    res = run("S18")
    assert res["objectives_active"] == ["cost", "time", "delay"]
    assert res["objectives_inactive"] == [{"name": "geopolitical", "reason": "explicit_weight_zero"}]
    assert res["objectives_available"] == ["cost", "time", "delay", "geopolitical"]
    q = route(res, "Q")
    assert q["geopolitical"] == 0.90 and "geopolitical" not in q["contributions"]
    assert q["balance_gap"] == approx(0.85 / 0.90)  # B includes the inactive objective
    assert route(res, "P")["balance_gap"] == approx(100 / 1300 + 20 / 190 + 0.04 / 0.38)


def test_s12_unavailable_geopolitical_is_not_zero_filled():
    res = run("S12")
    assert res["objectives_available"] == ["cost", "time", "delay"]
    for r in res["routes"]:
        assert "geopolitical" not in r["normalized"] and r["geopolitical"] is None
    assert res["comparison"]["lowest_geopolitical"] is None
    assert res["effective_weights"]["geopolitical"] == 0.0
    assert res["weight_source"] == "default_geopolitical_unavailable"


def test_s15_unequal_weights_s_and_b_minimisers_differ():
    res = run("S15")
    assert res["recommended_route_id"] == "C"
    feasible = [r for r in res["routes"] if r["feasible"]]
    assert min(feasible, key=lambda r: r["balance_gap"])["route_id"] == "R"
    assert route(res, "R")["balance_gap"] == approx(float(Fr(5, 6)))
    assert route(res, "C")["balance_gap"] == approx(float(Fr(53, 42)))


def test_normalize_helper():
    assert normalize([5.0]) == [0.0]
    assert normalize([2.0, 2.0, 2.0]) == [0.0, 0.0, 0.0]
    assert normalize([1.0, 3.0, 2.0]) == [0.0, 1.0, 0.5]


def test_score_tie_tolerance_is_1e9():
    assert _cmp_tol(0.5, 0.5 + 0.5e-9) == 0          # within tolerance: tie
    assert _cmp_tol(0.5, 0.5 + 2e-9) == -1           # beyond tolerance: ordered
    assert _cmp_tol(0.5 + 2e-9, 0.5) == 1
    res = run("S19")  # exact tie at 0.5 -> margin reported as 0.0, tie-break on delay picks M
    assert res["score_margin"] == 0.0 and res["recommended_route_id"] == "M"


def test_comparison_block_s03():
    res = run("S03")
    cmp = res["comparison"]
    assert cmp["cheapest"] == {"route_id": "C", "value": 1000.0}
    assert cmp["fastest"] == {"route_id": "F", "value": 180.0}
    assert cmp["lowest_delay"] == {"route_id": "R", "value": 0.08}
    assert cmp["lowest_geopolitical"] == {"route_id": "C", "value": 0.20}  # tie C/R -> id
    vs = cmp["versus_runner_up"]
    assert vs["cost"] == {"recommended": 1200.0, "runner_up": 1000.0, "difference": 200.0}
    assert vs["delay"]["recommended"] == 0.08 and vs["delay"]["runner_up"] == 0.40


def test_delay_override_does_not_change_feasibility():
    v = validate_shipment(corpus_shipment("S20"))
    res = score_shipment(v, delay_override={"F": 0.20})  # above the 0.15 limit
    assert route(res, "F")["feasible"] is True
    assert route(res, "F")["delay_probability"] == 0.20


def test_weights_override_only_for_balanced():
    v = validate_shipment(corpus_shipment("S03", "min_cost"))
    with pytest.raises(ValueError):
        score_shipment(v, weights_override={"cost": 1.0, "time": 0.0, "delay": 0.0, "geopolitical": 0.0})
