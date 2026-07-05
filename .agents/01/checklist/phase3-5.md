Task: Phase 3.5 — Clean signal builder registry

Clean up the Phase 1–3 refactor. Keep scope small. Do not change strategy formulas, simulator logic, metrics, API behavior, or frontend.

Goal:
Make build_signal_variants() truly use STRATEGY_BUILDERS, remove dead/unused registry-style code, and make the signal builder architecture cleaner.

Files:
- app/backtest/signals.py
- app/backtest/runner.py only if import cleanup is needed
- app/api/routes_backtest.py only if improving missing filter error

Requirements:

1. Make STRATEGY_BUILDERS the real source of truth.

   build_signal_variants() should use the registry instead of hardcoded if/else logic.

2. Expected behavior:

   strategies=None:
   - normal mode: build all normal-supported strategies
   - dense_high_winrate mode: build all dense-supported strategies

   strategies=["VOL_EXPANSION_CONT"]:
   - normal mode: build only VOL_EXPANSION_CONT normal variants
   - dense_high_winrate mode: build only VOL_EXPANSION_CONT dense variants

   strategies=["EMA_PULLBACK"] + dense_high_winrate:
   - return [] safely
   - no crash

3. Remove or reduce anonymous dense tuple public path.

   Prefer dense builder returns SignalVariant directly, or keep the old function private and expose only SignalVariant through registry.

4. Remove unused code/imports:
   - unused Callable if no longer needed
   - unused SignalVariant import in runner.py if not referenced directly
   - unused helper functions if replaced by registry

5. Do not change:
   - strategy formulas
   - TP/SL logic
   - simulate_trades logic
   - metrics
   - thresholds
   - API request/response shape
   - frontend

6. Optional small improvement:
   If apply_result_filter() receives a field missing from df.columns, return HTTPException 400 with a clear message instead of silently returning empty results.

Smoke checks:
- build_signal_variants(df, "M15", "normal", None)
- build_signal_variants(df, "M15", "normal", ["VOL_EXPANSION_CONT"])
- build_signal_variants(df, "M15", "dense_high_winrate", None)
- build_signal_variants(df, "M15", "dense_high_winrate", ["VOL_EXPANSION_CONT"])
- build_signal_variants(df, "M15", "dense_high_winrate", ["EMA_PULLBACK"])

Expected:
- registry is actually used
- dense unsupported strategy returns []
- runner still works
- no output metric changes
- no simulator behavior changes

After implementation, summarize:
- files changed
- registry cleanup done
- removed dead code/imports
- smoke test result
