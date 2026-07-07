```text
# Phase 1 Checklist — Normal Mode Fast + Exact

## Core Principles

- [ ] Focus only on `normal` mode.
- [ ] Do not modify `dense_high_winrate` in this phase.
- [ ] Do not add random sampling.
- [ ] Do not blindly limit `max_signal_variants`.
- [ ] Do not weaken filters to make the scan faster.
- [ ] Do not remove full/test/OOS metrics.
- [ ] Do not change the scoring formula in Phase 1.
- [ ] Do not change the default search space in Phase 1.
- [ ] Do not silently change backtest semantics.
- [ ] RAM usage around 1–2 GB is acceptable.
- [ ] Priority order: correctness first, speed second, RAM balance third.
- [ ] Any optimization must be measurable and covered by tests.

---

## 1. Add Normal Mode Diagnostics

- [ ] Add timing diagnostics for every `/api/backtest` normal run.
- [ ] Track `load_data_sec`.
- [ ] Track `indicator_sec`.
- [ ] Track `signal_build_sec`.
- [ ] Track `simulate_sec`.
- [ ] Track `row_build_sec`.
- [ ] Track total runtime.
- [ ] Track `variants_generated`.
- [ ] Track `variants_skipped_low_signal`.
- [ ] Track `side_modes_scanned`.
- [ ] Track `kernel_calls`.
- [ ] Track `configs_tested`.
- [ ] Track `rows_before_filter`.
- [ ] Track `rows_after_filter`.
- [ ] Track `rows_kept`.
- [ ] Return diagnostics in API response under a clearly separated field, for example `diagnostics`.
- [ ] Do not mix diagnostics into result rows.
- [ ] Make diagnostics optional if needed, but enabled during development.

Acceptance:

- [ ] One normal backtest response clearly shows where time is spent.
- [ ] It is possible to tell whether the bottleneck is data loading, signal building, simulation, or row building.

---

## 2. Build Indicator Context Once Per Timeframe

- [ ] Create an `IndicatorContext` object or dataclass.
- [ ] Build it once per timeframe after OHLC data is loaded.
- [ ] Store common series/arrays in the context:
  - [ ] open
  - [ ] high
  - [ ] low
  - [ ] close
  - [ ] volume
  - [ ] ATR14
  - [ ] ATR100
  - [ ] ADX14
  - [ ] RSI14
  - [ ] EMA20
  - [ ] EMA34
  - [ ] EMA50
  - [ ] EMA100
  - [ ] EMA200
  - [ ] EMA300
  - [ ] volume moving average
  - [ ] volume filter
  - [ ] range
  - [ ] IBS
- [ ] Refactor normal signal builders to use `IndicatorContext`.
- [ ] Avoid recomputing common indicators for each strategy.
- [ ] Keep all indicator formulas unchanged.
- [ ] Keep shifted signal behavior unchanged.

Acceptance:

- [ ] Running the old and new signal generation on the same data produces identical long/short entry arrays.
- [ ] Common indicators are computed once per timeframe, not once per strategy.
- [ ] No strategy result changes due to this refactor.

---

## 3. Remove Repeated Indicator Computation Inside Parameter Loops

- [ ] Refactor MACD signal generation.
  - [ ] Compute each MACD preset once.
  - [ ] Reuse the MACD output across trend/adx combinations.
- [ ] Refactor Supertrend signal generation.
  - [ ] Compute each period/mult pair once.
  - [ ] Reuse it across trend filters.
- [ ] Refactor Wavetrend signal generation.
  - [ ] Compute each preset once.
  - [ ] Reuse it across trend modes.
- [ ] Refactor Squeeze Momentum signal generation.
  - [ ] Compute each length/bb/kc combination once.
  - [ ] Reuse it across trend filters.
- [ ] Refactor Williams Vix Fix if repeated calculations exist.
- [ ] Do not change signal formulas.
- [ ] Do not change parameter names.
- [ ] Do not change generated `params` strings unless absolutely necessary.

Acceptance:

- [ ] Old and new signal arrays match exactly for each strategy and parameter combination.
- [ ] Signal generation time is lower in diagnostics.
- [ ] No result rows disappear due to refactor mistakes.

---

## 4. Add Normal-Core Simulation Kernel

- [ ] Add a new Numba kernel, for example:
  `simulate_many_configs_normal_core_summary`.
- [ ] Use it only for normal mode when advanced execution/risk features are disabled.
- [ ] The new kernel must return all current normal core metrics:
  - [ ] trades
  - [ ] win_rate
  - [ ] total_return
  - [ ] profit_factor
  - [ ] expectancy
  - [ ] max_drawdown
  - [ ] avg_win
  - [ ] avg_loss
  - [ ] test_trades
  - [ ] test_win_rate
  - [ ] test_total_return
  - [ ] test_profit_factor
  - [ ] test_expectancy
  - [ ] trades_per_day
  - [ ] max_gap_days
  - [ ] avg_bars_held
  - [ ] test_trades_per_day
  - [ ] test_max_gap_days
  - [ ] test_avg_bars_held
- [ ] Keep entry/exit behavior identical to the current normal default path.
- [ ] Keep fee handling identical.
- [ ] Keep full/test split identical.
- [ ] Keep max-hold behavior identical.
- [ ] Keep long/short behavior identical.
- [ ] Keep forced close at final candle behavior identical.
- [ ] Do not include unused branches for:
  - [ ] next-open entry
  - [ ] spread/slippage
  - [ ] position sizing
  - [ ] leverage
  - [ ] liquidation
  - [ ] ambiguity metrics
- [ ] Fall back to the existing realistic kernel when any advanced feature is enabled.

Acceptance:

- [ ] With default normal settings, the new kernel produces the same result as the old kernel for a fixed test sample.
- [ ] Differences, if any, must be explained and covered by tests.
- [ ] Simulation time decreases in diagnostics.

---

## 5. Kernel Selection Logic

- [ ] Add clear kernel selection logic in normal runner.
- [ ] Use `normal_core` kernel when:
  - [ ] mode is `normal`
  - [ ] entry mode is default/same-open
  - [ ] spread/slippage is disabled
  - [ ] position sizing is disabled
  - [ ] leverage is disabled
  - [ ] liquidation is disabled
  - [ ] ambiguity metrics are disabled
- [ ] Use existing realistic kernel when:
  - [ ] next-open entry is enabled
  - [ ] spread/slippage is enabled
  - [ ] position sizing is enabled
  - [ ] leverage is enabled
  - [ ] liquidation is enabled
  - [ ] ambiguity metrics are enabled
- [ ] Keep UI as one mode only: `normal`.
- [ ] Do not expose a second mode to the user.

Acceptance:

- [ ] User still sees only normal mode.
- [ ] Internally, normal chooses the correct kernel safely.
- [ ] Diagnostics show which kernel was used.

---

## 6. Safe Pre-Simulation Pruning

- [ ] Keep existing low raw signal count pruning.
- [ ] Keep existing side-mode signal count pruning.
- [ ] Add pruning only when it is mathematically safe.
- [ ] If user selected specific strategies, build only those strategies.
- [ ] If user selected specific timeframes, load only those timeframes.
- [ ] If result filters include exact `side_mode`, run only matching side modes.
- [ ] If result filters include clear parameter constraints, generate only matching parameter combinations when safe.
- [ ] Skip impossible TP/cost configs before simulation.
- [ ] Do not prune based on assumptions like:
  - [ ] “ADX low is probably bad”
  - [ ] “TP small is probably bad”
  - [ ] “EMA200 is probably better”
  - [ ] “few trades might be bad”
- [ ] Do not remove candidates that could still pass filters.

Acceptance:

- [ ] Safe pruning reduces work without changing valid results.
- [ ] A run without filters produces the same result set as before.
- [ ] A run with filters skips unnecessary work earlier.

---

## 7. Row Building Optimization

- [ ] Keep row schema unchanged.
- [ ] Keep all current normal columns unchanged.
- [ ] Avoid building full row dictionaries for configs that fail hard filters.
- [ ] Apply numeric filters as early as possible after simulation.
- [ ] Avoid unnecessary DataFrame creation inside tight loops.
- [ ] Keep final sorting behavior unchanged.
- [ ] Keep final `limit` behavior unchanged.
- [ ] Keep result values and column names stable.

Acceptance:

- [ ] API output format remains compatible with frontend.
- [ ] Row building time decreases or remains stable.
- [ ] Final sorted results match the old implementation.

---

## 8. Tests

- [ ] Add tests for indicator context equivalence.
- [ ] Add tests for each strategy signal output before/after refactor.
- [ ] Add tests for normal-core kernel vs old realistic kernel under default normal settings.
- [ ] Add tests for long-only side mode.
- [ ] Add tests for both side mode.
- [ ] Add tests for full/test split.
- [ ] Add tests for max-hold exit.
- [ ] Add tests for forced final close.
- [ ] Add tests for min trade pruning.
- [ ] Add tests for kernel selection logic.
- [ ] Add tests to ensure dense mode is untouched.
- [ ] Add regression test using a small fixed OHLC sample.
- [ ] Add tolerance rules for floating-point comparisons.

Acceptance:

- [ ] Existing tests pass.
- [ ] New tests pass.
- [ ] Normal default output is stable.
- [ ] No dense behavior changes.

---

## 9. Frontend / API Compatibility

- [ ] Keep frontend mode name as `normal`.
- [ ] Do not add dense-related UI changes.
- [ ] Do not require the user to select a new mode.
- [ ] If diagnostics are returned, display them only in a debug/dev area.
- [ ] Do not pollute the result table with diagnostics fields.
- [ ] Keep existing result table columns working.
- [ ] Keep existing filters working.
- [ ] Keep Search Grid behavior unchanged in Phase 1.

Acceptance:

- [ ] Existing frontend workflow still works.
- [ ] Normal backtest button still runs normally.
- [ ] Result table remains compatible.
- [ ] Diagnostics can be inspected without affecting normal user flow.

---

## 10. Performance Validation

- [ ] Run baseline normal backtest before changes.
- [ ] Record:
  - [ ] total runtime
  - [ ] peak RAM
  - [ ] variants generated
  - [ ] kernel calls
  - [ ] configs tested
  - [ ] rows kept
- [ ] Run the same normal backtest after Phase 1 changes.
- [ ] Compare runtime.
- [ ] Compare peak RAM.
- [ ] Compare top results.
- [ ] Compare row count.
- [ ] Compare score ordering.
- [ ] Investigate any mismatch.
- [ ] Document before/after numbers.

Acceptance:

- [ ] Normal mode is measurably faster.
- [ ] RAM remains acceptable.
- [ ] Results remain correct.
- [ ] Any result difference is intentional, explained, and tested.

---

## Final Phase 1 Definition of Done

- [ ] Normal mode is faster.
- [ ] Normal mode remains exact.
- [ ] Normal mode keeps current default search space.
- [ ] Normal mode keeps current scoring.
- [ ] Normal mode keeps current result columns.
- [ ] Normal mode uses less wasted CPU.
- [ ] RAM remains within acceptable range.
- [ ] Diagnostics show clear bottlenecks.
- [ ] Tests protect against silent result changes.
- [ ] Dense mode is not touched.
```
