Phase 2 Checklist — Refactor Runner and API Flow

Files to touch:
- app/backtest/runner.py
- app/api/routes_backtest.py
- app/api/schemas.py
- app/backtest/signals.py only if import adjustment is needed

Checklist:

[ ] Update run_search() signature:
    - timeframes=None
    - mode="normal"
    - strategies=None
    - search_params=None

[ ] Update evaluate_timeframe() signature:
    - pass strategies
    - pass search_params

[ ] Update evaluate_normal_timeframe():
    - use build_signal_variants()
    - loop over SignalVariant
    - remove direct dependency on build_signals()

[ ] Update evaluate_dense_timeframe():
    - use build_signal_variants()
    - loop over SignalVariant
    - remove direct call to build_vol_expansion_signals()
    - remove hardcoded "VOL_EXPANSION_CONT"

[ ] Keep existing metrics unchanged:
    - win_rate
    - test_win_rate
    - profit_factor
    - score
    - dense stats

[ ] Add search_params to API request schema.

[ ] Keep filters as result filters only.

[ ] Update API route:
    - pass request.strategies into run_search()
    - pass request.search_params into run_search()

[ ] Do not change simulator logic.

[ ] Do not fix dense OOS entry/exit bug yet.

[ ] Do not change thresholds in config.py.

Smoke checks:

[ ] normal mode + ["VOL_EXPANSION_CONT"]
    Expected: only VOL_EXPANSION_CONT is simulated.

[ ] normal mode + ["EMA_PULLBACK"]
    Expected: only EMA_PULLBACK is simulated.

[ ] dense_high_winrate + ["VOL_EXPANSION_CONT"]
    Expected: dense result works.

[ ] dense_high_winrate + ["EMA_PULLBACK"]
    Expected: empty result or safe skip, no crash.

[ ] no strategies selected
    Expected: default behavior still works.

Done when:

[ ] Runner consumes only SignalVariant objects.
[ ] API-selected strategies affect simulation before backtest loop.
[ ] No hardcoded strategy name remains in dense runner.
[ ] Existing frontend request still works.
[ ] Metrics/output format stay compatible.
