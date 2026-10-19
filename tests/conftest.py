"""Shared fixtures and the documented numerical tolerance for tests.

ABS_TOL: absolute tolerance for comparing computed floats (scores, normalized
values, weights, margins) against hand-derived rational expectations. It is
set equal to the scoring tie tolerance so that a test can never pass on a
difference the scorer itself would treat as a real gap.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from shipment_decision.constants import SCORE_TIE_TOL
from shipment_decision.corpus import build_corpus, build_invalid_fixtures, get_shipment, strip_meta
from shipment_decision.score import score_shipment
from shipment_decision.validate import validate_shipment

ABS_TOL = SCORE_TIE_TOL  # 1e-9


def approx(x: float) -> Any:
    return pytest.approx(x, abs=ABS_TOL)


def corpus_shipment(sid: str, priority: str = "balanced", **overrides: Any) -> dict[str, Any]:
    s = strip_meta(get_shipment(sid))
    s["priority"] = priority
    if priority != "balanced":
        s.pop("weights", None)
    s.update(copy.deepcopy(overrides))
    return s


def run(sid: str, priority: str = "balanced", **overrides: Any) -> dict[str, Any]:
    return score_shipment(validate_shipment(corpus_shipment(sid, priority, **overrides)))


def route(result: dict[str, Any], route_id: str) -> dict[str, Any]:
    for r in result["routes"]:
        if r["route_id"] == route_id:
            return r
    raise KeyError(route_id)


@pytest.fixture(scope="session")
def corpus() -> list[dict[str, Any]]:
    return build_corpus()


@pytest.fixture(scope="session")
def invalid_fixtures() -> list[dict[str, Any]]:
    return build_invalid_fixtures()
