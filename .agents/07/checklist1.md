```text
# Phase 1 Checklist — Core Backtest Realism

## Goal

- [ ] Add basic risk/reward metrics.
- [ ] Add realistic entry timing option.
- [ ] Add optional spread/slippage cost.
- [ ] Add intrabar ambiguity metrics.
- [ ] Add UI controls for the new options.
- [ ] Keep current behavior unchanged when all new options are OFF.

---

## 1. Add RR metric

Backend:

- [ ] Add `rr` column.
- [ ] Formula: `rr = tp / sl`.
- [ ] If `sl <= 0`, return `NaN`.
- [ ] Add `rr` to `REQUIRED_COLUMNS`.
- [ ] Add `rr` to `FILTER_FIELDS`.
- [ ] Add `rr` to normal result rows.
- [ ] Add `rr` to dense result rows.

UI:

- [ ] Make sure `rr` appears in the result table.
- [ ] Make sure `rr` can be selected in Result Filters.
- [ ] Format `rr` as a readable number.

Acceptance:

- [ ] `/api/backtest` returns `rr`.
- [ ] User can filter by `rr >= x`.
- [ ] Existing trade results are not changed.

---

## 2. Add realized RR metric

Backend:

- [ ] Add `realized_rr` column.
- [ ] Formula: `realized_rr = avg_win / abs(avg_loss)`.
- [ ] If `avg_win` or `avg_loss` is invalid, return `NaN`.
- [ ] If `avg_loss >= 0`, return `NaN`.
- [ ] Add `realized_rr` to `REQUIRED_COLUMNS`.
- [ ] Add `realized_rr` to `FILTER_FIELDS`.
- [ ] Add `realized_rr` to normal result rows.
- [ ] Add `realized_rr` to dense result rows.

UI:

- [ ] Make sure `realized_rr` appears in the result table.
- [ ] Make sure `realized_rr` can be selected in Result Filters.
- [ ] Format `realized_rr` as a readable number.

Acceptance:

- [ ] `/api/backtest` returns `realized_rr`.
- [ ] User can filter by `realized_rr >= x`.
- [ ] Existing trade results are not changed.

---

## 3. Add entry_next_open mode

Backend:

- [ ] Add `entry_mode` to `search_params`.
- [ ] Supported values:
  - `same_open`
  - `next_open`
- [ ] Default must be `same_open`.
- [ ] `same_open` must keep current behavior.
- [ ] `next_open` must enter at the next candle open.
- [ ] If signal appears at candle `i`, entry candle must be `i + 1`.
- [ ] If `i + 1` is outside data range, skip the signal.
- [ ] Do not check SL/TP on the signal candle when using `next_open`.
- [ ] Pass `entry_next_open` from `runner.py` into `batch_engine.py`.

UI:

- [ ] Add checkbox: `Entry next open`.
- [ ] Default checkbox state: OFF.
- [ ] OFF sends `entry_mode = "same_open"`.
- [ ] ON sends `entry_mode = "next_open"`.
- [ ] Save this option in saved run metadata.
- [ ] Restore this option when loading a saved run.

Acceptance:

- [ ] OFF gives behavior close to current code.
- [ ] ON uses `open[i + 1]` instead of `open[i]`.
- [ ] No lookahead entry is introduced.

---

## 4. Add spread/slippage option

Backend:

- [ ] Add `use_spread_slippage` to `search_params`.
- [ ] Add `spread_pct` to `search_params`.
- [ ] Add `slippage_pct` to `search_params`.
- [ ] Default `use_spread_slippage = false`.
- [ ] Default `spread_pct = 0`.
- [ ] Default `slippage_pct = 0`.
- [ ] If `use_spread_slippage` is false, keep current cost behavior.
- [ ] If true, subtract extra cost from each trade:
  - `extra_cost = spread_pct + slippage_pct`
  - `return = return - extra_cost`
- [ ] Do not double-count spread/slippage.
- [ ] Keep existing `FEE_PER_SIDE` behavior.

Optional columns:

- [ ] Add `spread_pct`.
- [ ] Add `slippage_pct`.
- [ ] Add `total_cost_pct`.

UI:

- [ ] Add checkbox: `Use spread/slippage`.
- [ ] Add input: `spread_pct`.
- [ ] Add input: `slippage_pct`.
- [ ] Disable or gray out inputs when checkbox is OFF.
- [ ] Save these options in saved run metadata.
- [ ] Restore these options when loading a saved run.

Acceptance:

- [ ] OFF gives current cost behavior.
- [ ] ON reduces total return and profit factor logically.
- [ ] Small TP strategies are affected more clearly.

---

## 5. Add ambiguous trade metrics

Backend:

- [ ] Add `ambiguous_trades` column.
- [ ] Add `ambiguous_rate` column.
- [ ] Definition: a trade is ambiguous when SL and TP are both touched inside the same candle.
- [ ] Keep current conservative behavior: SL is still prioritized before TP.
- [ ] For long:
  - ambiguous if `low <= sl_price` and `high >= tp_price`.
- [ ] For short:
  - ambiguous if `high >= sl_price` and `low <= tp_price`.
- [ ] Formula:
  - `ambiguous_rate = ambiguous_trades / trades * 100`
- [ ] Add `ambiguous_trades` to `REQUIRED_COLUMNS`.
- [ ] Add `ambiguous_rate` to `REQUIRED_COLUMNS`.
- [ ] Add both fields to `FILTER_FIELDS`.
- [ ] Return these metrics from batch engine.
- [ ] Unpack them in runner.
- [ ] Add them to normal result rows.
- [ ] Add them to dense result rows.

UI:

- [ ] Make sure `ambiguous_trades` appears in the result table.
- [ ] Make sure `ambiguous_rate` appears in the result table.
- [ ] Make sure both fields can be selected in Result Filters.
- [ ] Optional: add checkbox `Show ambiguity metrics`.

Acceptance:

- [ ] If one candle touches both SL and TP, `ambiguous_trades` increases.
- [ ] `ambiguous_rate` is calculated correctly.
- [ ] Exit behavior still prioritizes SL.

---

## 6. Update frontend config tracking

State:

- [ ] Add execution settings to frontend state:
  - `entry_next_open`
  - `use_spread_slippage`
  - `spread_pct`
  - `slippage_pct`
  - optional `show_ambiguity_metrics`

Payload:

- [ ] Update `buildSearchParams()`.
- [ ] Include `entry_mode`.
- [ ] Include `use_spread_slippage`.
- [ ] Include `spread_pct`.
- [ ] Include `slippage_pct`.

Snapshot:

- [ ] Update `snapshotCurrentConfig()`.
- [ ] Update `getConfigValue()`.
- [ ] Make dirty tracking work with new execution settings.

Saved runs:

- [ ] Save new execution settings in metadata.
- [ ] Restore new execution settings when loading a saved run.

Acceptance:

- [ ] Changing new options marks config as changed after a run.
- [ ] Loaded saved runs restore the correct execution settings.

---

## 7. Update UI layout

- [ ] Add a new section under Search Grid or near it: `Execution`.
- [ ] Add checkbox: `Entry next open`.
- [ ] Add checkbox: `Use spread/slippage`.
- [ ] Add number input: `spread_pct`.
- [ ] Add number input: `slippage_pct`.
- [ ] Keep UI simple and compact.
- [ ] Do not make the interface colorful or noisy.

Acceptance:

- [ ] User can clearly turn realistic options ON/OFF.
- [ ] Default UI state keeps current backtest behavior.

---

## 8. Tests

Backend tests:

- [ ] Test `rr = tp / sl`.
- [ ] Test `realized_rr = avg_win / abs(avg_loss)`.
- [ ] Test default `same_open` behavior.
- [ ] Test `next_open` uses next candle open.
- [ ] Test spread/slippage reduces trade return.
- [ ] Test ambiguous trade count.
- [ ] Test SL priority remains unchanged when SL and TP both hit.
- [ ] Test API returns new columns.

Frontend manual tests:

- [ ] Run backtest with all new options OFF.
- [ ] Confirm behavior is close to current result.
- [ ] Turn ON `Entry next open`.
- [ ] Confirm payload has `entry_mode = "next_open"`.
- [ ] Turn ON spread/slippage.
- [ ] Confirm payload includes spread/slippage params.
- [ ] Confirm Result Filters include:
  - `rr`
  - `realized_rr`
  - `ambiguous_trades`
  - `ambiguous_rate`

---

## Files to edit

Backend:

- [ ] `app/backtest/config.py`
- [ ] `app/backtest/batch_engine.py`
- [ ] `app/backtest/result_builder.py`
- [ ] `app/backtest/runner.py`
- [ ] `app/api/routes_options.py`
- [ ] `app/api/schemas.py` if validation is needed

Frontend:

- [ ] `frontend/index.html`
- [ ] `frontend/src/state.js`
- [ ] `frontend/src/main.js`
- [ ] `frontend/src/style.css`
- [ ] `frontend/src/table.js` if formatting or column visibility is needed

Tests:

- [ ] `tests/test_batch_engine.py`
- [ ] Add new tests if current test file becomes too large

---

## Final acceptance for Phase 1

- [ ] Existing default backtest behavior is preserved when new options are OFF.
- [ ] New result columns exist:
  - `rr`
  - `realized_rr`
  - `ambiguous_trades`
  - `ambiguous_rate`
- [ ] UI has option to enable:
  - `Entry next open`
  - `Use spread/slippage`
- [ ] User can filter by the new metrics.
- [ ] Saved runs preserve new settings.
- [ ] Tests pass.
```
