# Phase 2 Checklist — Refactor Runner to Use Batch Engine

## Scope

- Work only on current backend source.
- Do not switch to vectorbt API.
- Do not change frontend code.
- Do not change `/api/backtest`.
- Do not change API schema or response columns.
- Keep saved-runs behavior unchanged.
- Keep old single-config engine functions as reference/debug.

## Files to Add / Update

- [ ] Add `app/backtest/result_builder.py`
- [ ] Update `app/backtest/runner.py`
- [ ] Use existing Phase 1 files:
  - `app/backtest/batch_engine.py`
  - `app/backtest/grid.py`

## Result Builder

- [ ] Convert batch summary arrays into result rows.
- [ ] Preserve current row field names.
- [ ] Preserve `REQUIRED_COLUMNS`.
- [ ] Preserve normal mode scoring with `score_candidate`.
- [ ] Preserve dense mode scoring with `score_dense_candidate`.
- [ ] Keep sorting behavior unchanged.
- [ ] Keep `params`, `strategy`, `side_mode`, `sl`, `tp`, `max_hold` values correct.

## Runner Refactor

- [ ] Refactor `evaluate_normal_timeframe(...)`.
- [ ] Refactor `evaluate_dense_timeframe(...)`.
- [ ] Load OHLC once per timeframe.
- [ ] Build signal variants once per timeframe.
- [ ] Loop by:
  - signal variant
  - side_mode
- [ ] Build config grid once per signal + side_mode.
- [ ] Call batch engine once per signal + side_mode.
- [ ] Filter batch results using the same old conditions.
- [ ] Convert accepted configs into rows.
- [ ] Return DataFrame with same columns as before.

## Must Preserve

- [ ] `run_search(...)` public function signature.
- [ ] `search_params` behavior.
- [ ] strategy filtering behavior.
- [ ] normal mode filters:
  - min_full_trades
  - min_test_trades
  - min_test_win_rate
  - min_profit_factor
  - min_test_profit_factor
  - total_return > 0
  - expectancy > 0
- [ ] dense mode filters:
  - min_trades_per_day
  - min_test_trades_per_day
  - min_win_rate
  - min_test_win_rate
  - total_return > 0
  - profit_factor >= 1.0
  - expectancy > 0
- [ ] normal sort order:
  - score
  - test_profit_factor
  - test_total_return
- [ ] dense sort order:
  - score
  - test_total_return
  - test_profit_factor

## Validation

- [ ] Compare old runner vs new batch runner on small limited search.
- [ ] Use `max_signal_variants` for fast comparison.
- [ ] Compare columns.
- [ ] Compare row count approximately.
- [ ] Compare key metrics for same strategy/params/side/sl/tp/max_hold.
- [ ] Confirm `/api/backtest` still works.
- [ ] Confirm frontend can still load results.
- [ ] Confirm saved-runs still save/load/export.

## Done Criteria

- [ ] `runner.py` uses batch engine instead of per-config Numba calls.
- [ ] API behavior unchanged.
- [ ] Output schema unchanged.
- [ ] Results match old logic on sample runs.
- [ ] Backend is faster for multi-config searches.
- [ ] Old single-config engine remains available for debugging.
