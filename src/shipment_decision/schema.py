"""Result-object construction. One contract for CLI, evaluator, and explainer.

Statuses: "recommended", "no_feasible_route", "invalid_input".
Fields that are not meaningful for a status/mode are set to None, never 0.
"""

from __future__ import annotations

from typing import Any

from shipment_decision.constants import SCHEMA_VERSION

RESULT_FIELDS_ALL = (
    "schema_version", "shipment_id", "status", "priority", "errors", "explanation",
)
RESULT_FIELDS_SCORED = (
    "objectives_available", "objectives_active", "objectives_inactive", "objectives_unavailable",
    "effective_weights", "weight_source", "selection_keys", "constraints_applied",
    "normalization_notes", "recommended_route_id", "runner_up_route_id", "score_margin",
    "comparison", "routes",
)
ROUTE_FIELDS = (
    "route_id", "cost", "transit_hours", "delay_probability", "geopolitical", "congestion", "legs",
    "feasible", "failed_constraints", "normalized", "contributions", "score", "rank",
    "non_dominated_all_available", "non_dominated_selection", "balance_gap",
)


def invalid_result(errors: list[dict[str, str]], shipment_id: str | None, priority: str | None) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "shipment_id": shipment_id,
        "status": "invalid_input",
        "priority": priority,
        "errors": list(errors),
        "explanation": "",  # filled by explain()
    }


def base_result(shipment_id: str, priority: str) -> dict[str, Any]:
    out: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "shipment_id": shipment_id,
        "status": None,
        "priority": priority,
        "errors": [],
        "explanation": "",
    }
    for key in RESULT_FIELDS_SCORED:
        out[key] = None
    return out
