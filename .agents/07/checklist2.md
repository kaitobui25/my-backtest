# Phase 2 Checklist — Risk, Equity, Leverage, Liquidation, and UI Clarity

## Goal

- [ ] Add optional position sizing.
- [ ] Add optional equity-based metrics.
- [ ] Add optional leverage/liquidation simulation.
- [ ] Improve Result Filters UX with favorite fields.
- [ ] Improve UI clarity so user knows whether filters/grid are already applied.
- [ ] Keep current behavior unchanged when all Phase 2 options are OFF.

---

## 1. Position sizing settings

Backend:

- [ ] Add `use_position_sizing` to `search_params`.
- [ ] Add `risk_per_trade_pct` to `search_params`.
- [ ] Default `use_position_sizing = false`.
- [ ] Default `risk_per_trade_pct = 1.0`.
- [ ] If OFF, keep current return calculation unchanged.
- [ ] If ON, calculate trade result based on equity risk.
- [ ] Use `risk_per_trade_pct` to size each trade.
- [ ] Add validation:
  - `risk_per_trade_pct > 0`
  - reject or clamp unreasonable values.

Frontend:

- [ ] Add checkbox: `Use position sizing`.
- [ ] Add input: `Risk per trade %`.
- [ ] Disable risk input when checkbox is OFF.
- [ ] Save setting in `search_params`.
- [ ] Restore setting when loading saved run.

Acceptance:

- [ ] OFF keeps current behavior.
- [ ] ON changes equity-based metrics only.
- [ ] Saved runs restore position sizing settings.

---

## 2. Equity summary metrics

Backend:

- [ ] Add `equity_total_return` column.
- [ ] Add `equity_max_drawdown` column.
- [ ] Add `final_equity` column if useful.
- [ ] Add `start_equity` setting if needed.
- [ ] Default `start_equity = 1000` or use internal normalized equity.
- [ ] Equity should update trade by trade.
- [ ] Max drawdown should be calculated from equity curve.
- [ ] Do not generate full equity curve for every config in batch.
- [ ] Only return summary metrics in Phase 2.

Frontend:

- [ ] Show `equity_total_return`.
- [ ] Show `equity_max_drawdown`.
- [ ] Optionally show `final_equity`.
- [ ] Add these fields to Result Filters.

Acceptance:

- [ ] API returns equity summary metrics.
- [ ] User can filter by equity metrics.
- [ ] Batch performance does not become too slow.

---

## 3. Leverage settings

Backend:

- [ ] Add `use_leverage` to `search_params`.
- [ ] Add `leverage` to `search_params`.
- [ ] Default `use_leverage = false`.
- [ ] Default `leverage = 1`.
- [ ] If OFF, keep current behavior.
- [ ] If ON, apply leverage to trade return/risk model.
- [ ] Add validation:
  - `leverage >= 1`
  - reject or clamp unreasonable leverage.

Frontend:

- [ ] Add checkbox: `Use leverage`.
- [ ] Add input: `Leverage`.
- [ ] Disable leverage input when checkbox is OFF.
- [ ] Save setting in `search_params`.
- [ ] Restore setting when loading saved run.

Acceptance:

- [ ] OFF keeps current behavior.
- [ ] ON affects leveraged/equity metrics.
- [ ] Saved runs restore leverage settings.

---

## 4. Liquidation simulation

Backend:

- [ ] Add `use_liquidation` to `search_params`.
- [ ] Add `maintenance_margin_pct` to `search_params`.
- [ ] Default `use_liquidation = false`.
- [ ] Default `maintenance_margin_pct = 0.5` or another safe default.
- [ ] If OFF, do not check liquidation.
- [ ] If ON, check whether candle high/low reaches liquidation price.
- [ ] Long liquidation:
  - liquidation happens when price drops below liquidation price.
- [ ] Short liquidation:
  - liquidation happens when price rises above liquidation price.
- [ ] If liquidation and TP/SL happen in the same candle, use conservative priority:
  - liquidation first
  - then SL
  - then TP
- [ ] Add `liquidated_trades` column.
- [ ] Add `liquidation_rate` column.
- [ ] Add `liquidation_rate = liquidated_trades / trades * 100`.

Frontend:

- [ ] Add checkbox: `Use liquidation`.
- [ ] Add input: `Maintenance margin %`.
- [ ] Disable input when checkbox is OFF.
- [ ] Show `liquidated_trades`.
- [ ] Show `liquidation_rate`.
- [ ] Add liquidation fields to Result Filters.

Acceptance:

- [ ] OFF keeps current behavior.
- [ ] ON counts liquidated trades.
- [ ] User can filter `liquidation_rate <= x`.

---

## 5. Backend columns and filters

Update:

- [ ] `app/backtest/config.py`
- [ ] `app/backtest/result_builder.py`
- [ ] `app/api/routes_options.py`

Add columns if implemented:

- [ ] `equity_total_return`
- [ ] `equity_max_drawdown`
- [ ] `final_equity`
- [ ] `liquidated_trades`
- [ ] `liquidation_rate`

Add to Result Filters:

- [ ] `equity_total_return`
- [ ] `equity_max_drawdown`
- [ ] `final_equity`
- [ ] `liquidated_trades`
- [ ] `liquidation_rate`

Acceptance:

- [ ] New columns appear in API result.
- [ ] New columns can be filtered.
- [ ] Existing filters still work.

---

## 6. Result Filters favorite fields

Frontend:

- [ ] Add star button next to filter field options.
- [ ] Use `☆` for normal field.
- [ ] Use `★` for favorite field.
- [ ] Store favorite fields in `localStorage`.
- [ ] Put favorite fields at the top of dropdown.
- [ ] Keep non-favorite fields below.
- [ ] Do not break existing filter add/remove logic.

Acceptance:

- [ ] User can favorite a filter field.
- [ ] Favorite fields stay after page reload.
- [ ] Favorite fields appear at the top.

---

## 7. Applied vs changed UI status

Problem:

- [ ] Current UI makes it unclear whether Result Filters and Search Grid were already applied to current results.

Frontend:

- [ ] After successful Run Backtest, show status:
  - `Applied to current results`
- [ ] If user changes Result Filters after run, show:
  - `Changed after run — click Run Backtest to apply`
- [ ] If user changes Search Grid after run, show:
  - `Changed after run — click Run Backtest to apply`
- [ ] Reuse current dirty tracking if possible.
- [ ] Add text badge, not only color.
- [ ] Keep UI compact and not colorful.

Acceptance:

- [ ] After run, user knows filters/grid are applied.
- [ ] After changing settings, user knows results are stale.
- [ ] No confusion that changed filters already affected current table.

---

## 8. Saved run support

Frontend/backend:

- [ ] Save Phase 2 settings in run metadata via `search_params`.
- [ ] Restore Phase 2 settings when loading saved run.

Settings to preserve:

- [ ] `use_position_sizing`
- [ ] `risk_per_trade_pct`
- [ ] `use_leverage`
- [ ] `leverage`
- [ ] `use_liquidation`
- [ ] `maintenance_margin_pct`

Acceptance:

- [ ] Save run.
- [ ] Reload page.
- [ ] Load saved run.
- [ ] All Phase 2 settings are restored correctly.

---

## 9. Tests

Backend tests:

- [ ] Default OFF behavior remains unchanged.
- [ ] Position sizing changes equity metrics.
- [ ] Equity max drawdown is calculated correctly.
- [ ] Leverage affects leveraged/equity metrics.
- [ ] Liquidation count increases when candle reaches liquidation price.
- [ ] Liquidation has conservative priority.
- [ ] API returns new Phase 2 columns.
- [ ] New fields can be used in filters.

Frontend manual tests:

- [ ] Toggle position sizing ON/OFF.
- [ ] Toggle leverage ON/OFF.
- [ ] Toggle liquidation ON/OFF.
- [ ] Save and load run.
- [ ] Favorite filter fields.
- [ ] Reload page and confirm favorites remain.
- [ ] Change filters after run and confirm stale/applied badge works.
- [ ] Change search grid after run and confirm stale/applied badge works.

---

## Files likely to edit

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
- [ ] `frontend/src/table.js` if needed

Tests:

- [ ] `tests/test_batch_engine.py`
- [ ] Add new test file if needed

---

## Final acceptance for Phase 2

- [ ] Phase 1 still works.
- [ ] Current behavior is preserved when Phase 2 options are OFF.
- [ ] Position sizing can be enabled from UI.
- [ ] Equity summary metrics are returned.
- [ ] Leverage can be enabled from UI.
- [ ] Liquidation can be enabled from UI.
- [ ] Liquidation metrics are returned.
- [ ] New metrics can be used in Result Filters.
- [ ] Filter field favorites work.
- [ ] Applied/changed UI status is clear.
- [ ] Saved runs preserve Phase 2 settings.
- [ ] Tests pass.
