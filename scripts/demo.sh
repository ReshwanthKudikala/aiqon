#!/usr/bin/env bash
# Command-line demo (< 5 minutes). Run from the repository root after `pip install -e ".[test]"`.
set -u
if command -v shipment-decision >/dev/null 2>&1; then CMD="shipment-decision"; else export PYTHONPATH=src; CMD="python -m shipment_decision"; fi

echo; echo "# 1. The brief's example: a slightly dearer route with much lower delay (S03, balanced)"
$CMD score examples/S03_balanced.json --text
echo; echo "# 2. Same shipment, priority min_cost: the cheap route wins and the explanation says what it gives up"
$CMD score examples/S03_balanced.json --priority min_cost --text
echo; echo "# 3. Geopolitical data absent on every route: objective disabled, weights 1/3 each, nothing filled with zero"
$CMD score examples/S12_no_geopolitical.json --text
echo; echo "# 4. Hard limits exclude everything: an explicit no-recommendation, nothing relaxed"
$CMD score examples/S10_no_feasible.json --text
echo; echo "# 5. Partial risk data is rejected rather than guessed"
$CMD score examples/X01_invalid.json --text || true
echo; echo "# 6. Full evaluation: four methods, gaps, dominance, sensitivity (measured, including the trade-offs balanced loses)"
$CMD evaluate
