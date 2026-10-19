"""Numeric tolerances and fixed vocabularies. All values are documented in README."""

# Two weighted scores whose absolute difference is <= SCORE_TIE_TOL are a tie
# and fall through to the deterministic tie-break keys.
SCORE_TIE_TOL = 1e-9

# Explicit balanced weights must sum to 1 within this tolerance. They are
# never renormalised.
WEIGHT_SUM_TOL = 1e-6

# Leg costs / hours must sum to the route totals within this tolerance.
LEG_SUM_TOL = 0.01

SCHEMA_VERSION = 1

PRIORITIES = ("min_cost", "min_time", "min_risk", "balanced")

# Objectives that are always available once a shipment validates.
CORE_OBJECTIVES = ("cost", "time", "delay")
# The only risk indicator that can be scored (under the common-support rule).
SCORED_RISK = "geopolitical"
# Risk indicators accepted in input. Congestion is stored, never scored.
ALLOWED_RISKS = ("geopolitical", "congestion")

# Order in which failed constraints are listed on a route.
CONSTRAINT_ORDER = ("max_cost", "max_transit_hours", "max_delay_probability")

# Lexicographic key orders (objective names; route_id is always the final key).
SELECTION_KEYS = {
    "min_cost": ("cost", "delay", "time"),
    "min_time": ("time", "delay", "cost"),
}
