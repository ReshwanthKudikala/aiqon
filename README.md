# Shipment route decision support

A logistics operator is given, for one shipment, a handful of candidate routes that each carry a cost, a transit time, a delay probability and risk indicators, and has to choose one. This project is a small Python command-line tool that makes that choice. It validates the shipment, removes routes that break hard limits, scores the rest on cost, transit time, delay probability and (where the data exists) geopolitical risk according to a stated priority, and recommends one route together with a runner-up.

Every recommendation comes with an operator-readable explanation built only from the numbers that produced it: what was chosen, why, what it costs on each objective versus the runner-up, and which routes were excluded or dominated. There is no prediction model, path search, database or UI; the routes are given and the system chooses among them and says why.

Built for the Aiqon AI Internship take-home *Optimizing Shipment Routes Under Cost, Time, and Risk Constraints*.

- Technical report: [`docs/technical_report.pdf`](docs/technical_report.pdf) (3 pages) · editable source [`docs/technical_report.md`](docs/technical_report.md)
- Measured evaluation: [`results/evaluation.md`](results/evaluation.md) · [`results/evaluation.json`](results/evaluation.json)

## Quick start

Prerequisites: Python 3.10 or newer and Git. The package has no runtime dependencies; `pytest` is the only development dependency. Developed and tested on Windows with Python 3.13.9 and pytest 9.1.1.

### Windows PowerShell, fresh clone

```powershell
git clone https://github.com/ReshwanthKudikala/aiqon.git
cd aiqon
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[test]"

shipment-decision score examples\S03_balanced.json --text   # one recommendation with explanation
pytest -q                                                   # 131 passed
```

If `Activate.ps1` is blocked, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned` and retry, or skip activation and call `.\.venv\Scripts\python.exe -m pip install -e ".[test]"`, `.\.venv\Scripts\shipment-decision.exe`, and `.\.venv\Scripts\python.exe -m pytest -q`.

### Windows PowerShell, existing `.venv`

From the repository root, with `.venv` already created:

```powershell
.\.venv\Scripts\Activate.ps1
shipment-decision score examples\S03_balanced.json --text
pytest -q
```

### Linux / macOS

```bash
git clone https://github.com/ReshwanthKudikala/aiqon.git
cd aiqon
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[test]"
shipment-decision score examples/S03_balanced.json --text
pytest -q
```

These commands follow from `pyproject.toml` and the bash demo was exercised through Git Bash on Windows; they have not been run on a native Linux or macOS machine.

### Without installing

From the repository root, set `PYTHONPATH` to `src` and call the module:

```powershell
$env:PYTHONPATH = "src"
python -m shipment_decision score examples\S03_balanced.json --text
```

```bash
PYTHONPATH=src python -m shipment_decision score examples/S03_balanced.json --text
```

Both demo scripts fall back to this automatically if `shipment-decision` is not on `PATH`.

## See it in action

```powershell
.\scripts\demo.ps1          # or: powershell -ExecutionPolicy Bypass -File scripts\demo.ps1
```

```bash
bash scripts/demo.sh
```

The demo runs six commands in under five minutes: S03 under `balanced` and `min_cost`, a shipment with no geopolitical data, one where the hard limits exclude every route, an invalid input, and the full evaluation.

S03 is the shape of the brief's own example: a route that costs a little more but is far less likely to be delayed. Under `balanced`:

```
$ shipment-decision score examples\S03_balanced.json --text
Shipment S03: recommended route R.
Priority 'balanced': lowest weighted score using default equal weights (cost 0.250, transit time 0.250, delay probability 0.250, geopolitical risk 0.250).
Route R: cost 1,200, 250 h, delay probability 0.080, geopolitical risk 0.200.
Weighted score 0.2083 versus 0.3155 for runner-up C (margin 0.1071).
Score contributions for R: cost 0.0625, transit time 0.1458, delay probability 0.0000, geopolitical risk 0.0000.
Compared with C: cost 1,200 vs 1,000 (higher); transit time 250 h vs 240 h (higher); delay probability 0.080 vs 0.400 (lower); geopolitical risk equal at 0.200.
Single-objective references among feasible routes: cheapest C (1,000), fastest F (180 h), lowest delay R (0.080), lowest geopolitical risk C (0.200).
Dominated on every available objective by another feasible route: D.
```

Under `min_cost` the same input recommends C:

```
$ shipment-decision score examples\S03_balanced.json --priority min_cost --text
Shipment S03: recommended route C.
Priority 'min_cost': lowest cost, then delay probability, then transit time, then route id.
Route C: cost 1,000, 240 h, delay probability 0.400, geopolitical risk 0.200.
Runner-up by the same ordering: R.
Compared with R: cost 1,000 vs 1,200 (lower); transit time 240 h vs 250 h (lower); delay probability 0.400 vs 0.080 (higher); geopolitical risk equal at 0.200.
Single-objective references among feasible routes: cheapest C (1,000), fastest F (180 h), lowest delay R (0.080), lowest geopolitical risk C (0.200).
Dominated on every available objective by another feasible route: D.
```

Why they differ: `min_cost` looks at cost first and C is the cheapest feasible route, so C wins outright. `balanced` normalises each objective to 0 (best) … 1 (worst) within the feasible set and sums them with equal weights. R is 200 more expensive and 10 hours slower than C, which costs it 0.0625 + 0.1458 of score, but R has the lowest delay probability in the set (0.080 → normalised 0) while C's 0.400 sits most of the way to the worst route (normalised 0.76, contributing 0.19). The delay penalty outweighs the cost and time advantage, so R scores 0.2083 against C's 0.3155. The explanation shows exactly that trade-off in raw numbers.

## What the system does

### Four priorities

| `priority` | Rule |
| --- | --- |
| `min_cost` | lowest cost; ties by lower delay probability, then transit time, then route id |
| `min_time` | lowest transit time; ties by delay probability, then cost, then route id |
| `min_risk` | lowest weighted risk score with fixed weights delay 0.5 / geopolitical 0.5 (delay alone if geopolitical is unavailable); ties by cost, then time, then route id |
| `balanced` | lowest weighted score over cost, time, delay and geopolitical risk, with explicit `weights` or equal defaults; ties by lower delay, then cost, then time, then route id |

`min_cost` and `min_time` are lexicographic orderings and have no scalar score. `min_risk` and `balanced` compute a score `S`: each available objective is min-max normalised within the feasible set (best = 0, worst = 1; 0 for every route when the range is zero or only one route is feasible) and `S` is the weighted sum. Two scores within `1e-9` count as a tie and fall through to the fixed tie-break, so the result is a deterministic total order that does not depend on the order routes appear in the input.

### Hard constraints

`constraints` may set any of `max_cost`, `max_transit_hours`, `max_delay_probability`. A route that exceeds a limit is infeasible and is dropped before normalisation and scoring, so it cannot win by being excellent elsewhere; equality with a limit is feasible. Limits are never relaxed. If no route is feasible the status is `no_feasible_route`, the explanation lists each route with the limit it failed, and no recommendation is made.

### Geopolitical risk data

Geopolitical risk is the one risk indicator that is scored, because it plausibly measures something other than lateness. It follows a common-support rule:

- present on every route → scored;
- absent on every route (missing or `null`) → the objective is disabled for that shipment, defaults become 1/3 each over cost, time and delay, and the explanation says so; nothing is filled in with 0;
- present on some routes only → `invalid_input` with code `incomplete_risk`, because routes cannot be compared on an indicator only some of them carry.

Explicit `balanced` weights must sum to 1 within `1e-6` and are never renormalised; a positive geopolitical weight with no geopolitical data is rejected (`objective_requested_without_data`). `congestion` is accepted and echoed in the output but never scored, since the delay it causes is already represented by `delay_probability`.

### What else the output reports

`score_margin` (runner-up `S` minus recommended `S`; `null` for lexicographic modes or fewer than two feasible routes), a `balance_gap` per route (unweighted sum of its normalised objectives), two dominance flags per route, the cheapest / fastest / lowest-delay / lowest-geopolitical feasible routes, and the effective weights with their source. The explanation text is generated from the result object alone and a test asserts every number in it equals a result field.

The complete specification, including the reasoning behind each design choice, is in the [technical report](docs/technical_report.md).

## Architecture and project structure

```
JSON input → validate → feasibility filter → normalise → select (priority rule) → dominance, margin → explain → JSON / text
```

`pipeline.decide()` is the whole flow: `validate_shipment()` either raises a `ValidationError` (turned into an `invalid_input` result) or returns a `ValidatedShipment`; `score_shipment()` filters, normalises, selects and annotates every route; `explain()` renders the text from the finished result. The CLI only parses arguments, reads the file and prints.

```
src/shipment_decision/
  cli.py         score / show / evaluate subcommands
  pipeline.py    decide(): validate -> score -> explain; never raises on bad input
  validate.py    schema checks, common-support rule, weights -> ValidatedShipment
  score.py       feasibility, min-max normalisation, selection, tie-breaks, dominance, margin
  explain.py     operator text from the result object only; the only place values are rounded
  schema.py      result-object contract (field list, invalid_result)
  constants.py   tolerances (1e-9 score tie, 1e-6 weight sum, 0.01 leg sum) and vocabularies
  corpus.py      S01-S20 and X01-X04 as literals, each with a stated purpose
  evaluate.py    four-method comparison, gaps, aggregation, sensitivity, Markdown rendering
examples/        S03_balanced, S10_no_feasible, S12_no_geopolitical, X01_invalid as standalone inputs
tests/           131 tests (see below)
scripts/         demo.ps1, demo.sh (walkthrough); build_report.py (Markdown -> PDF)
results/         evaluation.md and evaluation.json as produced by `shipment-decision evaluate`
docs/            technical_report.md (source) and technical_report.pdf
pyproject.toml   package metadata, console script, pytest config (pythonpath = src)
requirements.txt pytest (same extra as pip install -e ".[test]")
```

## Evaluation and testing

### Tests

`pytest -q` → **131 passed** (Python 3.13.9, pytest 9.1.1; also 131 passed on a fresh clone with a new venv).

- `tests/test_validate.py`: the four invalid fixtures, common-support rule (including `null`), weight defaults, validation and tolerance, leg rules, constraints, ordering.
- `tests/test_score.py`: every corpus winner in all four modes, every balanced `S` as an exact rational, margins, null rules, empty feasible set (S10), limit-before-normalisation (S19, S20), zero range (S07), congestion invariance (S13), dominance flags, `S`-vs-`B` cases (S15, S18), tie tolerance.
- `tests/test_explain.py`: every number in an explanation equals a result field; required sentences per status and mode.
- `tests/test_evaluate.py`: null handling in means, geopolitical `n`, consistency check, perturbation rule, the hand-calculated S14 flips, uniform-shift invariance, report structure.
- `tests/test_cli.py`: JSON output, exit codes, BOM tolerance, file writing.

### Evaluation

```powershell
shipment-decision evaluate                                   # print the Markdown summary
shipment-decision evaluate --json results\evaluation.json --markdown results\evaluation.md
```

The corpus is **synthetic and designed, not sampled**: 20 shipments (S01–S20) and 4 invalid fixtures (X01–X04) written as literals in `corpus.py`, each built to exercise one trade-off or edge case (the purpose column in [`results/evaluation.md`](results/evaluation.md)). There is no hidden "correct" route. Each of the four methods is run on every shipment and measured by the gap between its chosen route and the best feasible value on each objective. Means are taken over shipments where a quantity is defined, with `n` reported; undefined values stay `null`.

Aggregate over the 19 shipments with a feasible route:

| Method | cost gap | time gap (h) | delay gap | geo gap (n=18) | mean S | mean B | non-dominated share |
| --- | --- | --- | --- | --- | --- | --- | --- |
| min_cost | 0.0 | 28.9 | 0.1163 | 0.0944 | 0.1681 | 0.7618 | 1.000 |
| min_time | 242.1 | 0.0 | 0.0558 | 0.2833 | 0.2631 | 1.0543 | 1.000 |
| min_risk | 84.3 | 29.6 | 0.0237 | 0.0111 | 0.1658 | 0.6528 | 1.000 |
| balanced | 47.4 | 23.2 | 0.0547 | 0.0694 | 0.1300 | 0.6094 | 1.000 |

How to read it: `balanced` has the lowest mean `S` by construction, so that row is a consistency check, not evidence of quality. It accepts a worse cost gap than `min_cost`, a worse time gap than `min_time`, and worse delay and geopolitical gaps than `min_risk`. Its lower mean balance gap `B` is a measured outcome on this corpus, not a guarantee (S15 and S18 are cases where the `S`-minimiser and `B`-minimiser differ). All four methods recommended non-dominated routes on every shipment here. None of this says anything about real-world savings.

Sensitivity (deterministic perturbations, not calibrated uncertainty): perturbing each active `balanced` weight by ±0.10 (148 perturbations) flips the recommendation 10 times, all on shipments that were already close (S07, S08, S14, S19; mean original margin 0.0206 vs 0.1626 for the unflipped). A uniform ±0.05 shift in every delay probability flips 1 of 38 cases (S14, where clipping at 1.0 breaks the shift invariance). Route-specific ±0.05 shifts flip 12/106 for `balanced`, 10/106 for `min_risk` and 4/106 for each lexicographic mode. Full tables are in [`results/evaluation.md`](results/evaluation.md).

## Input and output

### Input

One shipment per JSON file. Required: `shipment_id`, `origin`, `destination`, `priority`, and `routes` with `route_id`, `cost` (≥ 0), `transit_hours` (> 0) and `delay_probability` (in [0, 1]) on every route. Optional: `constraints`, `weights` (only with `balanced`), per-route `risks` (`geopolitical`, `congestion`, each in [0, 1] or `null`) and `legs` (which must chain origin → destination and sum to the route totals within 0.01). All validation failures are reported together and no recommendation is made.

A minimal valid example with one hard limit:

```json
{
  "shipment_id": "DEMO",
  "origin": "Shanghai",
  "destination": "Rotterdam",
  "priority": "balanced",
  "constraints": {"max_transit_hours": 300},
  "routes": [
    {"route_id": "A", "cost": 1000, "transit_hours": 240, "delay_probability": 0.40, "risks": {"geopolitical": 0.2}},
    {"route_id": "B", "cost": 1200, "transit_hours": 250, "delay_probability": 0.08, "risks": {"geopolitical": 0.2}},
    {"route_id": "C", "cost": 900,  "transit_hours": 320, "delay_probability": 0.10, "risks": {"geopolitical": 0.5}}
  ]
}
```

[`examples/S03_balanced.json`](examples/S03_balanced.json) is a fuller fixture with `legs` and `congestion`; the other three examples cover an empty feasible set, absent geopolitical data and a rejected input. Any corpus shipment can be exported with `shipment-decision show S07 --out my_shipment.json`.

### Running it

```
shipment-decision score <shipment.json> [--priority {min_cost,min_time,min_risk,balanced}] [--text]
shipment-decision show <SHIPMENT_ID> [--out PATH]
shipment-decision evaluate [--json PATH] [--markdown PATH]
```

- The priority comes from the file's `priority` field; `--priority` overrides it before validation.
- Hard limits and weights are set in the JSON (`constraints`, `weights`); there are no CLI flags for them.
- `--text` prints only the explanation; without it the full JSON result is printed.
- Exit code 0 for `recommended` and `no_feasible_route`, 2 for `invalid_input`. Files with a UTF-8 BOM (as PowerShell's `Out-File` writes) are accepted.

### Output

For the example above, `--text` gives:

```
Shipment DEMO: recommended route A.
Priority 'balanced': lowest weighted score using default equal weights (cost 0.250, transit time 0.250, delay probability 0.250, geopolitical risk 0.250).
Route A: cost 1,000, 240 h, delay probability 0.400, geopolitical risk 0.200.
Weighted score 0.2500 versus 0.5000 for runner-up B (margin 0.2500).
Score contributions for A: cost 0.0000, transit time 0.0000, delay probability 0.2500, geopolitical risk 0.0000.
Compared with B: cost 1,000 vs 1,200 (lower); transit time 240 h vs 250 h (lower); delay probability 0.400 vs 0.080 (higher); geopolitical risk equal at 0.200.
Single-objective references among feasible routes: cheapest A (1,000), fastest A (240 h), lowest delay B (0.080), lowest geopolitical risk A (0.200).
Identical across all feasible routes and therefore not affecting the ranking: geopolitical risk.
Excluded by hard constraints: C (max_transit_hours).
```

The JSON result (abridged; every route carries the same fields, with `null` scores for infeasible routes) is:

```json
{
  "status": "recommended",
  "priority": "balanced",
  "recommended_route_id": "A",
  "runner_up_route_id": "B",
  "score_margin": 0.25,
  "effective_weights": {"cost": 0.25, "time": 0.25, "delay": 0.25, "geopolitical": 0.25},
  "weight_source": "default",
  "constraints_applied": {"max_transit_hours": 300.0},
  "routes": [
    {"route_id": "A", "feasible": true, "failed_constraints": [],
     "normalized": {"cost": 0.0, "time": 0.0, "delay": 1.0, "geopolitical": 0.0},
     "score": 0.25, "rank": 1, "non_dominated_all_available": true, "balance_gap": 1.0},
    {"route_id": "B", "feasible": true, "failed_constraints": [],
     "normalized": {"cost": 1.0, "time": 1.0, "delay": 0.0, "geopolitical": 0.0},
     "score": 0.5, "rank": 2, "non_dominated_all_available": true, "balance_gap": 2.0},
    {"route_id": "C", "feasible": false, "failed_constraints": ["max_transit_hours"],
     "normalized": null, "score": null, "rank": null, "non_dominated_all_available": null, "balance_gap": null}
  ],
  "explanation": "Shipment DEMO: recommended route A. ..."
}
```

Other top-level fields: `schema_version`, `errors`, `objectives_available` / `active` / `inactive` / `unavailable`, `selection_keys`, `normalization_notes`, `comparison` (single-objective references and a per-objective comparison with the runner-up). Each route also carries its raw inputs, `contributions` per objective and `non_dominated_selection`. Values are rounded only in the text; the JSON holds the unrounded numbers.

## Limitations and assumptions

- **Normalisation is relative to the feasible set.** With two feasible routes, min-max records only which route is worse on each objective, not by how much (S04); adding or removing a non-winning route can change the winner among the others (S05). Raw values are always shown beside scores, and scores are not comparable across shipments.
- **Equal default weights are a convention**, not an elicited preference. Unequal weights change the recommendation (S15); the weight-sensitivity results show where ±0.10 matters.
- **Geopolitical risk is assumed independent of delay probability.** If a real dataset's delay estimates already reflect geopolitical disruption, this scores it twice. Nothing in the assignment lets that dependence be measured, so the assumption is stated rather than tested.
- **Congestion never changes a recommendation** (S13). An operator who regards congestion as independent of the supplied delay probability will not see that preference represented.
- **The corpus is designed, not sampled.** It can expose implementation errors and illustrate trade-offs; it supports no claim about average real-world savings or typical performance. Sensitivity flip rates are properties of this rule on these numbers, not confidence intervals.
- **Ties between identical routes are broken by route id**, so any perturbation to one of them flips the result (S13, S17 in the route-specific experiment).
- The system does not construct routes, predict attributes, or model time windows, connections or delay duration.

## Rebuilding the report PDF

`python scripts/build_report.py --pdf` converts `docs/technical_report.md` to `docs/technical_report.pdf` using only the standard library plus an installed Edge or Chrome in headless mode (for page numbers). The intermediate `docs/technical_report.html` is git-ignored.
