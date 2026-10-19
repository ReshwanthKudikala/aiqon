import copy

import pytest

from conftest import approx, corpus_shipment
from shipment_decision.validate import ValidationError, validate_shipment


def codes(exc: ValidationError) -> set[str]:
    return {e["code"] for e in exc.errors}


def expect_codes(shipment, *expected: str) -> ValidationError:
    with pytest.raises(ValidationError) as info:
        validate_shipment(shipment)
    assert set(expected) <= codes(info.value), info.value.errors
    return info.value


# --- invalid fixtures X01-X04 -------------------------------------------------

def test_invalid_fixtures_fail_with_expected_codes(invalid_fixtures):
    for fx in invalid_fixtures:
        exc = expect_codes({k: v for k, v in fx.items() if not k.startswith("_")}, fx["_expected_code"])
        assert exc.shipment_id == fx["shipment_id"]


def test_x01_lists_the_routes_missing_geopolitical():
    exc = expect_codes(corpus_shipment("X01"), "incomplete_risk")
    msg = next(e for e in exc.errors if e["code"] == "incomplete_risk")["message"]
    assert "B" in msg and "A" not in msg.split(":")[-1]


# --- geopolitical common-support rule ----------------------------------------

def test_null_geopolitical_counts_as_absent_not_zero():
    s = corpus_shipment("S11")
    s["routes"][0]["risks"]["geopolitical"] = None
    expect_codes(s, "incomplete_risk")


def test_empty_support_disables_objective_and_uses_third_defaults():
    v = validate_shipment(corpus_shipment("S12"))
    assert v.geopolitical_available is False
    assert v.objectives_available == ("cost", "time", "delay")
    assert v.objectives_active == ("cost", "time", "delay")
    assert v.objectives_unavailable == ({"name": "geopolitical", "reason": "absent_on_all_routes"},)
    assert v.weight_source == "default_geopolitical_unavailable"
    w = v.effective_weights
    assert w["cost"] == approx(1 / 3) and w["time"] == approx(1 / 3) and w["delay"] == approx(1 / 3)
    assert w["geopolitical"] == 0.0
    assert sum(w.values()) == 1.0  # exact: delay takes the remainder


def test_positive_geopolitical_weight_without_data_is_rejected_not_renormalised():
    expect_codes(corpus_shipment("X02"), "objective_requested_without_data")


def test_zero_geopolitical_weight_with_no_data_is_allowed():
    s = corpus_shipment("S12", weights={"cost": 0.5, "time": 0.25, "delay": 0.25, "geopolitical": 0.0})
    v = validate_shipment(s)
    assert v.weight_source == "explicit"
    assert v.objectives_inactive == ()  # unavailable, not inactive


# --- weights -------------------------------------------------------------------

def test_explicit_weights_must_sum_to_one_and_are_not_rescaled():
    expect_codes(corpus_shipment("X03"), "weights_sum")
    s = corpus_shipment("S03", weights={"cost": 0.5, "time": 0.25, "delay": 0.25, "geopolitical": 0.0})
    v = validate_shipment(s)
    assert v.effective_weights == {"cost": 0.5, "time": 0.25, "delay": 0.25, "geopolitical": 0.0}
    assert v.objectives_active == ("cost", "time", "delay")
    assert v.objectives_inactive == ({"name": "geopolitical", "reason": "explicit_weight_zero"},)


def test_weights_sum_tolerance_is_1e6():
    base = {"cost": 0.25, "time": 0.25, "delay": 0.25}
    ok = validate_shipment(corpus_shipment("S03", weights={**base, "geopolitical": 0.25 + 5e-7}))
    assert ok.weight_source == "explicit"
    expect_codes(corpus_shipment("S03", weights={**base, "geopolitical": 0.25 + 5e-6}), "weights_sum")


def test_geopolitical_weight_key_required_when_data_present():
    expect_codes(corpus_shipment("S03", weights={"cost": 0.4, "time": 0.3, "delay": 0.3}), "weights_missing_key")


def test_negative_weight_rejected():
    expect_codes(corpus_shipment("S03", weights={"cost": 1.2, "time": -0.2, "delay": 0.0, "geopolitical": 0.0}),
                 "weight_negative")


def test_weights_not_allowed_outside_balanced():
    s = corpus_shipment("S03", "min_cost")
    s["weights"] = {"cost": 0.25, "time": 0.25, "delay": 0.25, "geopolitical": 0.25}
    expect_codes(s, "weights_not_allowed")


def test_default_weights_when_geopolitical_available():
    v = validate_shipment(corpus_shipment("S03"))
    assert v.effective_weights == {"cost": 0.25, "time": 0.25, "delay": 0.25, "geopolitical": 0.25}
    assert v.weight_source == "default"


def test_min_risk_fixed_weights():
    assert validate_shipment(corpus_shipment("S03", "min_risk")).effective_weights == {"delay": 0.5, "geopolitical": 0.5}
    assert validate_shipment(corpus_shipment("S12", "min_risk")).effective_weights == {"delay": 1.0}


def test_lexicographic_modes_have_no_weights_but_selection_keys():
    v = validate_shipment(corpus_shipment("S03", "min_cost"))
    assert v.effective_weights is None and v.weight_source == "not_applicable"
    assert v.selection_keys == ("cost", "delay", "time")
    assert validate_shipment(corpus_shipment("S03", "min_time")).selection_keys == ("time", "delay", "cost")


# --- routes --------------------------------------------------------------------

def test_required_route_fields_and_ranges():
    s = corpus_shipment("S03")
    del s["routes"][0]["delay_probability"]
    expect_codes(s, "missing_field")
    s = corpus_shipment("S03")
    s["routes"][0]["delay_probability"] = 1.5
    expect_codes(s, "out_of_range")
    s = corpus_shipment("S03")
    s["routes"][0]["transit_hours"] = 0
    expect_codes(s, "transit_hours_not_positive")
    s = corpus_shipment("S03")
    s["routes"][0]["cost"] = float("inf")
    expect_codes(s, "not_finite")


def test_unknown_risk_name_rejected():
    s = corpus_shipment("S03")
    s["routes"][0]["risks"]["weather"] = 0.2
    expect_codes(s, "unknown_risk")


def test_duplicate_route_id_rejected():
    s = corpus_shipment("S03")
    s["routes"][1]["route_id"] = s["routes"][0]["route_id"]
    expect_codes(s, "duplicate_route_id")


def test_empty_routes_and_missing_priority():
    expect_codes(corpus_shipment("S03", routes=[]), "no_routes")
    s = corpus_shipment("S03")
    del s["priority"]
    expect_codes(s, "missing_field")
    expect_codes(corpus_shipment("S03", priority="fastest"), "invalid_priority")


def test_origin_must_differ_from_destination():
    expect_codes(corpus_shipment("S12", destination="Shanghai"), "origin_equals_destination")


# --- legs ----------------------------------------------------------------------

def test_leg_sums_must_match_route_totals():
    s = corpus_shipment("S03")
    s["routes"][0]["legs"][0]["cost"] += 1.0
    expect_codes(s, "legs_sum_mismatch")
    s = corpus_shipment("S03")
    s["routes"][0]["legs"][0]["transit_hours"] += 0.5
    expect_codes(s, "legs_sum_mismatch")


def test_leg_sum_tolerance_is_0_01():
    s = corpus_shipment("S03")
    s["routes"][0]["legs"][0]["cost"] += 0.005
    validate_shipment(s)  # within tolerance


def test_legs_must_connect_origin_to_destination():
    s = corpus_shipment("S03")
    s["routes"][0]["legs"][0]["to"] = "Mumbai"
    expect_codes(s, "legs_disconnected")
    s = corpus_shipment("S03")
    s["routes"][0]["legs"][-1]["to"] = "Hamburg"
    expect_codes(s, "legs_disconnected")


# --- constraints ---------------------------------------------------------------

def test_constraint_validation():
    expect_codes(corpus_shipment("S03", constraints={"max_delay_probability": 1.5}), "out_of_range")
    expect_codes(corpus_shipment("S03", constraints={"max_cost": -1}), "constraint_out_of_range")
    expect_codes(corpus_shipment("S03", constraints={"max_weight": 10}), "unknown_constraint")
    v = validate_shipment(corpus_shipment("S03", constraints={"max_cost": 1500, "max_transit_hours": None}))
    assert v.constraints == {"max_cost": 1500.0}


def test_routes_sorted_by_id_regardless_of_input_order():
    v = validate_shipment(corpus_shipment("S13"))
    assert [r.route_id for r in v.routes] == ["R1", "R2"]


def test_non_object_input():
    with pytest.raises(ValidationError) as info:
        validate_shipment([1, 2, 3])
    assert codes(info.value) == {"not_an_object"}
