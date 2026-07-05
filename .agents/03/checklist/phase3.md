# Phase 3 Checklist — Validation, Benchmark, and Cleanup

## Scope

- Work only on current backend source.
- Do not switch to vectorbt API.
- Do not change frontend code.
- Do not change API schema.
- Do not change result columns.
- Do not change trading logic.

## Validation Tests

- [ ] Add tests comparing old single-config engine vs new batch engine.
- [ ] Test normal mode:
  - `simulate_trades(...)`
  - `simulate_many_configs_summary(...)`
- [ ] Test dense mode:
  - `simulate_trades_with_entries(...)`
  - `simulate_many_configs_with_entries_summary(...)`
- [ ] Compare metrics with floating tolerance.
- [ ] Compare by config key:
  - timeframe
  - strategy
  - params
  - side_mode
  - sl
  - tp
  - max_hold

## API Tests

- [ ] Test `POST /api/backtest`.
- [ ] Confirm response has:
  - `run_temp_id`
  - `row_count`
  - `columns`
  - `rows`
  - `timing`
- [ ] Confirm all `REQUIRED_COLUMNS` still exist.
- [ ] Confirm filters still work.
- [ ] Confirm `limit` still works.
- [ ] Confirm `search_params.max_signal_variants` still works.

## Saved Runs Tests

- [ ] Save run still works.
- [ ] Load saved run still works.
- [ ] Delete saved run still works.
- [ ] Export CSV still works.
- [ ] CSV columns unchanged.

## Benchmark

- [ ] Add benchmark script or test helper.
- [ ] Warm up Numba before timing.
- [ ] Measure old runner time.
- [ ] Measure new batch runner time.
- [ ] Report:
  - mode
  - timeframes
  - strategies
  - signal variants
  - total configs
  - kept rows
  - duration seconds
  - speedup ratio

## Cleanup

- [ ] Remove temporary debug code.
- [ ] Keep old single-config engine for reference/debug.
- [ ] Add short backend refactor note to README or docs.
- [ ] Do not remove old engine functions yet.
- [ ] Do not over-optimize cache/parallelism in this phase.

## Done Criteria

- [ ] Batch results match old logic on sample cases.
- [ ] API behavior unchanged.
- [ ] Saved-runs behavior unchanged.
- [ ] Benchmark proves speed improvement.
- [ ] Code is clean and documented.
