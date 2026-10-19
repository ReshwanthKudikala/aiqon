# Command-line demo (< 5 minutes). Run from the repository root after `pip install -e ".[test]"`,
# or with PYTHONPATH=src using `python -m shipment_decision` instead of `shipment-decision`.
$ErrorActionPreference = "Continue"
$cmd = "shipment-decision"
if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { $env:PYTHONPATH = "src"; $cmd = "python -m shipment_decision" }

Write-Host "`n# 1. The brief's example: a slightly dearer route with much lower delay (S03, balanced)" -ForegroundColor Cyan
Invoke-Expression "$cmd score examples/S03_balanced.json --text"

Write-Host "`n# 2. Same shipment, priority min_cost: the cheap route wins and the explanation says what it gives up" -ForegroundColor Cyan
Invoke-Expression "$cmd score examples/S03_balanced.json --priority min_cost --text"

Write-Host "`n# 3. Geopolitical data absent on every route: objective disabled, weights 1/3 each, nothing filled with zero" -ForegroundColor Cyan
Invoke-Expression "$cmd score examples/S12_no_geopolitical.json --text"

Write-Host "`n# 4. Hard limits exclude everything: an explicit no-recommendation, nothing relaxed" -ForegroundColor Cyan
Invoke-Expression "$cmd score examples/S10_no_feasible.json --text"

Write-Host "`n# 5. Partial risk data is rejected rather than guessed" -ForegroundColor Cyan
Invoke-Expression "$cmd score examples/X01_invalid.json --text"

Write-Host "`n# 6. Full evaluation: four methods, gaps, dominance, sensitivity (measured, including the trade-offs balanced loses)" -ForegroundColor Cyan
Invoke-Expression "$cmd evaluate"
