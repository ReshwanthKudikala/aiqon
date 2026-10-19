# Evaluation results (measured)

Corpus: 20 shipments; 19 with a feasible route; no-feasible rate 0.050.

## Winners per shipment

| Shipment | Purpose | min_cost | min_time | min_risk | balanced | balanced S margin | S-min | B-min |
|---|---|---|---|---|---|---|---|---|
| S01 | Four-way conflict among cost, time, delay, geopolitical | C | F | M | M | 0.1704 | M | M |
| S02 | Tiny delay improvement against a large cost increase | C | F | M | C | 0.1916 | C | C |
| S03 | Brief's example: higher cost, much lower delay | C | F | R | R | 0.1071 | R | R |
| S04 | Two feasible routes: min-max erases gap size | A | A | B | A | 0.2500 | A | A |
| S05 | S04 plus a non-winning route that changes the winner | A | A | B | B | 0.2487 | B | B |
| S06 | One route best on every objective | G | G | G | G | 0.1833 | G | G |
| S07 | Delay identical on all routes: normalized delay term is 0 | C | F | C | C | 0.0464 | C | C |
| S08 | Cost tie: min_cost falls through to delay tie-break | R_B | R_C | R_B | R_A | 0.0333 | R_A | R_A |
| S09 | One feasible route under max_transit_hours | A | A | A | A | null | A | A |
| S10 | Empty feasible set | none | none | none | none | null | none | none |
| S11 | Geopolitical risk changes the balanced winner | Q | Q | P | P | 0.1642 | P | P |
| S12 | S11 with geopolitical absent on every route | Q | Q | Q | Q | 0.0958 | Q | Q |
| S13 | Congestion differs, scored fields equal; input order reversed | R1 | R1 | R1 | R1 | 0.0000 | R1 | R1 (tie with R2) |
| S14 | Near-tie with a delay value on the clipping boundary | A | B | B | A | 0.0028 | A | A |
| S15 | S03 with unequal explicit weights | C | F | R | C | 0.1071 | C | R |
| S16 | Single supplied route | X | X | X | X | null | X | X |
| S17 | All scored values equal | R_A | R_A | R_A | R_A | 0.0000 | R_A | R_A (tie with R_B) |
| S18 | S11 with explicit zero geopolitical weight | Q | Q | P | Q | 0.0958 | Q | P |
| S19 | Cost limit applied before normalization | C | M | C | M | 0.0000 | M | C (tie with M) |
| S20 | Delay limit applied before normalization (F at equality) | R | F | R | R | 0.5000 | R | R |

## Aggregate by method (means over shipments where defined; n shown)

| Method | cost abs gap | time abs gap (h) | delay abs gap | geo abs gap | cost rel gap | time rel gap | delay rel gap | geo rel gap | mean S | mean B | non-dominated share | tie rate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| min_cost | 0.0 (n=19) | 28.9 (n=19) | 0.1163 (n=19) | 0.0944 (n=18) | 0.0000 (n=19) | 0.1488 (n=19) | 1.7269 (n=19) | 1.8889 (n=18) | 0.1681 (n=19) | 0.7618 (n=19) | 1.000 | null (n=0) |
| min_time | 242.1 (n=19) | 0.0 (n=19) | 0.0558 (n=19) | 0.2833 (n=18) | 0.2386 (n=19) | 0.0000 (n=19) | 0.9715 (n=19) | 3.2685 (n=18) | 0.2631 (n=19) | 1.0543 (n=19) | 1.000 | null (n=0) |
| min_risk | 84.3 (n=19) | 29.6 (n=19) | 0.0237 (n=19) | 0.0111 (n=18) | 0.0835 (n=19) | 0.1526 (n=19) | 0.2982 (n=19) | 0.1111 (n=18) | 0.1658 (n=19) | 0.6528 (n=19) | 1.000 | 0.176 (n=17) |
| balanced | 47.4 (n=19) | 23.2 (n=19) | 0.0547 (n=19) | 0.0694 (n=18) | 0.0470 (n=19) | 0.1235 (n=19) | 0.8497 (n=19) | 1.1667 (n=18) | 0.1300 (n=19) | 0.6094 (n=19) | 1.000 | 0.176 (n=17) |

## Validation fixtures

| Fixture | Expected code | Rejected | Codes raised |
|---|---|---|---|
| X01 | incomplete_risk | True | incomplete_risk |
| X02 | objective_requested_without_data | True | objective_requested_without_data |
| X03 | weights_sum | True | weights_sum |
| X04 | cost_negative | True | cost_negative |

## Weight sensitivity (balanced only, delta = 0.10, proportional renormalisation)

- Perturbations applied: 148; skipped: 0 ({})
- Flips: 10 (flip rate 0.0676)
- Shipments flipped: S07, S08, S14, S19
- Mean original margin, flipped shipments: 0.0206 (n=4)
- Mean original margin, unflipped shipments: 0.1626 (n=13)
  - S07: cost down -> C becomes M (original margin 0.0464)
  - S07: time up -> C becomes M (original margin 0.0464)
  - S08: time down -> R_A becomes R_B (original margin 0.0333)
  - S08: delay up -> R_A becomes R_B (original margin 0.0333)
  - S14: cost down -> A becomes B (original margin 0.0028)
  - S14: delay up -> A becomes B (original margin 0.0028)
  - S19: cost up -> M becomes C (original margin 0.0000)
  - S19: time down -> M becomes C (original margin 0.0000)
  - S19: delay down -> M becomes C (original margin 0.0000)
  - S19: geopolitical up -> M becomes C (original margin 0.0000)

## Delay-probability sensitivity (eps = +/-0.05, clipped to [0,1], feasibility fixed)

| Family | Method | Applied | Flips | Flip rate | Shipments flipped | Mean margin flipped | Mean margin unflipped | Limit crossings counted |
|---|---|---|---|---|---|---|---|---|
| uniform | min_cost | 38 | 0 | 0.0000 | none | null (n=0) | null (n=0) | 1 |
| uniform | min_time | 38 | 0 | 0.0000 | none | null (n=0) | null (n=0) | 1 |
| uniform | min_risk | 38 | 0 | 0.0000 | none | null (n=0) | 0.2803 (n=17) | 1 |
| uniform | balanced | 38 | 1 | 0.0263 | S14 | 0.0028 (n=1) | 0.1371 (n=16) | 1 |
| route_specific | min_cost | 106 | 4 | 0.0377 | S13, S17 | null (n=0) | null (n=0) | 1 |
| route_specific | min_time | 106 | 4 | 0.0377 | S13, S17 | null (n=0) | null (n=0) | 1 |
| route_specific | min_risk | 106 | 10 | 0.0943 | S02, S07, S12, S13, S17 | 0.0587 (n=5) | 0.3726 (n=12) | 1 |
| route_specific | balanced | 106 | 12 | 0.1132 | S07, S08, S13, S14, S17 | 0.0165 (n=5) | 0.1762 (n=12) | 1 |

Margins are defined only for balanced and min_risk (weighted-score modes); lexicographic modes report null. Flip rates are deterministic sensitivity measurements on assigned scenario values, not calibrated uncertainty.
