# Phase 1 Checklist — Custom Numba Batch Engine

## Scope

- Focus only on backend source code in `kaitobui25/my-backtest`.
- Do not switch to vectorbt API.
- Do not change frontend API contract.
- Do not change `/api/backtest` request/response format.
- Do not change strategy logic, filters, scoring, or output columns.

## Files to Add

- [ ] `app/backtest/batch_engine.py`
- [ ] `app/backtest/grid.py`

## File: `app/backtest/grid.py`

- [ ] Add `build_config_grid(sl_values, tp_values, max_holds)`.
- [ ] Return 3 NumPy arrays:
  - `sl_arr: np.ndarray[np.float64]`
  - `tp_arr: np.ndarray[np.float64]`
  - `max_hold_arr: np.ndarray[np.int64]`
- [ ] Keep config order identical to current `itertools.product(sl_values, tp_values, max_holds)`.
- [ ] Skip configs where `tp <= 2.5 * FEE_PER_SIDE` outside or inside batch consistently.
- [ ] Add simple test/manual check to confirm config order matches old loop order.

## File: `app/backtest/batch_engine.py`

- [ ] Add `@njit(cache=True)` batch kernel for normal mode:
  - `simulate_many_configs_summary(...)`
- [ ] Add `@njit(cache=True)` batch kernel for dense mode:
  - `simulate_many_configs_with_entries_summary(...)`

## Normal Mode Batch Kernel

- [ ] Must match current `simulate_trades(...)` behavior.
- [ ] Do not check TP/SL on the entry candle.
- [ ] Entry price is current candle open when entry signal is true.
- [ ] Exit by SL, TP, max_hold, or final close.
- [ ] Same-candle TP/SL conflict must keep current behavior: SL first.
- [ ] Return summary arrays, not full trade records.

## Dense Mode Batch Kernel

- [ ] Must match current `simulate_trades_with_entries(...)` behavior.
- [ ] Must check TP/SL on the entry candle.
- [ ] Entry price is current candle open when entry signal is true.
- [ ] Exit by SL, TP, max_hold, or final close.
- [ ] Same-candle TP/SL conflict must keep current behavior: SL first.
- [ ] Return summary arrays including entry/exit based metrics.

## Metrics to Return

For each config, return:

- [ ] `trades`
- [ ] `win_rate`
- [ ] `total_return`
- [ ] `profit_factor`
- [ ] `expectancy`
- [ ] `max_drawdown`
- [ ] `avg_win`
- [ ] `avg_loss`
- [ ] `test_trades`
- [ ] `test_win_rate`
- [ ] `test_total_return`
- [ ] `test_profit_factor`
- [ ] `test_expectancy`

For dense mode, also return:

- [ ] `trades_per_day`
- [ ] `max_gap_days`
- [ ] `avg_bars_held`
- [ ] `test_trades_per_day`
- [ ] `test_max_gap_days`
- [ ] `test_avg_bars_held`

## Compatibility Rules

- [ ] Keep old `engine.py` functions unchanged.
- [ ] Do not modify `runner.py` yet, except optional local import check if needed.
- [ ] Do not remove `metrics.py`.
- [ ] Do not remove old single-config Numba functions.
- [ ] Batch result must match old single-config result for sample configs.

## Validation

- [ ] Add temporary/manual validation comparing:
  - old `simulate_trades(...)` + `metrics(...)`
  - new `simulate_many_configs_summary(...)`
- [ ] Add temporary/manual validation comparing:
  - old `simulate_trades_with_entries(...)` + `metrics(...)`
  - new `simulate_many_configs_with_entries_summary(...)`
- [ ] Test at least:
  - `long_only`
  - `short_only`
  - `both`
  - `max_hold = 0`
  - `max_hold > 0`
  - config with no trades
  - config with only wins
  - config with only losses
- [ ] Run a warm-up call before timing to avoid Numba JIT noise.

## Done Criteria

- [ ] New batch engine compiles.
- [ ] Old engine remains untouched.
- [ ] Batch metrics match old metrics on sample configs.
- [ ] Config order matches old loop order.
- [ ] No frontend/API behavior changed.
- [ ] Phase 1 does not refactor runner yet.
