# Plan 9 - Exact Streaming Runner + Plan 7 Feature Flags

## Goal

Fix normal-mode web runs that become very slow and memory-heavy after Plan 7.

Keep search exact:
- Do not use heuristic pruning.
- Do not drop any candidate before it is fully simulated.
- Chunk/stream only changes memory ownership, not ranking semantics.

Make Plan 7 features opt-in:
- Default web run should not compute or expose extra Plan 7 metrics unless selected.
- Optional filters should only be allowed when their metric group is enabled.

## Assumptions

- The web API only needs the first `limit` rows for the submitted request.
- Research scripts can keep using `run_search()` for full DataFrame output.
- Web path may use a new exact limited runner to avoid holding all rows.
- Existing saved runs without new flags should load with all Plan 7 feature flags OFF.

## Phase 1 - Feature Flags

Add search params:
- `use_rr_metrics`: default false.
- `compute_ambiguity_metrics`: default false.
- `use_position_sizing`: already exists, default false.
- `use_leverage`: already exists, default false.
- `use_liquidation`: already exists, default false.

UI defaults:
- `Entry next open`: OFF.
- `Use spread/slippage`: OFF.
- `Show RR metrics`: OFF.
- `Compute ambiguity metrics`: OFF.
- `Position sizing`: OFF.
- `Use leverage`: OFF.
- `Liquidation`: OFF.

Backend behavior:
- RR columns appear only when `use_rr_metrics` is true.
- Ambiguity columns appear only when `compute_ambiguity_metrics` is true.
- Equity columns appear only when position sizing, leverage, or liquidation is enabled.
- Liquidation columns appear only when liquidation is enabled.
- Extra cost, next-open entry, equity, leverage, liquidation stay opt-in.

Verify:
- Default API/web columns exclude optional Plan 7 columns.
- Enabling each option includes its columns.
- Saved run metadata persists and restores flags.

## Phase 2 - Lazy Signal Variants

Add an iterator path:
- `iter_signals(...)` yields one signal tuple at a time.
- `iter_signal_variants(...)` yields `SignalVariant` one at a time.
- `max_signal_variants` is enforced during iteration, not after materializing all variants.
- Strategy filtering happens before building a strategy block.

Verify:
- `max_signal_variants=1` on `VOL_EXPANSION_CONT` does not build all variants.
- `build_signal_variants()` remains as a list wrapper for existing tests/scripts.

## Phase 3 - Exact Limited Runner for Web

Add a limited runner for API:
- Iterate timeframes, variants, side modes.
- Simulate each candidate chunk fully with existing batch kernel.
- Convert only that chunk to rows.
- Apply request filters to chunk rows.
- Keep only exact top `limit` rows by the same final sort keys:
  - normal: `score`, `test_profit_factor`, `test_total_return`
  - dense: `score`, `test_total_return`, `test_profit_factor`

No candidate is discarded before full metrics and score are computed.

Verify:
- On small requests, limited runner output equals old `run_search()` + `apply_filters()` + `head(limit)`.
- Web API uses limited runner.
- `run_search()` remains available for full research output.

## Phase 4 - Filter Validation

Classify fields:
- Core fields are always filterable.
- RR fields require `use_rr_metrics`.
- Ambiguity fields require `compute_ambiguity_metrics`.
- Equity fields require position sizing, leverage, or liquidation.
- Liquidation fields require liquidation.

Verify:
- Filtering by disabled optional field returns a clear 400.
- Filtering by enabled optional field works.

## Phase 5 - Tests

Backend tests:
- Default run excludes optional Plan 7 columns.
- Enabling RR includes `rr` and `realized_rr`.
- Enabling ambiguity includes `ambiguous_trades` and `ambiguous_rate`.
- Enabling position sizing includes equity columns.
- Enabling liquidation includes liquidation columns.
- Disabled optional filters are rejected.
- Enabled optional filters work.
- Limited runner matches full runner on small request.
- `max_signal_variants` is applied before materializing all variants.

Manual frontend checks:
- All new checkboxes default OFF.
- Payload includes flags when toggled.
- Saved run restore keeps checkbox states.
- Optional columns appear only when enabled.
