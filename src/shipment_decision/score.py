"""Feasibility, normalization, selection, dominance, margin.

score_shipment() is a pure function of a ValidatedShipment plus two optional
overrides used only by the sensitivity experiments:

  weights_override  - replaces the balanced effective weights (sum to 1, >= 0)
  delay_override    - {route_id: p} used for normalization, scoring, tie-breaks
                      and reported raw values; feasibility ALWAYS uses the
                      original delay probabilities.

No rounding happens here. Floats are carried at full precision.
"""

from __future__ import annotations

from functools import cmp_to_key
from typing import Any

from shipment_decision.constants import CONSTRAINT_ORDER, SCORE_TIE_TOL, SCORED_RISK
from shipment_decision.schema import base_result
from shipment_decision.validate import Route, ValidatedShipment

_LIMIT_FIELD = {
    "max_cost": "cost",
    "max_transit_hours": "time",
    "max_delay_probability": "delay",
}


# ---------------------------------------------------------------------------
# small numeric helpers
# ---------------------------------------------------------------------------

def _cmp_exact(a: float, b: float) -> int:
    return (a > b) - (a < b)


def _cmp_tol(a: float, b: float, tol: float = SCORE_TIE_TOL) -> int:
    if abs(a - b) <= tol:
        return 0
    return (a > b) - (a < b)


def normalize(values: list[float]) -> list[float]:
    """Min-max over the given list; all zeros if one value or zero range."""
    if len(values) <= 1:
        return [0.0] * len(values)
    lo, hi = min(values), max(values)
    if hi == lo:
        return [0.0] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


def _dominates(a: dict[str, float], b: dict[str, float], objectives: tuple[str, ...]) -> bool:
    """True if a is no worse than b on every objective and strictly better on one."""
    strictly_better = False
    for obj in objectives:
        if a[obj] > b[obj]:
            return False
        if a[obj] < b[obj]:
            strictly_better = True
    return strictly_better


# ---------------------------------------------------------------------------
# main entry
# ---------------------------------------------------------------------------

def score_shipment(
    shipment: ValidatedShipment,
    *,
    weights_override: dict[str, float] | None = None,
    delay_override: dict[str, float] | None = None,
) -> dict[str, Any]:
    result = base_result(shipment.shipment_id, shipment.priority)
    priority = shipment.priority
    available = shipment.objectives_available
    weights = shipment.effective_weights
    if weights_override is not None:
        if priority != "balanced":
            raise ValueError("weights_override is only valid for balanced priority")
        weights = dict(weights_override)
    active = shipment.objectives_active
    if weights_override is not None:
        active = tuple(k for k in ("cost", "time", "delay", SCORED_RISK) if weights.get(k, 0.0) > 0)

    result.update({
        "objectives_available": list(available),
        "objectives_active": list(active),
        "objectives_inactive": [dict(x) for x in shipment.objectives_inactive],
        "objectives_unavailable": [dict(x) for x in shipment.objectives_unavailable],
        "effective_weights": dict(weights) if weights is not None else None,
        "weight_source": shipment.weight_source,
        "selection_keys": list(shipment.selection_keys) if shipment.selection_keys else None,
        "constraints_applied": dict(shipment.constraints),
        "normalization_notes": [],
    })

    # Effective raw values per route (delay may be overridden for experiments).
    def raw_value(route: Route, objective: str) -> float:
        if objective == "delay" and delay_override is not None and route.route_id in delay_override:
            return delay_override[route.route_id]
        value = route.raw(objective)
        assert value is not None  # available objectives are present on every route
        return value

    # Feasibility uses ORIGINAL values.
    routes_out: dict[str, dict[str, Any]] = {}
    feasible: list[Route] = []
    for route in shipment.routes:
        failed = []
        for limit in CONSTRAINT_ORDER:
            if limit in shipment.constraints:
                if route.raw(_LIMIT_FIELD[limit]) > shipment.constraints[limit]:
                    failed.append(limit)
        entry = {
            "route_id": route.route_id,
            "cost": route.cost,
            "transit_hours": route.transit_hours,
            "delay_probability": raw_value(route, "delay"),
            "geopolitical": route.geopolitical,
            "congestion": route.congestion,
            "legs": route.legs,
            "feasible": not failed,
            "failed_constraints": failed,
            "normalized": None,
            "contributions": None,
            "score": None,
            "rank": None,
            "non_dominated_all_available": None,
            "non_dominated_selection": None,
            "balance_gap": None,
        }
        routes_out[route.route_id] = entry
        if not failed:
            feasible.append(route)

    result["routes"] = [routes_out[r.route_id] for r in shipment.routes]  # already sorted by id

    if not feasible:
        result["status"] = "no_feasible_route"
        return result

    # Normalization on the feasible set, for every available objective.
    raw: dict[str, dict[str, float]] = {
        r.route_id: {obj: raw_value(r, obj) for obj in available} for r in feasible
    }
    normalized: dict[str, dict[str, float]] = {r.route_id: {} for r in feasible}
    for obj in available:
        values = [raw[r.route_id][obj] for r in feasible]
        norm = normalize(values)
        if len(feasible) > 1 and max(values) == min(values):
            result["normalization_notes"].append(obj)
        for r, n in zip(feasible, norm):
            normalized[r.route_id][obj] = n

    # Weighted score (balanced, min_risk) and balance gap (all modes).
    scores: dict[str, float | None] = {}
    contributions: dict[str, dict[str, float] | None] = {}
    for r in feasible:
        rid = r.route_id
        routes_out[rid]["normalized"] = dict(normalized[rid])
        routes_out[rid]["balance_gap"] = sum(normalized[rid][obj] for obj in available)
        if weights is not None:
            contrib = {obj: weights[obj] * normalized[rid][obj] for obj in active}
            contributions[rid] = contrib
            scores[rid] = sum(contrib.values())
        else:
            contributions[rid] = None
            scores[rid] = None
        routes_out[rid]["contributions"] = contributions[rid]
        routes_out[rid]["score"] = scores[rid]

    # Total order for the mode.
    def compare(a: Route, b: Route) -> int:
        pa, pb = raw_value(a, "delay"), raw_value(b, "delay")
        if priority == "balanced":
            keys = [
                _cmp_tol(scores[a.route_id], scores[b.route_id]),
                _cmp_exact(pa, pb), _cmp_exact(a.cost, b.cost), _cmp_exact(a.transit_hours, b.transit_hours),
            ]
        elif priority == "min_risk":
            keys = [
                _cmp_tol(scores[a.route_id], scores[b.route_id]),
                _cmp_exact(a.cost, b.cost), _cmp_exact(a.transit_hours, b.transit_hours),
            ]
        elif priority == "min_cost":
            keys = [_cmp_exact(a.cost, b.cost), _cmp_exact(pa, pb), _cmp_exact(a.transit_hours, b.transit_hours)]
        else:  # min_time
            keys = [_cmp_exact(a.transit_hours, b.transit_hours), _cmp_exact(pa, pb), _cmp_exact(a.cost, b.cost)]
        for k in keys:
            if k != 0:
                return k
        return (a.route_id > b.route_id) - (a.route_id < b.route_id)

    ordered = sorted(feasible, key=cmp_to_key(compare))
    for rank, r in enumerate(ordered, start=1):
        routes_out[r.route_id]["rank"] = rank
    recommended = ordered[0]
    runner_up = ordered[1] if len(ordered) > 1 else None

    # Dominance flags (weight-independent).
    for r in feasible:
        others = [o for o in feasible if o.route_id != r.route_id]
        routes_out[r.route_id]["non_dominated_all_available"] = not any(
            _dominates(raw[o.route_id], raw[r.route_id], available) for o in others)
        routes_out[r.route_id]["non_dominated_selection"] = not any(
            _dominates(raw[o.route_id], raw[r.route_id], active) for o in others)

    # Margin.
    margin: float | None = None
    if weights is not None and runner_up is not None:
        margin = scores[runner_up.route_id] - scores[recommended.route_id]
        if abs(margin) <= SCORE_TIE_TOL:
            margin = 0.0

    # Comparison block.
    def best_by(obj: str) -> dict[str, Any]:
        best = min(feasible, key=lambda r: (raw[r.route_id][obj], r.route_id))
        return {"route_id": best.route_id, "value": raw[best.route_id][obj]}

    comparison: dict[str, Any] = {
        "cheapest": best_by("cost"),
        "fastest": best_by("time"),
        "lowest_delay": best_by("delay"),
        "lowest_geopolitical": best_by(SCORED_RISK) if SCORED_RISK in available else None,
        "versus_runner_up": None,
    }
    if runner_up is not None:
        comparison["versus_runner_up"] = {
            obj: {
                "recommended": raw[recommended.route_id][obj],
                "runner_up": raw[runner_up.route_id][obj],
                "difference": raw[recommended.route_id][obj] - raw[runner_up.route_id][obj],
            }
            for obj in available
        }

    result.update({
        "status": "recommended",
        "recommended_route_id": recommended.route_id,
        "runner_up_route_id": runner_up.route_id if runner_up else None,
        "score_margin": margin,
        "comparison": comparison,
    })
    return result
