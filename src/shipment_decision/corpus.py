"""The fixed synthetic corpus: 20 designed shipments (S01-S20) and 4 invalid
fixtures (X01-X04), exactly as tabulated in the approved specification.

Routes are given as (cost, transit_hours, delay_probability, geopolitical).
geopolitical=None means the key is absent on that route. Each shipment is
stored with priority "balanced"; the evaluator overrides the priority to run
all four methods. Nothing here is random.
"""

from __future__ import annotations

import copy
from typing import Any

ORIGIN = "Shanghai"
DESTINATION = "Rotterdam"


def _route(route_id: str, cost: float, hours: float, delay: float, geo: float | None,
           congestion: float | None = None, legs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    r: dict[str, Any] = {
        "route_id": route_id,
        "cost": cost,
        "transit_hours": hours,
        "delay_probability": delay,
    }
    risks: dict[str, float] = {}
    if geo is not None:
        risks["geopolitical"] = geo
    if congestion is not None:
        risks["congestion"] = congestion
    if risks:
        r["risks"] = risks
    if legs is not None:
        r["legs"] = legs
    return r


def _shipment(sid: str, routes: list[dict[str, Any]], *, purpose: str,
              weights: dict[str, float] | None = None,
              constraints: dict[str, float] | None = None) -> dict[str, Any]:
    s: dict[str, Any] = {
        "shipment_id": sid,
        "origin": ORIGIN,
        "destination": DESTINATION,
        "priority": "balanced",
        "routes": routes,
    }
    if weights is not None:
        s["weights"] = weights
    if constraints is not None:
        s["constraints"] = constraints
    s["_purpose"] = purpose  # stripped before validation
    return s


def _leg(a: str, b: str, mode: str, cost: float, hours: float) -> dict[str, Any]:
    return {"from": a, "to": b, "mode": mode, "cost": cost, "transit_hours": hours}


# --- shared route sets -------------------------------------------------------

def _s01_routes() -> list[dict[str, Any]]:
    return [
        _route("C", 1000, 300, 0.40, 0.10),
        _route("F", 1800, 200, 0.20, 0.80),
        _route("M", 1300, 250, 0.08, 0.30),
        _route("D", 1900, 320, 0.45, 0.85),
    ]


def _s03_routes() -> list[dict[str, Any]]:
    return [
        _route("C", 1000, 240, 0.40, 0.20, congestion=0.6, legs=[
            _leg("Shanghai", "Singapore", "sea", 400, 100),
            _leg("Singapore", "Rotterdam", "sea", 600, 140),
        ]),
        _route("R", 1200, 250, 0.08, 0.20, congestion=0.3, legs=[
            _leg("Shanghai", "Colombo", "sea", 500, 110),
            _leg("Colombo", "Rotterdam", "sea", 700, 140),
        ]),
        _route("F", 1600, 180, 0.15, 0.60, congestion=0.5, legs=[
            _leg("Shanghai", "Dubai", "sea", 700, 100),
            _leg("Dubai", "Rotterdam", "air", 900, 80),
        ]),
        _route("D", 1800, 300, 0.50, 0.90, congestion=0.7, legs=[
            _leg("Shanghai", "Singapore", "sea", 400, 100),
            _leg("Singapore", "Piraeus", "sea", 800, 130),
            _leg("Piraeus", "Rotterdam", "rail", 600, 70),
        ]),
    ]


def _s04_routes() -> list[dict[str, Any]]:
    return [
        _route("A", 100, 100, 0.40, 0.20),
        _route("B", 101, 101, 0.05, 0.20),
    ]


def _s11_routes(geo: bool = True) -> list[dict[str, Any]]:
    g = (lambda v: v) if geo else (lambda v: None)
    return [
        _route("P", 1300, 230, 0.16, g(0.05)),
        _route("Q", 1200, 210, 0.12, g(0.90)),
        _route("R", 2500, 400, 0.50, g(0.95)),
    ]


_THIRD = 1.0 / 3.0


def build_corpus() -> list[dict[str, Any]]:
    """Return S01..S20 as fresh dicts (callers may mutate)."""
    return [
        _shipment("S01", _s01_routes(), purpose="Four-way conflict among cost, time, delay, geopolitical"),
        _shipment("S02", [
            _route("C", 1000, 240, 0.10, 0.20),
            _route("M", 1600, 240, 0.09, 0.20),
            _route("F", 1500, 180, 0.12, 0.70),
            _route("D", 1700, 260, 0.20, 0.80),
        ], purpose="Tiny delay improvement against a large cost increase"),
        _shipment("S03", _s03_routes(), purpose="Brief's example: higher cost, much lower delay"),
        _shipment("S04", _s04_routes(), purpose="Two feasible routes: min-max erases gap size"),
        _shipment("S05", _s04_routes() + [_route("Z", 500, 500, 0.40, 0.20)],
                  purpose="S04 plus a non-winning route that changes the winner"),
        _shipment("S06", [
            _route("G", 1000, 200, 0.05, 0.10),
            _route("H", 1200, 220, 0.10, 0.20),
            _route("I", 1500, 260, 0.20, 0.40),
            _route("J", 2000, 300, 0.35, 0.70),
        ], purpose="One route best on every objective"),
        _shipment("S07", [
            _route("C", 1000, 300, 0.15, 0.10),
            _route("F", 1800, 200, 0.15, 0.80),
            _route("M", 1400, 240, 0.15, 0.30),
        ], purpose="Delay identical on all routes: normalized delay term is 0"),
        _shipment("S08", [
            _route("R_A", 1000, 220, 0.20, 0.30),
            _route("R_B", 1000, 260, 0.10, 0.30),
            _route("R_C", 1500, 210, 0.05, 0.40),
        ], purpose="Cost tie: min_cost falls through to delay tie-break"),
        _shipment("S09", [
            _route("A", 1000, 200, 0.10, 0.20),
            _route("B", 800, 300, 0.05, 0.10),
            _route("C", 900, 250, 0.08, 0.15),
        ], purpose="One feasible route under max_transit_hours", constraints={"max_transit_hours": 210}),
        _shipment("S10", _s01_routes(), purpose="Empty feasible set", constraints={"max_cost": 500}),
        _shipment("S11", _s11_routes(), purpose="Geopolitical risk changes the balanced winner"),
        _shipment("S12", _s11_routes(geo=False), purpose="S11 with geopolitical absent on every route"),
        _shipment("S13", [
            _route("R2", 1000, 200, 0.10, 0.20, congestion=0.1),
            _route("R1", 1000, 200, 0.10, 0.20, congestion=0.9),
        ], purpose="Congestion differs, scored fields equal; input order reversed"),
        _shipment("S14", [
            _route("A", 1000, 200, 0.27, 0.30),
            _route("B", 1100, 200, 0.10, 0.30),
            _route("C", 1500, 200, 1.00, 0.30),
        ], purpose="Near-tie with a delay value on the clipping boundary"),
        _shipment("S15", _s03_routes(), purpose="S03 with unequal explicit weights",
                  weights={"cost": 0.70, "time": 0.10, "delay": 0.10, "geopolitical": 0.10}),
        _shipment("S16", [_route("X", 1000, 200, 0.10, 0.20)], purpose="Single supplied route"),
        _shipment("S17", [
            _route("R_A", 1200, 240, 0.12, 0.25),
            _route("R_B", 1200, 240, 0.12, 0.25),
        ], purpose="All scored values equal"),
        _shipment("S18", _s11_routes(), purpose="S11 with explicit zero geopolitical weight",
                  weights={"cost": _THIRD, "time": _THIRD, "delay": 1.0 - 2.0 * _THIRD, "geopolitical": 0.0}),
        _shipment("S19", _s01_routes(), purpose="Cost limit applied before normalization",
                  constraints={"max_cost": 1500}),
        _shipment("S20", _s03_routes(), purpose="Delay limit applied before normalization (F at equality)",
                  constraints={"max_delay_probability": 0.15}),
    ]


def build_invalid_fixtures() -> list[dict[str, Any]]:
    """X01..X04: each must fail validation with the stated code."""
    x01 = _shipment("X01", [
        _route("A", 1000, 200, 0.10, 0.20),
        _route("B", 1100, 210, 0.08, None),
    ], purpose="Partial geopolitical support")
    x01["_expected_code"] = "incomplete_risk"

    x02 = _shipment("X02", _s11_routes(geo=False), purpose="Positive geopolitical weight with no data",
                    weights={"cost": 0.25, "time": 0.25, "delay": 0.25, "geopolitical": 0.25})
    x02["_expected_code"] = "objective_requested_without_data"

    x03 = _shipment("X03", _s03_routes(), purpose="Weights sum to 0.90",
                    weights={"cost": 0.30, "time": 0.30, "delay": 0.20, "geopolitical": 0.10})
    x03["_expected_code"] = "weights_sum"

    x04 = _shipment("X04", _s03_routes(), purpose="Negative cost on route C")
    for r in x04["routes"]:
        if r["route_id"] == "C":
            r["cost"] = -1000
            del r["legs"]  # leg sum would also mismatch; keep the fixture to a single fault
    x04["_expected_code"] = "cost_negative"
    return [x01, x02, x03, x04]


def strip_meta(shipment: dict[str, Any]) -> dict[str, Any]:
    """Return a deep copy without underscore-prefixed metadata keys."""
    out = copy.deepcopy(shipment)
    for key in [k for k in out if k.startswith("_")]:
        del out[key]
    return out


def get_shipment(sid: str) -> dict[str, Any]:
    for s in build_corpus() + build_invalid_fixtures():
        if s["shipment_id"] == sid:
            return s
    raise KeyError(sid)
