Refactor Plan: Unified Signal Builder for normal and dense_high_winrate modes

Phase 1 — Create a unified signal builder layer

Goal:
Remove strategy-specific hardcoding from the runner and make all signal variants use the same structure.

Tasks:
1. Add a common SignalVariant model, for example:

   @dataclass(frozen=True)
   class SignalVariant:
       strategy: str
       params: str
       long_entries: np.ndarray
       short_entries: np.ndarray
       side_modes: tuple[str, ...]

2. Create a new central function:

   build_signal_variants(
       df,
       timeframe,
       mode,
       strategies=None,
   ) -> list[SignalVariant]

3. Move strategy selection logic into this builder layer.
   The runner should not directly call build_signals() or build_vol_expansion_signals() anymore.

4. Create a simple strategy registry:

   STRATEGY_BUILDERS = {
       "VOL_EXPANSION_CONT": {
           "normal": build_vol_expansion_normal,
           "dense_high_winrate": build_vol_expansion_dense,
       },
       "EMA_PULLBACK": {
           "normal": build_ema_pullback_normal,
       },
       ...
   }

5. For now, dense_high_winrate can support only strategies that have a dense builder.
   Unsupported strategies should be skipped safely, not hardcoded or crashed.

Acceptance:
- Both normal and dense modes return SignalVariant objects.
- No dense signal is missing a strategy name.
- build_vol_expansion_signals() no longer returns anonymous tuples.
- New strategies can be added by updating the registry, not the runner.


Phase 2 — Refactor runner and API flow

Goal:
Make selected strategies and search parameters affect the actual backtest search, not only post-filtered results.

Tasks:
1. Update run_search signature:

   run_search(
       timeframes=None,
       mode="normal",
       strategies=None,
       search_params=None,
   )

2. Pass strategies and search_params down through:

   run_search()
     -> evaluate_timeframe()
       -> evaluate_normal_timeframe() / evaluate_dense_timeframe()
         -> build_signal_variants()

3. In both normal and dense evaluators, replace direct signal calls with:

   signals = build_signal_variants(
       df=df,
       timeframe=timeframe,
       mode=mode,
       strategies=strategies,
   )

4. Loop over SignalVariant:

   for signal in signals:
       strategy = signal.strategy
       params = signal.params
       long_entries = signal.long_entries
       short_entries = signal.short_entries
       side_modes = signal.side_modes

5. Remove this kind of hardcode from dense mode:

   "strategy": "VOL_EXPANSION_CONT"

6. Update API route:

   df = run_search(
       timeframes=request.timeframes,
       mode=request.mode,
       strategies=request.strategies,
       search_params=request.search_params,
   )

7. Separate two concepts:
   - search_params: controls how the backtest search runs
   - filters: filters result rows after backtest

Example request shape:

{
  "mode": "dense_high_winrate",
  "timeframes": ["M15", "M30", "H1"],
  "strategies": ["VOL_EXPANSION_CONT"],
  "search_params": {
    "min_trades_per_day": 0.33,
    "min_win_rate": 75,
    "min_test_trades_per_day": 0.33,
    "min_test_win_rate": 75
  },
  "filters": [
    {"field": "profit_factor", "op": ">=", "value": 1.2}
  ],
  "limit": 100
}

Acceptance:
- If the user selects only one strategy, only that strategy is built and tested.
- dense_high_winrate no longer always runs VOL_EXPANSION_CONT by force.
- Strategy filtering happens before simulation, not only after simulation.
- Runner does not know strategy implementation details.


Phase 3 — Fix hidden consistency bugs and add safety tests

Goal:
Clean up mode inconsistencies and prevent silent wrong results.

Tasks:
1. Fix dense out-of-sample logic.
   Current dense mode uses entry index for test split.
   Change it to use exit index, same as normal mode.

   Preferred:
   test_mask = is_test_exit[exits]

2. Add H2 thresholds for normal mode or remove H2 from normal options.
   Do not allow H2 to appear in options if normal mode cannot run it safely.

3. Make empty result DataFrames stable.
   REQUIRED_COLUMNS should include both normal and dense columns, such as:

   trades_per_day
   max_gap_days
   avg_bars_held
   test_trades_per_day
   test_max_gap_days
   test_avg_bars_held

4. Guard against division by zero:
   - days == 0
   - test_days == 0
   - no trades
   - less than 2 entries when calculating max gap

5. Make result filters safe.
   If the user filters by a column that does not exist for the current mode, do not crash.
   Either ignore safely or return a clear validation error.

6. Add tests:

   Test 1:
   normal mode + selected strategy
   Expected: only selected strategy appears in results.

   Test 2:
   dense_high_winrate + VOL_EXPANSION_CONT
   Expected: dense results appear, strategy column is VOL_EXPANSION_CONT, no hardcode in runner.

   Test 3:
   dense_high_winrate + unsupported strategy
   Expected: returns empty result safely, not crash.

   Test 4:
   normal mode + H2
   Expected: either works with thresholds or is rejected clearly.

   Test 5:
   empty results
   Expected: DataFrame still has stable columns.

   Test 6:
   dense OOS split
   Expected: test metrics are based on exit time, consistent with normal mode.

Acceptance:
- No hardcoded strategy name remains in runner.
- dense and normal modes use the same signal interface.
- API selected strategies affect actual simulation.
- Empty results do not break frontend/table rendering.
- Adding a new dense strategy only requires adding a builder and registering it.
