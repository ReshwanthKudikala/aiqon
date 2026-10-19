"""Explainable shipment route selection among supplied route options.

Pipeline: validate -> score -> explain. The evaluator and the CLI both call
the same scoring function; the explainer reads only the result object.
"""

from shipment_decision.validate import validate_shipment
from shipment_decision.score import score_shipment
from shipment_decision.explain import explain
from shipment_decision.pipeline import decide

__all__ = ["validate_shipment", "score_shipment", "explain", "decide"]
