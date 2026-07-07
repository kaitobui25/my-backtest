Focus only on normal mode. Ignore dense_high_winrate for now.

Goal:
Normal mode must be the only mode users need.
It must be fast, RAM-balanced, exact, and good at finding robust setups.
Do not optimize by random sampling, truncating variants blindly, weakening filters, or changing backtest semantics silently.

Phase 1:
1. Add diagnostics to /api/backtest normal runs:
   load_data_sec, indicator_sec, signal_build_sec, simulate_sec, row_build_sec,
   variants_generated, variants_skipped_low_signal, side_modes_scanned,
   kernel_calls, configs_tested, rows_kept.
2. Build IndicatorContext once per timeframe and reuse it across all strategy builders.
3. Refactor strategy signal generation so MACD/Supertrend/Wavetrend/Squeeze and common indicators are not recomputed inside inner parameter loops.
4. Add simulate_many_configs_normal_core_summary:
   - returns all current CORE_COLUMNS metrics
   - avoids Plan 7 branches when execution/risk features are disabled
   - keeps exact same normal semantics
5. Use safe pre-simulation pruning only:
   strategy/timeframe/side_mode/params filters, low raw signal count, impossible TP/cost configs.
6. Add tests comparing old normal output vs new normal-core output on small samples.

Phase 2:
1. Redesign normal default search space to be balanced, not dense.
2. Keep normal as the only user-facing mode.
3. Add top-candidate verification inside normal.
4. Add stability metrics for top results:
   stability_score, neighbor_pass_count, neighbor_avg_pf, neighbor_avg_test_win_rate.
5. Update score ranking to prefer robust tradeable setups:
   test PF, test winrate, sufficient trades, drawdown, max gap days, stability.
6. Keep dense_high_winrate untouched/ignored for now.