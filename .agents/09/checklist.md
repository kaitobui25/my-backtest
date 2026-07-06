# Plan 9 Checklist - Exact Streaming Runner + Plan 7 Feature Flags

## Goal

- [ ] Keep search exact: no heuristic pruning.
- [ ] Prevent web runs from materializing all heavy strategy variants/rows in memory.
- [ ] Make Plan 7 metrics opt-in, default OFF.
- [ ] Keep research/full `run_search()` behavior available.

---

## 1. Feature Flag Schema

Backend:

- [ ] Add `use_rr_metrics` search param, default `false`.
- [ ] Add `compute_ambiguity_metrics` search param, default `false`.
- [ ] Keep `entry_mode` default as `same_open`.
- [ ] Keep `use_spread_slippage` default `false`.
- [ ] Keep `use_position_sizing` default `false`.
- [ ] Keep `use_leverage` default `false`.
- [ ] Keep `use_liquidation` default `false`.

Frontend:

- [ ] Add checkbox `Show RR metrics`, default OFF.
- [ ] Add checkbox `Compute ambiguity metrics`, default OFF.
- [ ] Ensure existing Plan 7 checkboxes default OFF.
- [ ] Include new flags in `buildSearchParams()`.
- [ ] Include new flags in config snapshot and dirty tracking.
- [ ] Save and restore new flags in saved runs.

Acceptance:

- [ ] Fresh page load has all Plan 7 feature flags OFF.
- [ ] Default payload sends opt-in flags as false.
- [ ] Loading old saved runs leaves new flags OFF.

---

## 2. Optional Columns

Backend:

- [ ] Core columns are always returned.
- [ ] `rr`, `realized_rr` are returned only when `use_rr_metrics` is true.
- [ ] `ambiguous_trades`, `ambiguous_rate` are returned only when `compute_ambiguity_metrics` is true.
- [ ] `equity_total_return`, `equity_max_drawdown`, `final_equity` are returned only when equity/risk computation is enabled.
- [ ] `liquidated_trades`, `liquidation_rate` are returned only when `use_liquidation` is true.

Frontend:

- [ ] Table receives and renders optional columns only when present.
- [ ] Running config view shows enabled metric groups.

Acceptance:

- [ ] Default run excludes Plan 7 optional columns.
- [ ] Turning each flag ON includes the expected columns.

---

## 3. Optional Filter Validation

Backend:

- [ ] Classify always-available core filter fields.
- [ ] Classify RR-only filter fields.
- [ ] Classify ambiguity-only filter fields.
- [ ] Classify equity-only filter fields.
- [ ] Classify liquidation-only filter fields.
- [ ] Reject disabled optional filters with a clear HTTP 400.
- [ ] Allow optional filters when their feature flag is enabled.

Frontend:

- [ ] Filter dropdown hides disabled optional fields.
- [ ] Filter dropdown updates when feature flags change.
- [ ] Existing favorites do not force hidden disabled fields into the dropdown.

Acceptance:

- [ ] Filtering `rr` with RR metrics OFF fails clearly or is unavailable in UI.
- [ ] Filtering `rr` with RR metrics ON works.
- [ ] Same behavior is covered for ambiguity/equity/liquidation fields.

---

## 4. Lazy Signal Variants

Backend:

- [ ] Add `iter_signals()` to yield signal tuples one at a time.
- [ ] Add `iter_signal_variants()` to yield `SignalVariant` one at a time.
- [ ] Enforce strategy filtering before building each strategy block.
- [ ] Enforce `max_signal_variants` during iteration.
- [ ] Keep `build_signal_variants()` as a list wrapper for existing callers/tests.

Acceptance:

- [ ] `max_signal_variants=1` for `VOL_EXPANSION_CONT` does not build all variants.
- [ ] Existing signal tests still pass.

---

## 5. Exact Limited Runner

Backend:

- [ ] Add API-facing limited runner.
- [ ] Iterate timeframe -> signal variant -> side mode.
- [ ] Simulate each chunk fully with existing batch kernel.
- [ ] Convert the chunk to rows.
- [ ] Apply request filters to chunk rows.
- [ ] Keep exact top `limit` rows using the same sort keys as current runner.
- [ ] Do not discard a candidate before full metrics and score are computed.
- [ ] Keep existing full `run_search()` path usable.

Acceptance:

- [ ] Limited runner output equals full runner + filters + head on small requests.
- [ ] API `/api/backtest` uses limited runner.
- [ ] Full scripts can still call `run_search()`.

---

## 6. Performance Guardrails

- [ ] Avoid building full `rows` list for web requests.
- [ ] Avoid building full signal variant list for web requests.
- [ ] Build config grid once per timeframe where possible.
- [ ] Do not introduce new pandas DataFrame concatenation inside hot loops unless chunk is small.

Acceptance:

- [ ] Heavy `VOL_EXPANSION_CONT` request starts producing work without upfront multi-GB signal materialization.
- [ ] `max_signal_variants` materially shortens heavy requests.

---

## 7. Tests

Backend tests:

- [ ] Default API columns exclude optional Plan 7 columns.
- [ ] RR flag includes RR columns.
- [ ] Ambiguity flag includes ambiguity columns.
- [ ] Position sizing flag includes equity columns.
- [ ] Liquidation flag includes liquidation columns.
- [ ] Disabled optional filter returns 400.
- [ ] Enabled optional filter works.
- [ ] Limited runner matches full runner on small request.
- [ ] Lazy `max_signal_variants` is applied before full materialization.

Frontend/manual tests:

- [ ] New checkboxes default OFF.
- [ ] Toggling options updates payload.
- [ ] Saved run restores toggles.
- [ ] Filter fields update when toggles change.

---

## Final Acceptance

- [ ] Default normal web run is lighter than Plan 7 behavior.
- [ ] Heavy strategy search remains exact.
- [ ] No good strategy is dropped by pruning.
- [ ] Optional Plan 7 features are user-controlled.
- [ ] Tests pass.
