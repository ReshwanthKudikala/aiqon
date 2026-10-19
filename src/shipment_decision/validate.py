"""Input validation. Produces a ValidatedShipment or raises ValidationError.

Nothing here scores or imputes. The common-support rule for geopolitical risk,
the weight defaults, and the effective-weight derivation live here because they
are properties of the *input*, fixed before any scoring happens.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from shipment_decision.constants import (
    ALLOWED_RISKS,
    CONSTRAINT_ORDER,
    CORE_OBJECTIVES,
    LEG_SUM_TOL,
    PRIORITIES,
    SCORED_RISK,
    SELECTION_KEYS,
    WEIGHT_SUM_TOL,
)


class ValidationError(Exception):
    """Raised with the full list of field errors."""

    def __init__(self, errors: list[dict[str, str]], shipment_id: str | None, priority: str | None):
        super().__init__(f"{len(errors)} validation error(s)")
        self.errors = errors
        self.shipment_id = shipment_id
        self.priority = priority


@dataclass(frozen=True)
class Route:
    route_id: str
    cost: float
    transit_hours: float
    delay_probability: float
    geopolitical: float | None
    congestion: float | None
    legs: list[dict[str, Any]] | None

    def raw(self, objective: str) -> float | None:
        if objective == "cost":
            return self.cost
        if objective == "time":
            return self.transit_hours
        if objective == "delay":
            return self.delay_probability
        if objective == "geopolitical":
            return self.geopolitical
        raise KeyError(objective)


@dataclass(frozen=True)
class ValidatedShipment:
    shipment_id: str
    origin: str
    destination: str
    priority: str
    routes: tuple[Route, ...]  # sorted by route_id
    constraints: dict[str, float]  # only supplied limits
    objectives_available: tuple[str, ...]
    objectives_active: tuple[str, ...]
    objectives_inactive: tuple[dict[str, str], ...]
    objectives_unavailable: tuple[dict[str, str], ...]
    effective_weights: dict[str, float] | None
    weight_source: str
    selection_keys: tuple[str, ...] | None
    geopolitical_available: bool = field(default=False)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _err(errors: list[dict[str, str]], code: str, path: str, message: str) -> None:
    errors.append({"code": code, "path": path, "message": message})


def _check_number(errors, value, path, *, minimum=None, maximum=None, strict_min=False,
                  negative_code="out_of_range") -> bool:
    if not _is_number(value):
        _err(errors, "invalid_type", path, "must be a number")
        return False
    if not math.isfinite(value):
        _err(errors, "not_finite", path, "must be finite")
        return False
    if minimum is not None:
        if strict_min and value <= minimum:
            _err(errors, negative_code, path, f"must be > {minimum}")
            return False
        if not strict_min and value < minimum:
            _err(errors, negative_code, path, f"must be >= {minimum}")
            return False
    if maximum is not None and value > maximum:
        _err(errors, "out_of_range", path, f"must be <= {maximum}")
        return False
    return True


def _check_string(errors, data, key, path) -> str | None:
    value = data.get(key)
    if value is None:
        _err(errors, "missing_field", path, "required")
        return None
    if not isinstance(value, str):
        _err(errors, "invalid_type", path, "must be a string")
        return None
    if not value.strip():
        _err(errors, "empty_string", path, "must be non-empty")
        return None
    return value


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------

def _validate_route(errors, raw: Any, index: int, origin: str | None, destination: str | None) -> Route | None:
    path = f"routes[{index}]"
    if not isinstance(raw, dict):
        _err(errors, "invalid_type", path, "must be an object")
        return None
    ok = True
    route_id = _check_string(errors, raw, "route_id", f"{path}.route_id")
    ok &= route_id is not None

    cost = raw.get("cost")
    if cost is None:
        _err(errors, "missing_field", f"{path}.cost", "required"); ok = False
    else:
        ok &= _check_number(errors, cost, f"{path}.cost", minimum=0, negative_code="cost_negative")

    hours = raw.get("transit_hours")
    if hours is None:
        _err(errors, "missing_field", f"{path}.transit_hours", "required"); ok = False
    else:
        ok &= _check_number(errors, hours, f"{path}.transit_hours", minimum=0, strict_min=True,
                            negative_code="transit_hours_not_positive")

    delay = raw.get("delay_probability")
    if delay is None:
        _err(errors, "missing_field", f"{path}.delay_probability", "required"); ok = False
    else:
        ok &= _check_number(errors, delay, f"{path}.delay_probability", minimum=0, maximum=1)

    geopolitical = None
    congestion = None
    risks = raw.get("risks")
    if risks is not None:
        if not isinstance(risks, dict):
            _err(errors, "invalid_type", f"{path}.risks", "must be an object"); ok = False
        else:
            for name, value in risks.items():
                rpath = f"{path}.risks.{name}"
                if name not in ALLOWED_RISKS:
                    _err(errors, "unknown_risk", rpath, f"allowed risk names: {', '.join(ALLOWED_RISKS)}")
                    ok = False
                    continue
                if value is None:
                    continue  # null == absent, never 0
                if not _check_number(errors, value, rpath, minimum=0, maximum=1):
                    ok = False
                    continue
                if name == "geopolitical":
                    geopolitical = float(value)
                else:
                    congestion = float(value)

    legs = raw.get("legs")
    legs_out = None
    if legs is not None:
        if not isinstance(legs, list) or not legs:
            _err(errors, "invalid_type", f"{path}.legs", "must be a non-empty list when present"); ok = False
        else:
            legs_out = []
            leg_cost_sum = 0.0
            leg_hours_sum = 0.0
            legs_ok = True
            for j, leg in enumerate(legs):
                lpath = f"{path}.legs[{j}]"
                if not isinstance(leg, dict):
                    _err(errors, "invalid_type", lpath, "must be an object"); legs_ok = False; continue
                lfrom = _check_string(errors, leg, "from", f"{lpath}.from")
                lto = _check_string(errors, leg, "to", f"{lpath}.to")
                lcost = leg.get("cost")
                lhours = leg.get("transit_hours")
                if lcost is None:
                    _err(errors, "missing_field", f"{lpath}.cost", "required"); legs_ok = False
                elif not _check_number(errors, lcost, f"{lpath}.cost", minimum=0, negative_code="leg_cost_negative"):
                    legs_ok = False
                if lhours is None:
                    _err(errors, "missing_field", f"{lpath}.transit_hours", "required"); legs_ok = False
                elif not _check_number(errors, lhours, f"{lpath}.transit_hours", minimum=0, strict_min=True,
                                       negative_code="leg_hours_not_positive"):
                    legs_ok = False
                if lfrom is None or lto is None:
                    legs_ok = False
                if legs_ok:
                    leg_cost_sum += float(lcost)
                    leg_hours_sum += float(lhours)
                    legs_out.append({"from": lfrom, "to": lto, "mode": leg.get("mode"),
                                     "cost": float(lcost), "transit_hours": float(lhours)})
            if legs_ok:
                if origin is not None and legs_out[0]["from"] != origin:
                    _err(errors, "legs_disconnected", f"{path}.legs[0].from", "first leg must start at the shipment origin")
                    ok = False
                if destination is not None and legs_out[-1]["to"] != destination:
                    _err(errors, "legs_disconnected", f"{path}.legs[{len(legs_out) - 1}].to",
                         "last leg must end at the shipment destination")
                    ok = False
                for j in range(1, len(legs_out)):
                    if legs_out[j]["from"] != legs_out[j - 1]["to"]:
                        _err(errors, "legs_disconnected", f"{path}.legs[{j}].from",
                             "leg must start where the previous leg ended")
                        ok = False
                if _is_number(cost) and abs(leg_cost_sum - cost) > LEG_SUM_TOL:
                    _err(errors, "legs_sum_mismatch", f"{path}.legs",
                         f"leg costs sum to {leg_cost_sum}, route cost is {cost}")
                    ok = False
                if _is_number(hours) and abs(leg_hours_sum - hours) > LEG_SUM_TOL:
                    _err(errors, "legs_sum_mismatch", f"{path}.legs",
                         f"leg hours sum to {leg_hours_sum}, route transit_hours is {hours}")
                    ok = False
            else:
                ok = False

    if not ok:
        return None
    return Route(
        route_id=route_id,
        cost=float(cost),
        transit_hours=float(hours),
        delay_probability=float(delay),
        geopolitical=geopolitical,
        congestion=congestion,
        legs=legs_out,
    )


# ---------------------------------------------------------------------------
# weights
# ---------------------------------------------------------------------------

def _default_weights(geo_available: bool) -> tuple[dict[str, float], str]:
    if geo_available:
        return {"cost": 0.25, "time": 0.25, "delay": 0.25, "geopolitical": 0.25}, "default"
    third = 1.0 / 3.0
    # delay takes the remainder so the three weights sum to exactly 1.0 in floats
    return {"cost": third, "time": third, "delay": 1.0 - 2.0 * third, "geopolitical": 0.0}, \
        "default_geopolitical_unavailable"


def _validate_explicit_weights(errors, weights: Any, geo_available: bool) -> dict[str, float] | None:
    path = "weights"
    if not isinstance(weights, dict):
        _err(errors, "invalid_type", path, "must be an object")
        return None
    ok = True
    allowed = set(CORE_OBJECTIVES) | {SCORED_RISK}
    for key in weights:
        if key not in allowed:
            _err(errors, "weights_unknown_key", f"{path}.{key}", f"allowed keys: {', '.join(sorted(allowed))}")
            ok = False
    for key in CORE_OBJECTIVES:
        if key not in weights:
            _err(errors, "weights_missing_key", f"{path}.{key}", "required in balanced mode")
            ok = False
    if geo_available and SCORED_RISK not in weights:
        _err(errors, "weights_missing_key", f"{path}.{SCORED_RISK}",
             "required because geopolitical data is present on every route")
        ok = False
    out: dict[str, float] = {}
    for key, value in weights.items():
        if key not in allowed:
            continue
        if not _check_number(errors, value, f"{path}.{key}", minimum=0, negative_code="weight_negative"):
            ok = False
            continue
        out[key] = float(value)
    if not ok:
        return None
    geo_weight = out.get(SCORED_RISK, 0.0)
    if not geo_available and geo_weight > 0:
        _err(errors, "objective_requested_without_data", f"{path}.{SCORED_RISK}",
             "positive weight on geopolitical risk but no route carries a geopolitical value")
        return None
    total = sum(out.values())
    if abs(total - 1.0) > WEIGHT_SUM_TOL:
        _err(errors, "weights_sum", path, f"weights sum to {total!r}; must sum to 1 within {WEIGHT_SUM_TOL}")
        return None
    out.setdefault(SCORED_RISK, 0.0)
    return out


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

def validate_shipment(data: Any) -> ValidatedShipment:
    """Validate a parsed JSON shipment. Raises ValidationError on any problem."""
    errors: list[dict[str, str]] = []
    if not isinstance(data, dict):
        raise ValidationError([{"code": "not_an_object", "path": "", "message": "shipment must be a JSON object"}],
                              None, None)

    shipment_id = _check_string(errors, data, "shipment_id", "shipment_id")
    origin = _check_string(errors, data, "origin", "origin")
    destination = _check_string(errors, data, "destination", "destination")
    if origin is not None and destination is not None and origin == destination:
        _err(errors, "origin_equals_destination", "destination", "origin and destination must differ")

    priority = data.get("priority")
    if priority is None:
        _err(errors, "missing_field", "priority", "required")
        priority = None
    elif priority not in PRIORITIES:
        _err(errors, "invalid_priority", "priority", f"must be one of {', '.join(PRIORITIES)}")
        priority = None

    # constraints
    constraints: dict[str, float] = {}
    raw_constraints = data.get("constraints")
    if raw_constraints is not None:
        if not isinstance(raw_constraints, dict):
            _err(errors, "invalid_type", "constraints", "must be an object")
        else:
            for key, value in raw_constraints.items():
                cpath = f"constraints.{key}"
                if key not in CONSTRAINT_ORDER:
                    _err(errors, "unknown_constraint", cpath, f"allowed: {', '.join(CONSTRAINT_ORDER)}")
                    continue
                if value is None:
                    continue
                maximum = 1 if key == "max_delay_probability" else None
                if _check_number(errors, value, cpath, minimum=0, maximum=maximum,
                                 negative_code="constraint_out_of_range"):
                    constraints[key] = float(value)

    # routes
    raw_routes = data.get("routes")
    routes: list[Route] = []
    routes_ok = True
    if raw_routes is None:
        _err(errors, "missing_field", "routes", "required"); routes_ok = False
    elif not isinstance(raw_routes, list) or not raw_routes:
        _err(errors, "no_routes", "routes", "must be a non-empty list"); routes_ok = False
    else:
        for i, raw in enumerate(raw_routes):
            route = _validate_route(errors, raw, i, origin, destination)
            if route is None:
                routes_ok = False
            else:
                routes.append(route)
        seen: set[str] = set()
        for i, route in enumerate(routes):
            if route.route_id in seen:
                _err(errors, "duplicate_route_id", f"routes[{i}].route_id", f"duplicate route_id {route.route_id!r}")
                routes_ok = False
            seen.add(route.route_id)

    # common-support rule for geopolitical risk
    geo_available = False
    if routes_ok and routes:
        with_geo = [r for r in routes if r.geopolitical is not None]
        if len(with_geo) == len(routes):
            geo_available = True
        elif with_geo:
            missing = sorted(r.route_id for r in routes if r.geopolitical is None)
            _err(errors, "incomplete_risk", "routes",
                 f"geopolitical risk present on some routes but missing on: {', '.join(missing)}")
            routes_ok = False

    # weights and effective configuration
    raw_weights = data.get("weights")
    effective_weights: dict[str, float] | None = None
    weight_source = "not_applicable"
    selection_keys: tuple[str, ...] | None = None
    objectives_inactive: list[dict[str, str]] = []
    objectives_unavailable: list[dict[str, str]] = []
    objectives_active: tuple[str, ...] = ()

    if priority is not None and priority != "balanced" and raw_weights is not None:
        _err(errors, "weights_not_allowed", "weights", "weights are only permitted with priority 'balanced'")

    if routes_ok and priority is not None:
        if not geo_available:
            objectives_unavailable.append({"name": SCORED_RISK, "reason": "absent_on_all_routes"})
        if priority == "balanced":
            if raw_weights is None:
                effective_weights, weight_source = _default_weights(geo_available)
            else:
                explicit = _validate_explicit_weights(errors, raw_weights, geo_available)
                if explicit is not None:
                    effective_weights, weight_source = explicit, "explicit"
            if effective_weights is not None:
                active = [k for k in (*CORE_OBJECTIVES, SCORED_RISK) if effective_weights[k] > 0]
                objectives_active = tuple(active)
                for k in (*CORE_OBJECTIVES, SCORED_RISK):
                    if effective_weights[k] == 0 and (k != SCORED_RISK or geo_available):
                        objectives_inactive.append({"name": k, "reason": "explicit_weight_zero"})
        elif priority == "min_risk":
            if geo_available:
                effective_weights = {"delay": 0.5, "geopolitical": 0.5}
                objectives_active = ("delay", "geopolitical")
            else:
                effective_weights = {"delay": 1.0}
                objectives_active = ("delay",)
            weight_source = "fixed_min_risk"
        else:
            selection_keys = SELECTION_KEYS[priority]
            objectives_active = tuple(sorted(CORE_OBJECTIVES, key=CORE_OBJECTIVES.index))

    if errors:
        raise ValidationError(errors, shipment_id, priority)

    objectives_available = tuple(CORE_OBJECTIVES) + ((SCORED_RISK,) if geo_available else ())
    return ValidatedShipment(
        shipment_id=shipment_id,
        origin=origin,
        destination=destination,
        priority=priority,
        routes=tuple(sorted(routes, key=lambda r: r.route_id)),
        constraints=constraints,
        objectives_available=objectives_available,
        objectives_active=objectives_active,
        objectives_inactive=tuple(objectives_inactive),
        objectives_unavailable=tuple(objectives_unavailable),
        effective_weights=effective_weights,
        weight_source=weight_source,
        selection_keys=selection_keys,
        geopolitical_available=geo_available,
    )
