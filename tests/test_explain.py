"""The explainer may only restate the result object. These tests check that
every number in the text equals the corresponding result field (after the
presentation rounding defined in explain.py) and that required statements
appear for each status/mode."""

import re

from conftest import corpus_shipment, route, run
from shipment_decision import decide
from shipment_decision.explain import explain, fmt_money, fmt_prob, fmt_score, fmt_weight


def test_s03_balanced_states_cost_increase_and_delay_decrease():
    res = run("S03")
    text = explain(res)
    rec, ru = route(res, "R"), route(res, "C")
    assert "recommended route R" in text
    assert f"cost {fmt_money(rec['cost'])} vs {fmt_money(ru['cost'])} (higher)" in text  # 1,200 vs 1,000
    assert f"delay probability {fmt_prob(rec['delay_probability'])} vs {fmt_prob(ru['delay_probability'])} (lower)" in text
    assert f"Weighted score {fmt_score(rec['score'])} versus {fmt_score(ru['score'])}" in text
    assert f"margin {fmt_score(res['score_margin'])}" in text
    for k, w in res["effective_weights"].items():
        assert fmt_weight(w) in text
    for k, v in rec["contributions"].items():
        assert fmt_score(v) in text
    assert "cheapest C (1,000)" in text and "fastest F (180 h)" in text and "lowest delay R (0.080)" in text
    assert "Dominated on every available objective by another feasible route: D." in text


def test_numbers_in_text_come_from_result_object():
    res = run("S01")
    text = explain(res)
    numbers = set(re.findall(r"\d+(?:,\d{3})*(?:\.\d+)?", text))
    allowed = set()
    for r in res["routes"]:
        allowed |= {fmt_money(r["cost"]), f"{r['transit_hours']:g}", fmt_prob(r["delay_probability"]),
                    fmt_prob(r["geopolitical"])}
        if r["score"] is not None:
            allowed.add(fmt_score(r["score"]))
            allowed |= {fmt_score(v) for v in r["contributions"].values()}
    allowed |= {fmt_weight(w) for w in res["effective_weights"].values()}
    allowed.add(fmt_score(res["score_margin"]))
    allowed |= {"01"}  # the shipment id S01
    unexplained = {n for n in numbers if n not in allowed}
    assert not unexplained, unexplained


def test_lexicographic_explanation_has_no_score_and_names_key_order():
    text = explain(run("S03", "min_cost"))
    assert "Weighted score" not in text
    assert "lowest cost, then delay probability, then transit time, then route id" in text
    assert "Runner-up by the same ordering: R." in text


def test_min_risk_explanation():
    text = explain(run("S03", "min_risk"))
    assert "Priority 'min_risk'" in text and "delay probability 0.500, geopolitical risk 0.500" in text


def test_single_feasible_route_explanation_lists_exclusions():
    text = explain(run("S09"))
    assert "only feasible route" in text
    assert "Excluded by hard constraints: B (max_transit_hours); C (max_transit_hours)." in text


def test_no_feasible_route_explanation():
    text = explain(run("S10"))
    assert "no route satisfies the hard constraints (max_cost=500)" in text
    assert "no constraint was relaxed" in text
    assert text.count("excluded by max_cost") == 4


def test_tie_statement_and_notes():
    text = explain(run("S19"))
    assert "The top scores tie" in text and "delay probability, cost, transit time, route id" in text
    text7 = explain(run("S07"))
    assert "Identical across all feasible routes and therefore not affecting the ranking: delay probability." in text7


def test_unavailable_and_inactive_statements():
    assert "Geopolitical risk is absent on every route and was not scored." in explain(run("S12"))
    assert "Geopolitical risk has weight 0 and was not scored; raw values are still reported." in explain(run("S18"))


def test_invalid_input_explanation_enumerates_errors():
    res = decide(corpus_shipment("X03"))
    assert res["status"] == "invalid_input"
    assert "input rejected" in res["explanation"] and "weights_sum at weights" in res["explanation"]


def test_decide_is_deterministic():
    a = decide(corpus_shipment("S03"))
    b = decide(corpus_shipment("S03"))
    assert a == b
