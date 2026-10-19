"""Evaluation over the fixed corpus: four methods, per-objective gaps, weighted
score S and balance gap B, dominance share, and the two sensitivity families.

Every mean is reported together with its count n. Undefined values are None
and are excluded from means; zero is never substituted.
"""

from __future__ import annotations

import copy
from typing import Any

from shipment_decision.constants import SCORED_RISK
from shipment_decision.corpus import build_corpus, build_invalid_fixtures, strip_meta
from shipment_decision.score import score_shipment
from shipment_decision.validate import ValidationError, validate_shipment

METHODS = ("min_cost", "min_time", "min_risk", "balanced")
WEIGHT_DELTA = 0.10
DELAY_EPS = (0.05, -0.05)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _mean(values: list[float | None]) -> dict[str, Any]:
    defined = [v for v in values if v is not None]
    return {"mean": (sum(defined) / len(defined)) if defined else None, "n": len(defined)}


def shipment_for_method(shipment: dict[str, Any], method: str) -> dict[str, Any]:
    s = strip_meta(shipment)
    s["priority"] = method
    if method != "balanced":
        s.pop("weights", None)
    return s


def _route_entry(result: dict[str, Any], route_id: str) -> dict[str, Any]:
    for r in result["routes"]:
        if r["route_id"] == route_id:
            return r
    raise KeyError(route_id)


def _clip01(x: float) -> float:
    return min(1.0, max(0.0, x))


# ---------------------------------------------------------------------------
# per-shipment evaluation
# ---------------------------------------------------------------------------

def evaluate_shipment(shipment: dict[str, Any]) -> dict[str, Any]:
    results = {m: score_shipment(validate_shipment(shipment_for_method(shipment, m))) for m in METHODS}
    balanced = results["balanced"]
    out: dict[str, Any] = {
        "shipment_id": shipment["shipment_id"],
        "purpose": shipment.get("_purpose"),
        "status": balanced["status"],
        "objectives_available": balanced["objectives_available"],
        "balanced_effective_weights": balanced["effective_weights"],
        "balanced_weight_source": balanced["weight_source"],
        "methods": {},
        "results": results,
    }
    if balanced["status"] != "recommended":
        for m in METHODS:
            out["methods"][m] = {"recommended_route_id": None}
        return out

    feasible = [r for r in balanced["routes"] if r["feasible"]]
    available = balanced["objectives_available"]
    best = {obj: min(_raw(r, obj) for r in feasible) for obj in available}

    # Balance-gap minimiser (weight independent) for the report.
    b_min = min(feasible, key=lambda r: (r["balance_gap"], r["route_id"]))
    b_tied = [r["route_id"] for r in feasible if r["balance_gap"] == b_min["balance_gap"]]
    out["balance_gap_minimizer"] = b_min["route_id"]
    out["balance_gap_minimizer_tied_with"] = [rid for rid in b_tied if rid != b_min["route_id"]]
    out["weighted_score_minimizer"] = balanced["recommended_route_id"]

    for m in METHODS:
        res = results[m]
        rid = res["recommended_route_id"]
        chosen_bal = _route_entry(balanced, rid)  # same route, scored under balanced config
        per_obj = {}
        for obj in available:
            value = _raw(chosen_bal, obj)
            abs_gap = value - best[obj]
            rel_gap = (abs_gap / best[obj]) if best[obj] > 0 else None
            per_obj[obj] = {"value": value, "abs_gap": abs_gap, "rel_gap": rel_gap, "best": best[obj]}
        out["methods"][m] = {
            "recommended_route_id": rid,
            "runner_up_route_id": res["runner_up_route_id"],
            "score_margin": res["score_margin"],
            "objectives": per_obj,
            "weighted_score_S": chosen_bal["score"],
            "balance_gap_B": chosen_bal["balance_gap"],
            "non_dominated_all_available": chosen_bal["non_dominated_all_available"],
            "non_dominated_selection": _route_entry(res, rid)["non_dominated_selection"],
        }
    return out


def _raw(route_entry: dict[str, Any], obj: str) -> float:
    return {
        "cost": route_entry["cost"],
        "time": route_entry["transit_hours"],
        "delay": route_entry["delay_probability"],
        SCORED_RISK: route_entry["geopolitical"],
    }[obj]


# ---------------------------------------------------------------------------
# sensitivity
# ---------------------------------------------------------------------------

def perturb_weights(weights: dict[str, float], active: list[str], k: str, direction: str,
                    delta: float = WEIGHT_DELTA) -> tuple[dict[str, float] | None, str | None]:
    """Return (new_weights, None) or (None, skip_reason). Preserves >=0 and sum 1."""
    w_k = weights[k]
    if direction == "up":
        add = min(delta, 1.0 - w_k)
        if add == 0:
            return None, "weight_already_one"
        new_k = w_k + add
    else:
        sub = min(delta, w_k)
        if sub == 0:
            return None, "weight_already_zero"
        if w_k == 1.0:
            return None, "no_other_positive_weight"
        new_k = w_k - sub
    factor = (1.0 - new_k) / (1.0 - w_k)
    new = {}
    for obj, w in weights.items():
        if obj == k:
            new[obj] = new_k
        else:
            new[obj] = w * factor
    # objectives outside `active` have weight 0 and stay 0 (0 * factor == 0)
    return new, None


def weight_sensitivity(corpus_eval: list[dict[str, Any]], shipments: dict[str, dict[str, Any]]) -> dict[str, Any]:
    applied = 0
    flips: list[dict[str, Any]] = []
    skips: dict[str, int] = {}
    flipped_ids: set[str] = set()
    margins: dict[str, float | None] = {}
    for ev in corpus_eval:
        if ev["status"] != "recommended":
            continue
        sid = ev["shipment_id"]
        base = ev["results"]["balanced"]
        margins[sid] = base["score_margin"]
        validated = validate_shipment(shipment_for_method(shipments[sid], "balanced"))
        weights = base["effective_weights"]
        active = base["objectives_active"]
        for k in active:
            for direction in ("up", "down"):
                new_w, skip = perturb_weights(weights, active, k, direction)
                if skip:
                    skips[skip] = skips.get(skip, 0) + 1
                    continue
                applied += 1
                res = score_shipment(validated, weights_override=new_w)
                if res["recommended_route_id"] != base["recommended_route_id"]:
                    flipped_ids.add(sid)
                    flips.append({
                        "shipment_id": sid, "objective": k, "direction": direction,
                        "weights": new_w, "from": base["recommended_route_id"],
                        "to": res["recommended_route_id"], "original_margin": base["score_margin"],
                    })
    return _summarise(applied, skips, flips, flipped_ids, margins)


def delay_sensitivity(corpus_eval: list[dict[str, Any]], shipments: dict[str, dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {"uniform": {}, "route_specific": {}}
    for method in METHODS:
        for family in ("uniform", "route_specific"):
            applied = 0
            flips: list[dict[str, Any]] = []
            flipped_ids: set[str] = set()
            margins: dict[str, float | None] = {}
            limit_crossings = 0
            for ev in corpus_eval:
                if ev["status"] != "recommended":
                    continue
                sid = ev["shipment_id"]
                base = ev["results"][method]
                margins[sid] = base["score_margin"]
                validated = validate_shipment(shipment_for_method(shipments[sid], method))
                feasible = [r for r in base["routes"] if r["feasible"]]
                limit = validated.constraints.get("max_delay_probability")
                for eps in DELAY_EPS:
                    overrides: list[dict[str, float]] = []
                    if family == "uniform":
                        overrides.append({r["route_id"]: _clip01(r["delay_probability"] + eps) for r in feasible})
                    else:
                        for r in feasible:
                            overrides.append({r["route_id"]: _clip01(r["delay_probability"] + eps)})
                    for ov in overrides:
                        applied += 1
                        if limit is not None:
                            limit_crossings += sum(1 for p in ov.values() if p > limit)
                        res = score_shipment(validated, delay_override=ov)
                        if res["recommended_route_id"] != base["recommended_route_id"]:
                            flipped_ids.add(sid)
                            flips.append({
                                "shipment_id": sid, "eps": eps, "override": ov,
                                "from": base["recommended_route_id"], "to": res["recommended_route_id"],
                                "original_margin": base["score_margin"],
                            })
            summary = _summarise(applied, {}, flips, flipped_ids, margins)
            summary["limit_crossings_counted_not_applied"] = limit_crossings
            out[family][method] = summary
    return out


def _summarise(applied: int, skips: dict[str, int], flips: list[dict[str, Any]],
               flipped_ids: set[str], margins: dict[str, float | None]) -> dict[str, Any]:
    flipped_margins = [margins[s] for s in sorted(flipped_ids)]
    unflipped_margins = [m for s, m in margins.items() if s not in flipped_ids]
    return {
        "perturbations_applied": applied,
        "perturbations_skipped": sum(skips.values()),
        "skips_by_reason": skips,
        "perturbations_flipped": len(flips),
        "flip_rate": (len(flips) / applied) if applied else None,
        "shipments_evaluated": len(margins),
        "shipments_flipped": sorted(flipped_ids),
        "mean_original_margin_flipped": _mean(flipped_margins),
        "mean_original_margin_unflipped": _mean(unflipped_margins),
        "flips": flips,
    }


# ---------------------------------------------------------------------------
# aggregate
# ---------------------------------------------------------------------------

def aggregate(corpus_eval: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [ev for ev in corpus_eval if ev["status"] == "recommended"]
    agg: dict[str, Any] = {
        "shipments_total": len(corpus_eval),
        "shipments_scored": len(scored),
        "no_feasible_rate": (len(corpus_eval) - len(scored)) / len(corpus_eval) if corpus_eval else None,
        "methods": {},
    }
    objectives = ("cost", "time", "delay", SCORED_RISK)
    for m in METHODS:
        row: dict[str, Any] = {"objectives": {}}
        for obj in objectives:
            vals, abs_gaps, rel_gaps = [], [], []
            for ev in scored:
                po = ev["methods"][m]["objectives"].get(obj)
                if po is None:
                    continue  # objective unavailable on this shipment
                vals.append(po["value"]); abs_gaps.append(po["abs_gap"]); rel_gaps.append(po["rel_gap"])
            row["objectives"][obj] = {
                "mean_value": _mean(vals), "mean_abs_gap": _mean(abs_gaps), "mean_rel_gap": _mean(rel_gaps),
            }
        row["mean_weighted_score_S"] = _mean([ev["methods"][m]["weighted_score_S"] for ev in scored])
        row["mean_balance_gap_B"] = _mean([ev["methods"][m]["balance_gap_B"] for ev in scored])
        nd = [ev["methods"][m]["non_dominated_all_available"] for ev in scored]
        row["non_dominated_all_available_share"] = (sum(1 for x in nd if x) / len(nd)) if nd else None
        margins = [ev["methods"][m]["score_margin"] for ev in scored]
        defined = [x for x in margins if x is not None]
        row["tie_rate"] = {"rate": (sum(1 for x in defined if x == 0) / len(defined)) if defined else None,
                           "n": len(defined)}
        agg["methods"][m] = row
    return agg


# ---------------------------------------------------------------------------
# entry
# ---------------------------------------------------------------------------

def run_evaluation() -> dict[str, Any]:
    corpus = build_corpus()
    shipments = {s["shipment_id"]: s for s in corpus}
    corpus_eval = [evaluate_shipment(s) for s in corpus]

    invalid: list[dict[str, Any]] = []
    for fx in build_invalid_fixtures():
        try:
            validate_shipment(strip_meta(fx))
            invalid.append({"shipment_id": fx["shipment_id"], "expected_code": fx["_expected_code"],
                            "codes": [], "rejected": False})
        except ValidationError as exc:
            invalid.append({"shipment_id": fx["shipment_id"], "expected_code": fx["_expected_code"],
                            "codes": sorted({e["code"] for e in exc.errors}), "rejected": True})

    report = {
        "corpus_size": len(corpus),
        "per_shipment": [{k: v for k, v in ev.items() if k != "results"} for ev in corpus_eval],
        "aggregate": aggregate(corpus_eval),
        "validation_failures": invalid,
        "weight_sensitivity": weight_sensitivity(corpus_eval, shipments),
        "delay_sensitivity": delay_sensitivity(corpus_eval, shipments),
    }
    return report


# ---------------------------------------------------------------------------
# markdown rendering (presentation only; rounding happens here)
# ---------------------------------------------------------------------------

def _f(x: float | None, nd: int = 4) -> str:
    return "null" if x is None else f"{x:.{nd}f}"


def _mean_cell(m: dict[str, Any], nd: int = 4) -> str:
    return f"{_f(m['mean'], nd)} (n={m['n']})"


def render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    agg = report["aggregate"]
    lines.append("# Evaluation results (measured)\n")
    lines.append(f"Corpus: {report['corpus_size']} shipments; {agg['shipments_scored']} with a feasible route; "
                 f"no-feasible rate {_f(agg['no_feasible_rate'], 3)}.\n")

    lines.append("## Winners per shipment\n")
    lines.append("| Shipment | Purpose | min_cost | min_time | min_risk | balanced | balanced S margin | S-min | B-min |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for ev in report["per_shipment"]:
        m = ev["methods"]
        if ev["status"] != "recommended":
            lines.append(f"| {ev['shipment_id']} | {ev['purpose']} | none | none | none | none | null | none | none |")
            continue
        b_min = ev["balance_gap_minimizer"]
        if ev["balance_gap_minimizer_tied_with"]:
            b_min += " (tie with " + ", ".join(ev["balance_gap_minimizer_tied_with"]) + ")"
        lines.append(f"| {ev['shipment_id']} | {ev['purpose']} | {m['min_cost']['recommended_route_id']} | "
                     f"{m['min_time']['recommended_route_id']} | {m['min_risk']['recommended_route_id']} | "
                     f"{m['balanced']['recommended_route_id']} | {_f(m['balanced']['score_margin'])} | "
                     f"{ev['weighted_score_minimizer']} | {b_min} |")
    lines.append("")

    lines.append("## Aggregate by method (means over shipments where defined; n shown)\n")
    lines.append("| Method | cost abs gap | time abs gap (h) | delay abs gap | geo abs gap | cost rel gap | "
                 "time rel gap | delay rel gap | geo rel gap | mean S | mean B | non-dominated share | tie rate |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for m in METHODS:
        row = agg["methods"][m]
        o = row["objectives"]
        lines.append(
            f"| {m} | {_mean_cell(o['cost']['mean_abs_gap'], 1)} | {_mean_cell(o['time']['mean_abs_gap'], 1)} | "
            f"{_mean_cell(o['delay']['mean_abs_gap'])} | {_mean_cell(o['geopolitical']['mean_abs_gap'])} | "
            f"{_mean_cell(o['cost']['mean_rel_gap'])} | {_mean_cell(o['time']['mean_rel_gap'])} | "
            f"{_mean_cell(o['delay']['mean_rel_gap'])} | {_mean_cell(o['geopolitical']['mean_rel_gap'])} | "
            f"{_mean_cell(row['mean_weighted_score_S'])} | {_mean_cell(row['mean_balance_gap_B'])} | "
            f"{_f(row['non_dominated_all_available_share'], 3)} | "
            f"{_f(row['tie_rate']['rate'], 3)} (n={row['tie_rate']['n']}) |")
    lines.append("")

    lines.append("## Validation fixtures\n")
    lines.append("| Fixture | Expected code | Rejected | Codes raised |")
    lines.append("|---|---|---|---|")
    for fx in report["validation_failures"]:
        lines.append(f"| {fx['shipment_id']} | {fx['expected_code']} | {fx['rejected']} | {', '.join(fx['codes'])} |")
    lines.append("")

    ws = report["weight_sensitivity"]
    lines.append("## Weight sensitivity (balanced only, delta = 0.10, proportional renormalisation)\n")
    lines.append(f"- Perturbations applied: {ws['perturbations_applied']}; skipped: {ws['perturbations_skipped']} "
                 f"({ws['skips_by_reason']})")
    lines.append(f"- Flips: {ws['perturbations_flipped']} (flip rate {_f(ws['flip_rate'], 4)})")
    lines.append(f"- Shipments flipped: {', '.join(ws['shipments_flipped']) or 'none'}")
    lines.append(f"- Mean original margin, flipped shipments: {_mean_cell(ws['mean_original_margin_flipped'])}")
    lines.append(f"- Mean original margin, unflipped shipments: {_mean_cell(ws['mean_original_margin_unflipped'])}")
    for fl in ws["flips"]:
        lines.append(f"  - {fl['shipment_id']}: {fl['objective']} {fl['direction']} -> {fl['from']} becomes {fl['to']} "
                     f"(original margin {_f(fl['original_margin'])})")
    lines.append("")

    ds = report["delay_sensitivity"]
    lines.append("## Delay-probability sensitivity (eps = +/-0.05, clipped to [0,1], feasibility fixed)\n")
    lines.append("| Family | Method | Applied | Flips | Flip rate | Shipments flipped | "
                 "Mean margin flipped | Mean margin unflipped | Limit crossings counted |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for family in ("uniform", "route_specific"):
        for m in METHODS:
            s = ds[family][m]
            lines.append(f"| {family} | {m} | {s['perturbations_applied']} | {s['perturbations_flipped']} | "
                         f"{_f(s['flip_rate'], 4)} | {', '.join(s['shipments_flipped']) or 'none'} | "
                         f"{_mean_cell(s['mean_original_margin_flipped'])} | "
                         f"{_mean_cell(s['mean_original_margin_unflipped'])} | "
                         f"{s['limit_crossings_counted_not_applied']} |")
    lines.append("")
    lines.append("Margins are defined only for balanced and min_risk (weighted-score modes); "
                 "lexicographic modes report null. Flip rates are deterministic sensitivity measurements "
                 "on assigned scenario values, not calibrated uncertainty.")
    return "\n".join(lines) + "\n"
