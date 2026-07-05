# 3-Phase Refactor Plan: Custom Numba Batch Backend

## Goal

Refactor the current backend in `kaitobui25/my-backtest` to use a custom Numba batch engine.

Do not use old script files `01/02/03`.
Do not switch to vectorbt API.
Do not change the frontend API contract.
Keep `/api/backtest`, request schema, response columns, filters, saved-runs behavior unchanged.

---

## Phase 1 — Add Batch Engine

### Objective
Replace per-config Numba calls with one batch call per signal + side_mode.

### Main changes

Create:

- `app/backtest/batch_engine.py`
- `app/backtest/grid.py`

Add batch kernels:

- `simulate_many_configs_summary(...)`
- `simulate_many_configs_with_entries_summary(...)`

Input:

- OHLC arrays
- long_entries
- short_entries
- sl_values
- tp_values
- max_hold_values
- fee_per_side
- test mask / test start index

Output summary arrays:

- trades
- win_rate
- total_return
- profit_factor
- expectancy
- max_drawdown
- avg_win
- avg_loss
- test_trades
- test_win_rate
- test_total_return
- test_profit_factor
- test_expectancy
- avg_bars_held
- max_gap_days

Important rule:

- Keep normal mode behavior unchanged.
- Keep dense mode behavior unchanged.
- Do not “fix” entry-candle TP/SL logic during this phase.

Expected result:

Current style:

    for sl, tp, max_hold:
        simulate_trades(...)

New style:

    simulate_many_configs_summary(... all sl/tp/max_hold configs ...)

---

## Phase 2 — Refactor Runner Around Batch Results

### Objective
Make `runner.py` use the new batch engine while keeping output identical.

### Main changes

Create:

- `app/backtest/result_builder.py`

Update:

- `app/backtest/runner.py`

Refactor:

- `evaluate_normal_timeframe(...)`
- `evaluate_dense_timeframe(...)`

New flow:

    load OHLC once
    build signals once
    for each signal variant:
        for each side_mode:
            build config grid
            run batch engine once
            filter summary arrays
            convert accepted configs to rows
    return DataFrame

Keep:

- `run_search(...)` public function unchanged
- API response columns unchanged
- `REQUIRED_COLUMNS` unchanged
- frontend behavior unchanged
- search_params behavior unchanged
- filters behavior unchanged

Expected result:

- Same results as old engine, except possible harmless row ordering differences.
- Much fewer Python -> Numba calls.
- Easier code path for normal and dense modes.

---

## Phase 3 — Validation, Benchmark, and Safe Cleanup

### Objective
Prove the batch engine matches the old engine before removing old runner loops.

### Main changes

Add tests:

- old `simulate_trades` vs new batch result for normal mode
- old `simulate_trades_with_entries` vs new batch result for dense mode
- sample configs across long_only / short_only / both
- sample configs with max_hold = 0 and max_hold > 0
- `/api/backtest` still returns valid columns and rows

Add benchmark:

- old runner time
- new batch runner time
- warm-up run before timing to avoid Numba JIT noise
- report number of tested configs and kept configs

Optional cleanup after validation:

- keep old single-config engine as reference/debug
- remove duplicated metrics work from Python loop
- document backend flow in README

Final target:

    Custom Numba batch engine
    Same API
    Same result schema
    Faster config sweep
    Lower Python loop overhead
    Old scripts 01/02/03 ignored
