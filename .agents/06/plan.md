PHASE 1 — Frontend UX + State Fixes

Goal:
Fix the current UI behavior first so the app feels correct before expanding backend strategy settings.

Files:
- frontend/src/state.js
- frontend/src/main.js
- frontend/src/style.css

1. Strategy click behavior

Current problem:
- Single click on a strategy currently toggles add/remove and also opens settings.
- This makes it impossible to only inspect/edit settings.

Required behavior:
- Single click on a strategy:
  - Set it as active strategy.
  - Show its settings panel.
  - Do NOT add it to selected strategies.
- Double click on a strategy:
  - Add/remove it from selected strategies.
  - Keep it active so its settings remain visible.

Implementation:
- Split current `toggleStrategy(s)` into:
  - `activateStrategy(s)`
  - `toggleSelectedStrategy(s)`
- Bind:
  - `click` on `#strategy-list` => `activateStrategy`
  - `dblclick` on `#strategy-list` => `toggleSelectedStrategy`
- Add separate visual styles:
  - `.item.active` = strategy currently opened in settings panel
  - `.item.selected` = strategy included in setup/backtest

Acceptance:
- Clicking `VOL_EXPANSION_CONT` only opens settings.
- Double-clicking `VOL_EXPANSION_CONT` adds it to selected setup.
- Clicking another strategy changes the settings panel without changing selected strategies.
- Removing a selected strategy from the selected list still works.

2. Search Grid default values

Current problem:
- `SL values`, `TP values`, and `Max Hold` are empty on initial load.
- `state.gridSettings` starts with empty strings even though backend has defaults.

Required behavior:
- On first page load, Search Grid inputs must be pre-filled with default values.
- Defaults should come from `/api/options -> grid_param_schema`.
- If no backend default exists, fallback to safe hardcoded values.

Implementation:
- Add helper:
  - `formatCsvDefault(value)`
  - `applyGridDefaults(overwrite = false)`
- After `fetchOptions()`:
  - Save `state.gridParamSchema`.
  - Call `applyGridDefaults(true)`.
- Render Search Grid using initialized state, not empty strings.

Acceptance:
- After opening frontend, these fields are not blank:
  - SL values
  - TP values
  - Max Hold
- Running backtest without touching Search Grid sends default grid values correctly.

3. Search Grid Profile switching

Current problem:
- Changing Profile between `dense` and `normal` only changes `state.gridSettings.profile`.
- The input fields do not update.

Required behavior:
- Changing Profile updates:
  - SL values
  - TP values
  - Max Hold
- User can still manually edit after profile is applied.

Implementation:
- Add profile defaults to frontend from backend schema if available.
- On `grid-profile` change:
  - Set `state.gridSettings.profile`.
  - Apply profile defaults with overwrite.
  - Re-render Search Grid.
- Prefer using the first selected timeframe to choose timeframe-specific defaults.
- If no timeframe is selected, use a common/default profile grid.

Acceptance:
- Switching Dense -> Normal changes grid inputs.
- Switching Normal -> Dense changes them back.
- Manual edits still stay until the user changes profile again.

4. Highlight changed controls after run / while running

Current problem:
- After a result exists, changing setup parameters does not visually warn the user.
- User may think current table matches current settings, but it does not.

Required behavior:
- If a backtest is running OR current result exists and is not saved, then any changed setup control gets light pink background.
- Affected controls include:
  - timeframes
  - selected strategies
  - mode
  - filters
  - Search Grid fields
  - strategy setting fields

Implementation:
- Add state:
  - `lastRunConfigSnapshot`
  - `changedConfigKeys`
  - optionally separate `resultDirty` from config dirty
- After successful run:
  - Store `lastRunConfigSnapshot = snapshotCurrentConfig()`
  - Clear `changedConfigKeys`
- When user changes any setup field:
  - Compare with snapshot.
  - Mark changed field key if different.
  - Add `.config-dirty` class to related control.
- After Save:
  - Clear visual dirty indicators if result is saved.
- Add CSS:
  - `.config-dirty { background: #ffe6ea !important; border-color: #f3a6b3 !important; }`

Acceptance:
- Run backtest, then change SL values => SL input becomes light pink.
- Run backtest, then change timeframe => changed timeframe item/selected area becomes light pink.
- Save result => dirty indicator clears.
- While running, changing a control marks it pink.


PHASE 2 — Backend Strategy Settings + VOL_EXPANSION_CONT Auto Trend

Goal:
Make strategy settings real for all strategies, not only visible in UI. Any setting changed in frontend must actually affect generated signals and backtest results.

Files:
- app/backtest/strategy_params.py
- app/backtest/signals.py
- app/api/routes_options.py
- app/backtest/runner.py
- tests/

1. Add parameter schemas for all strategies

Current problem:
- Only `VOL_EXPANSION_CONT` has settings schema.
- Other strategies appear in the list but have no editable settings.

Required strategies:
- EMA_PULLBACK
- DONCHIAN_BREAKOUT
- BB_RSI_REVERT
- IBS_REVERT
- VOL_EXPANSION_CONT
- SUPERTREND
- MACD_CROSS
- WAVETREND
- SQUEEZE_MOM
- WILLIAMS_VIX_FIX

Implementation:
- Expand `STRATEGY_PARAM_SCHEMAS`.
- Each schema must match current hardcoded loops in `signals.py`.
- Supported field types:
  - `range`
  - `select`
  - optional `boolean`
- Add defaults that reproduce current behavior as closely as possible.

Example direction:
- EMA_PULLBACK:
  - fast: 34, 50
  - trend: ema200
  - rsi_lo: 40..45
  - rsi_hi: 55..60
  - adx_min: 12..18
  - atr_mult: 0.60..0.90
  - vol: false
- DONCHIAN_BREAKOUT:
  - window: 40, 80
  - trend: ema200
  - adx_min: 18, 24
  - vol: false
- BB_RSI_REVERT:
  - window: 20, 40
  - z: 2.0, 2.4
  - rsi_lo: 25, 30
  - rsi_hi: 70, 75
  - trend_mode: trend, range
  - adx_max: none, 24
- IBS_REVERT:
  - ibs_lo: 0.05, 0.10, 0.20
  - ibs_hi: 0.80, 0.90, 0.95
  - trend_mode: trend, range
  - adx_max: none, 24
- SUPERTREND:
  - period: 10, 14, 20
  - mult: 2.0, 3.0, 4.0
  - trend: none, ema200
- MACD_CROSS:
  - macd preset: 8/21/5, 12/26/9, 5/34/5
  - trend: none, ema200
  - adx_min: 12, 18
- WAVETREND:
  - wt preset: 10/21, 10/11, 14/21
  - ob_os: 53/-53, 60/-60
  - trend_mode: trend, range
- SQUEEZE_MOM:
  - length: 20, 30
  - bb_mult: 2.0
  - kc_mult: 1.5, 2.0
  - trend: none, ema200
- WILLIAMS_VIX_FIX:
  - pd_len: 22, 30
  - bbl: 20
  - ph: 0.85, 0.90
  - trend_mode: trend, range

Acceptance:
- `/api/options` returns settings schema for all strategies.
- Frontend can open settings for every strategy.
- No strategy shows “Click a strategy to edit” when it has a valid schema.

2. Make `signals.py` consume strategy params for every strategy

Current problem:
- UI settings would be fake unless `build_signals()` actually uses them.
- Currently only `VOL_EXPANSION_CONT` reads `strategy_params`.

Required behavior:
- Every strategy block reads user-defined params from `strategy_params`.
- If no user params are provided, defaults reproduce current behavior.

Implementation:
- Add helpers:
  - `_schema_defaults(strategy_name)`
  - `_params_for(strategy_name, strategy_params)`
  - `_expand_range(value, step)`
  - `_expand_select(value)`
  - `_expand_optional_number(value)`
- Replace hardcoded product lists inside each strategy block with expanded params.
- Keep output param strings explicit and readable.

Acceptance:
- Changing `BB_RSI_REVERT.window` changes generated params.
- Changing `MACD_CROSS.adx_min` changes generated params.
- Selecting only one option in UI reduces signal variants.
- Running old/default config produces roughly same behavior as before.

3. Add `auto` option for VOL_EXPANSION_CONT trend

Current problem:
- VOL_EXPANSION_CONT trend currently only supports fixed choices such as none/ema100/ema200.
- User wants `auto` so the strategy searches multiple trend filters automatically.

Required behavior:
- `trend` options:
  - auto
  - none
  - ema20
  - ema50
  - ema100
  - ema200
  - ema300
- If `auto` is selected:
  - Backend expands it to:
    - none
    - ema20
    - ema50
    - ema100
    - ema200
    - ema300

Implementation:
- Update `STRATEGY_PARAM_SCHEMAS["VOL_EXPANSION_CONT"]["trend"]`.
- Update normal VOL builder in `build_signals()`.
- Update dense VOL builder too.
- Use existing EMA series already calculated:
  - ema20
  - ema50
  - ema100
  - ema200
  - ema300

Acceptance:
- Selecting trend `auto` generates params containing multiple trend variants.
- Result table can show:
  - trend=none
  - trend=ema20
  - trend=ema50
  - trend=ema100
  - trend=ema200
  - trend=ema300
- Selecting only `ema200` runs only ema200.

4. Dense mode behavior for non-VOL strategies

Current problem:
- Dense mode currently only has a dense builder for `VOL_EXPANSION_CONT`.
- If user selects another strategy in dense mode, backend may return empty results without clear reason.

Required behavior:
- Either support dense mode for more strategies, or clearly communicate unsupported strategies.
- Best minimal fix:
  - Dense mode uses VOL_EXPANSION_CONT only for now.
  - If selected strategies contain unsupported dense strategies, backend ignores them but returns warning metadata.
- Better fix:
  - Allow dense mode to reuse normal signal builders but apply dense filters/grid.

Recommended approach:
- For Phase 2, implement better fix if not too risky:
  - Dense mode should call `build_signal_variants(..., mode="normal", strategy_params=...)`
  - Then apply dense filters/scoring.
  - Keep specialized VOL dense builder only if it is materially different.
- If this is too large, keep VOL-only dense but add explicit warning.

Acceptance:
- Dense mode with `VOL_EXPANSION_CONT` still works.
- Dense mode with `IBS_REVERT` does not silently fail.
- User can understand whether dense supports the selected strategy.

5. Tests

Add tests:
- `test_options_contains_all_strategy_schemas`
- `test_grid_schema_has_defaults`
- `test_vol_auto_expands_trends`
- `test_strategy_param_override_changes_signal_params`
- `test_dense_mode_selected_non_vol_strategy_has_clear_behavior`

Final acceptance for both phases:
- Single click strategy opens settings.
- Double click strategy adds/removes it from setup.
- Every strategy has settings.
- Search Grid loads with default SL/TP/Max Hold.
- Profile switching updates grid inputs.
- Changed setup controls are highlighted pink after a run / while running.
- VOL_EXPANSION_CONT supports trend auto.
- Strategy settings actually affect backend signal generation, not only UI.
