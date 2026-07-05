Phase 3 Checklist — Consistency Fixes and Safety Tests

Files to touch:
- app/backtest/runner.py
- app/backtest/config.py
- app/api/routes_backtest.py
- app/api/routes_options.py if needed
- tests/ or simple smoke test script

Checklist:

[ ] Fix dense OOS split:
    - use exits for test split
    - replace is_test_exit[entries] with is_test_exit[exits]

[ ] Handle H2 safely:
    - add H2 thresholds to MIN_FULL_TRADES / MIN_TEST_TRADES
    - or reject H2 clearly in normal mode

[ ] Stabilize empty DataFrame columns:
    - include dense columns in REQUIRED_COLUMNS
    - make empty normal/dense results frontend-safe

[ ] Add missing dense columns:
    - trades_per_day
    - max_gap_days
    - avg_bars_held
    - test_trades_per_day
    - test_max_gap_days
    - test_avg_bars_held

[ ] Guard division by zero:
    - days == 0
    - test_days == 0
    - no trades
    - less than 2 entries for max gap

[ ] Make result filters safe:
    - filtering by missing column should not crash
    - return clear error or skip safely

[ ] Keep simulator behavior unchanged.
    - do not change TP/SL logic
    - do not merge simulators yet

[ ] Add smoke tests:
    - dense OOS uses exits
    - normal + H2 works or fails clearly
    - empty result has stable columns
    - invalid result filter does not crash
    - dense unsupported strategy returns empty safely

Done when:
[ ] dense and normal OOS split are consistent
[ ] frontend does not break on empty results
[ ] normal H2 behavior is safe
[ ] missing filter columns do not crash API
[ ] no simulator logic changed
