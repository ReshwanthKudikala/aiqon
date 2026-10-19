"""Operator-facing explanation built ONLY from the result object.

This module never recomputes a score or a ranking. Every number it prints is
read from a field of the result. Rounding happens here and nowhere else.
"""

from __future__ import annotations

from typing import Any

_OBJ_LABEL = {
    "cost": "cost",
    "time": "transit time",
    "delay": "delay probability",
    "geopolitical": "geopolitical risk",
}
_LIMIT_LABEL = {
    "max_cost": "max_cost",
    "max_transit_hours": "max_transit_hours",
    "max_delay_probability": "max_delay_probability",
}


def fmt_money(x: float) -> str:
    return f"{x:,.2f}".rstrip("0").rstrip(".") if x != int(x) else f"{int(x):,}"


def fmt_hours(x: float) -> str:
    return f"{x:g} h"


def fmt_prob(x: float) -> str:
    return f"{x:.3f}"


def fmt_score(x: float) -> str:
    return f"{x:.4f}"


def fmt_weight(x: float) -> str:
    return f"{x:.3f}"


def _fmt_obj(obj: str, x: float) -> str:
    if obj == "cost":
        return fmt_money(x)
    if obj == "time":
        return fmt_hours(x)
    return fmt_prob(x)


def _route(result: dict[str, Any], route_id: str) -> dict[str, Any]:
    for r in result["routes"]:
        if r["route_id"] == route_id:
            return r
    raise KeyError(route_id)


def _mode_sentence(result: dict[str, Any]) -> str:
    p = result["priority"]
    if p == "balanced":
        w = result["effective_weights"]
        active = result["objectives_active"]
        parts = ", ".join(f"{_OBJ_LABEL[k]} {fmt_weight(w[k])}" for k in active)
        src = {
            "default": "default equal weights",
            "default_geopolitical_unavailable": "default equal weights over the available objectives",
            "explicit": "the supplied weights",
        }[result["weight_source"]]
        return f"Priority 'balanced': lowest weighted score using {src} ({parts})."
    if p == "min_risk":
        w = result["effective_weights"]
        parts = ", ".join(f"{_OBJ_LABEL[k]} {fmt_weight(w[k])}" for k in result["objectives_active"])
        return f"Priority 'min_risk': lowest weighted risk score ({parts}); ties broken by cost, then transit time."
    keys = result["selection_keys"]
    return (f"Priority '{p}': lowest {_OBJ_LABEL[keys[0]]}, then {_OBJ_LABEL[keys[1]]}, "
            f"then {_OBJ_LABEL[keys[2]]}, then route id.")


def explain(result: dict[str, Any]) -> str:
    status = result["status"]
    if status == "invalid_input":
        lines = [f"Shipment {result.get('shipment_id') or '(unknown)'}: input rejected, no recommendation."]
        for e in result["errors"]:
            path = e["path"] or "(root)"
            lines.append(f"- {e['code']} at {path}: {e['message']}")
        return "\n".join(lines)

    sid = result["shipment_id"]
    if status == "no_feasible_route":
        lines = [f"Shipment {sid}: no route satisfies the hard constraints "
                 f"({', '.join(f'{k}={v:g}' for k, v in result['constraints_applied'].items())}). "
                 f"No recommendation is made and no constraint was relaxed."]
        for r in result["routes"]:
            lines.append(f"- {r['route_id']} excluded by {', '.join(r['failed_constraints'])} "
                         f"(cost {fmt_money(r['cost'])}, {fmt_hours(r['transit_hours'])}, "
                         f"delay {fmt_prob(r['delay_probability'])}).")
        return "\n".join(lines)

    rec_id = result["recommended_route_id"]
    rec = _route(result, rec_id)
    lines = [f"Shipment {sid}: recommended route {rec_id}.", _mode_sentence(result)]

    # Recommended route facts.
    facts = [f"cost {fmt_money(rec['cost'])}", fmt_hours(rec["transit_hours"]),
             f"delay probability {fmt_prob(rec['delay_probability'])}"]
    if rec["geopolitical"] is not None and "geopolitical" in result["objectives_available"]:
        facts.append(f"geopolitical risk {fmt_prob(rec['geopolitical'])}")
    lines.append(f"Route {rec_id}: " + ", ".join(facts) + ".")

    feasible_ids = [r["route_id"] for r in result["routes"] if r["feasible"]]
    excluded = [r for r in result["routes"] if not r["feasible"]]

    if len(feasible_ids) == 1:
        lines.append("It is the only feasible route, so there is no alternative to compare against.")
    else:
        ru_id = result["runner_up_route_id"]
        ru = _route(result, ru_id)
        if rec["score"] is not None:
            margin = result["score_margin"]
            lines.append(f"Weighted score {fmt_score(rec['score'])} versus {fmt_score(ru['score'])} "
                         f"for runner-up {ru_id} (margin {fmt_score(margin)}).")
            contrib = rec["contributions"]
            lines.append("Score contributions for " + rec_id + ": " + ", ".join(
                f"{_OBJ_LABEL[k]} {fmt_score(v)}" for k, v in contrib.items()) + ".")
            if margin == 0:
                lines.append("The top scores tie; the tie was broken by the fixed order "
                             + ("delay probability, cost, transit time, route id."
                                if result["priority"] == "balanced" else "cost, transit time, route id."))
        else:
            lines.append(f"Runner-up by the same ordering: {ru_id}.")
        vs = result["comparison"]["versus_runner_up"]
        comp_parts = []
        for obj in result["objectives_available"]:
            a, b, d = vs[obj]["recommended"], vs[obj]["runner_up"], vs[obj]["difference"]
            if d == 0:
                comp_parts.append(f"{_OBJ_LABEL[obj]} equal at {_fmt_obj(obj, a)}")
            else:
                direction = "higher" if d > 0 else "lower"
                comp_parts.append(f"{_OBJ_LABEL[obj]} {_fmt_obj(obj, a)} vs {_fmt_obj(obj, b)} ({direction})")
        lines.append(f"Compared with {ru_id}: " + "; ".join(comp_parts) + ".")

        cmp = result["comparison"]
        base = [f"cheapest {cmp['cheapest']['route_id']} ({fmt_money(cmp['cheapest']['value'])})",
                f"fastest {cmp['fastest']['route_id']} ({fmt_hours(cmp['fastest']['value'])})",
                f"lowest delay {cmp['lowest_delay']['route_id']} ({fmt_prob(cmp['lowest_delay']['value'])})"]
        if cmp["lowest_geopolitical"] is not None:
            base.append(f"lowest geopolitical risk {cmp['lowest_geopolitical']['route_id']} "
                        f"({fmt_prob(cmp['lowest_geopolitical']['value'])})")
        lines.append("Single-objective references among feasible routes: " + ", ".join(base) + ".")

        dominated = [r["route_id"] for r in result["routes"]
                     if r["feasible"] and r["non_dominated_all_available"] is False]
        if dominated:
            lines.append("Dominated on every available objective by another feasible route: "
                         + ", ".join(dominated) + ".")
        if rec["non_dominated_all_available"] is False:
            lines.append(f"Note: {rec_id} is dominated on the full set of available objectives; "
                         f"it was selected because the priority consults only "
                         + ", ".join(_OBJ_LABEL[k] for k in result["objectives_active"]) + ".")

    if result["normalization_notes"]:
        lines.append("Identical across all feasible routes and therefore not affecting the ranking: "
                     + ", ".join(_OBJ_LABEL[k] for k in result["normalization_notes"]) + ".")
    for item in result["objectives_unavailable"]:
        lines.append(f"{_OBJ_LABEL[item['name']].capitalize()} is absent on every route and was not scored.")
    for item in result["objectives_inactive"]:
        lines.append(f"{_OBJ_LABEL[item['name']].capitalize()} has weight 0 and was not scored; "
                     f"raw values are still reported.")
    if excluded:
        lines.append("Excluded by hard constraints: " + "; ".join(
            f"{r['route_id']} ({', '.join(r['failed_constraints'])})" for r in excluded) + ".")
    return "\n".join(lines)
