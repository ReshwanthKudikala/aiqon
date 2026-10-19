"""validate -> score -> explain, returning one result object."""

from __future__ import annotations

from typing import Any

from shipment_decision.explain import explain
from shipment_decision.schema import invalid_result
from shipment_decision.score import score_shipment
from shipment_decision.validate import ValidationError, validate_shipment


def decide(data: Any) -> dict[str, Any]:
    """Full pipeline for one parsed-JSON shipment. Never raises on bad input."""
    try:
        shipment = validate_shipment(data)
    except ValidationError as exc:
        result = invalid_result(exc.errors, exc.shipment_id, exc.priority)
    else:
        result = score_shipment(shipment)
    result["explanation"] = explain(result)
    return result
