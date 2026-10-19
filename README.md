# Shipment route decision support

Recommends one shipment route from a supplied set of options, under cost, transit-time, delay-probability and geopolitical-risk trade-offs, and explains the choice in operator terms using only the numbers that produced it.

Built for the Aiqon AI Internship take-home *Optimizing Shipment Routes Under Cost, Time, and Risk Constraints*. The technical report is in [`docs/technical_report.md`](docs/technical_report.md); measured evaluation output is in [`results/evaluation.md`](results/evaluation.md) and [`results/evaluation.json`](results/evaluation.json).

## What it does

- Input: one shipment (origin, destination, priority, optional weights, optional hard limits) and its candidate routes (cost, transit hours, delay probability, optional `geopolitical` and `congestion` risk indicators, optional legs).
- Output: a JSON result with status `recommended`, `no_feasible_route` or `invalid_input`; the recommended route, runner-up, per-route normalized values, score contributions, rank, dominance flags; and a deterministic plain-text explanation.
- Four priorities: `min_cost`, `min_time` (lexicographic), `min_risk`, `balanced` (weighted score on min-max-normalized objectives within the feasible set).
- No prediction model, no graph search, no database, no UI. The routes are given; the system chooses among them and says why.

## Install and run

Python 3.10+. The only dependency is `pytest`, for the tests.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
pip install -e ".[test]"

shipment-decision show S03 --out examples/S03_balanced.json   # dump a corpus shipment
shipment-decision score examples/S03_balanced.json            # full JSON result
shipment-decision score examples/S03_balanced.json --text     # explanation only
shipment-decision score examples/S03_balanced.json --priority min_cost --text
shipment-decision evaluate --json results/evaluation.json --markdown results/evaluation.md
pytest -q
```

Without installing: set `PYTHONPATH=src` and use `python -m shipment_decision ...`. Exit code is 0 for `recommended`/`no_feasible_route`, 2 for `invalid_input`.

## Example

`shipment-decision score examples/S03_balanced.json --text`

```
Shipment S03: recommended route R.
Priority 'balanced': lowest weighted score using default equal weights (cost 0.250, transit time 0.250, delay probability 0.250, geopolitical risk 0.250).
Route R: cost 1,200, 250 h, delay probability 0.080, geopolitical risk 0.200.
Weighted score 0.2083 versus 0.3155 for runner-up C (margin 0.1071).
Score contributions for R: cost 0.0625, transit time 0.1458, delay probability 0.0000, geopolitical risk 0.0000.
Compared with C: cost 1,200 vs 1,000 (higher); transit time 250 h vs 240 h (higher); delay probability 0.080 vs 0.400 (lower); geopolitical risk equal at 0.200.
Single-objective references among feasible routes: cheapest C (1,000), fastest F (180 h), lowest delay R (0.080), lowest geopolitical risk C (0.200).
Dominated on every available objective by another feasible route: D.
```

With `--priority min_cost` the same shipment returns C and says so in the same format.

## Input schema

```json
{
  "shipment_id": "S03", "origin": "Shanghai", "destination": "Rotterdam",
  "priority": "balanced",
  "weights": {"cost": 0.25, "time": 0.25, "delay": 0.25, "geopolitical": 0.25},
  "constraints": {"max_cost": 5000, "max_transit_hours": 360, "max_delay_probability": 0.25},
  "routes": [{
    "route_id": "R", "cost": 1200, "transit_hours": 250, "delay_probability": 0.08,
    "risks": {"geopolitical": 0.20, "congestion": 0.40},
    "legs": [{"from": "Shanghai", "to": "Colombo", "mode": "sea", "cost": 500, "transit_hours": 110},
             {"from": "Colombo", "to": "Rotterdam", "mode": "sea", "cost": 700, "transit_hours": 140}]
  }]
}
```

Validation rules (all failures are reported together, no recommendation is made):

- `cost` >= 0, `transit_hours` > 0, `delay_probability` in [0, 1], all finite, all required on every route; unique `route_id`; origin != destination.
- Risk names allowed: `geopolitical`, `congestion`. Values in [0, 1]. `null` means absent, never 0.
- **Geopolitical common-support rule**: present on every route -> scored; absent on every route -> objective disabled for the shipment (`objectives_unavailable`); present on some routes only -> `invalid_input` (`incomplete_risk`). Congestion is stored for context and never scored.
- `weights` only with `balanced`. Omitted -> equal defaults over the available objectives (0.25 each, or 1/3 each when geopolitical is unavailable). Supplied -> must include `cost`, `time`, `delay` (and `geopolitical` when its data exists), be >= 0, and sum to 1 within `1e-6`; they are **not** renormalised. A positive geopolitical weight with no geopolitical data is rejected (`objective_requested_without_data`).
- Constraints are optional; equality with a limit is feasible. Legs, when present, must chain origin -> destination and sum to the route totals within 0.01.

## Decision rule

1. **Feasible set** `F`: routes satisfying every supplied limit. Empty `F` -> `no_feasible_route`; limits are never relaxed.
2. **Normalize** each available objective on `F` by min-max: best = 0, worst = 1; zero range (or a single feasible route) -> 0 for all.
3. **Select**
   - `balanced`: minimize `S = sum(w_x * x_norm)` over objectives with positive weight. Ties (|dS| <= 1e-9): lower raw delay, lower cost, lower hours, route id.
   - `min_risk`: `S` with fixed weights delay 0.5 / geopolitical 0.5 (delay 1.0 if geopolitical unavailable). Ties: cost, hours, route id.
   - `min_cost`: cost, then delay, then hours, then route id. `min_time`: hours, then delay, then cost, then route id.
4. **Report** `score_margin` (runner-up S minus recommended S; `null` for lexicographic modes and when fewer than two routes are feasible), `balance_gap` (unweighted sum of normalized available objectives), two dominance flags (`non_dominated_all_available` on every available objective; `non_dominated_selection` on the objectives the mode consults), and the cheapest / fastest / lowest-delay / lowest-geopolitical feasible routes.

Delay probability and planned transit time are distinct inputs. Reliability (1 - p) is not scored separately. No delay duration or monetary delay cost is assumed. Geopolitical risk is treated as separate from delay probability (assumption stated in the report); congestion is excluded from scoring because it is a delay cause already represented by delay probability.

### Tolerances (documented, used consistently)

| Constant | Value | Where |
| --- | --- | --- |
| `SCORE_TIE_TOL` | `1e-9` | scores within this are a tie -> deterministic tie-break; margin reported as 0.0; also the test tolerance (`tests/conftest.py: ABS_TOL`) |
| `WEIGHT_SUM_TOL` | `1e-6` | explicit weights must sum to 1 within this |
| `LEG_SUM_TOL` | `0.01` | leg cost/hour sums vs route totals |

No rounding happens in validation, scoring or evaluation; rounding is applied only when rendering text (`explain.py`, Markdown rendering in `evaluate.py`).

## Evaluation (measured)

The corpus is 20 designed shipments (S01-S20) plus 4 invalid fixtures (X01-X04), defined as literals in `src/shipment_decision/corpus.py`; each is built to exercise a specific trade-off or edge case (purpose column in `results/evaluation.md`). There is no hidden "correct" route; each method is measured against the best feasible value on every objective. Means are over shipments where the quantity is defined, with `n` shown; undefined values are `null`, never 0.

Aggregate over the 19 shipments with a feasible route (`results/evaluation.md`):

| Method | cost abs gap | time abs gap (h) | delay abs gap | geo abs gap (n=18) | mean S | mean B | non-dominated share |
| --- | --- | --- | --- | --- | --- | --- | --- |
| min_cost | 0.0 | 28.9 | 0.1163 | 0.0944 | 0.1681 | 0.7618 | 1.000 |
| min_time | 242.1 | 0.0 | 0.0558 | 0.2833 | 0.2631 | 1.0543 | 1.000 |
| min_risk | 84.3 | 29.6 | 0.0237 | 0.0111 | 0.1658 | 0.6528 | 1.000 |
| balanced | 47.4 | 23.2 | 0.0547 | 0.0694 | 0.1300 | 0.6094 | 1.000 |

What this does and does not show: `balanced` has the lowest mean `S` by construction (it minimizes `S` on every shipment; this is a consistency check, not evidence). It accepts a worse cost gap than `min_cost`, a worse time gap than `min_time`, and worse delay and geopolitical gaps than `min_risk`. Its lower mean balance gap `B` is a measured outcome on this corpus, not a guarantee: S15 (unequal weights) and S18 (zero geopolitical weight) are cases where the `S`-minimizer and the `B`-minimizer are different routes. All four methods happened to recommend non-dominated routes on every shipment of this corpus.

Sensitivity (deterministic perturbations, not calibrated uncertainty):

- **Weights** (`balanced`, +/-0.10 per active weight, proportional renormalisation, 148 perturbations, 0 skipped): 10 flips (6.8%) on S07, S08, S14, S19. Mean original margin of flipped shipments 0.0206 vs 0.1626 for unflipped. S19 flips from an exact tie (margin 0).
- **Uniform delay shift** (+/-0.05, clipped): 1 flip in 38 for `balanced` (S14, where clipping at 1.0 breaks the min-max invariance), 0 for every other method. Shifts that do not clip leave rankings unchanged, as the normalization predicts.
- **Route-specific delay shift**: 12/106 flips for `balanced` (S07, S08, S13, S14, S17), 10/106 for `min_risk`, 4/106 for the lexicographic modes (S13, S17 only). S13 and S17 have identical routes, so any single-route perturbation breaks the id tie-break; that is a property of ties, not of the weights.

## Tests

`pytest -q` -> **131 passed** (Python 3.13.9, pytest 9.1.1). Coverage by file:

- `tests/test_validate.py`: all four invalid fixtures, common-support rule (including `null`), weight defaults/validation/tolerance, leg rules, constraints, ordering.
- `tests/test_score.py`: every corpus winner in all four modes, every balanced `S` value as an exact rational, margins, null rules, S10 empty set, S19/S20 limit-before-normalization, S07 zero range, S13 congestion invariance, dominance flags, S15/S18 S-vs-B, tie tolerance.
- `tests/test_explain.py`: every number in an explanation equals a result field; required statements per status/mode.
- `tests/test_evaluate.py`: null handling in means, geopolitical `n`, consistency check, perturbation rule (simplex, zeros, skips), the hand-calculated S14 flips, S01 uniform-shift invariance, report structure.
- `tests/test_cli.py`: JSON output, exit codes, BOM tolerance, file writing.

## Repository layout

```
README.md
pyproject.toml            # package metadata; pytest config (pythonpath = src)
requirements.txt          # pytest
docs/technical_report.md  # 2-3 page report (approach, decisions, results, limitations)
examples/                 # S03, S10, S12, X01 as standalone inputs
results/                  # measured evaluation.md / evaluation.json
scripts/demo.ps1, demo.sh # < 5 minute command-line walkthrough
src/shipment_decision/
  constants.py            # tolerances and vocabularies
  validate.py             # schema, common-support rule, weights -> ValidatedShipment
  score.py                # feasibility, normalization, selection, dominance, margin
  explain.py              # text from the result object only (rounding lives here)
  schema.py               # result-object contract
  pipeline.py             # decide(): validate -> score -> explain
  corpus.py               # S01-S20, X01-X04 as literals
  evaluate.py             # baselines, gaps, aggregation, sensitivity, Markdown
  cli.py                  # score / show / evaluate
tests/
```

## Limitations

- Min-max normalization is relative to the feasible set. With two feasible routes it records only which route is worse on each objective, not by how much (S04); adding or removing a non-winning route can change the winner among the others (S04 vs S05). Raw values are therefore always shown next to scores.
- Equal default weights are a convention, not an elicited preference. Unequal weights change the recommendation (S15) and separate the weighted score from the unweighted balance gap.
- Geopolitical risk is scored as independent of delay probability. If a real dataset already folds geopolitical disruption into its delay estimates, this double-counts it. Nothing in this assignment measures that dependence.
- Congestion differences never change a recommendation (S13). An operator who regards congestion as independent of the supplied delay probability will not see that preference represented.
- The corpus is designed, not sampled. It can expose implementation errors and illustrate trade-offs; it supports no claim about average real-world savings.
- Sensitivity flip rates are properties of this rule on these numbers. They are not confidence intervals.
- Ties between identical routes are broken by route id; any perturbation to one of them flips the result (S13, S17 in the route-specific experiment).
