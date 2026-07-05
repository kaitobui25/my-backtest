# 2-Phase Plan: Upgrade Normal Mode into Custom Dense-Style Search

## Phase 1 — Backend: Make Normal Mode Dense-Capable

Goal:
Normal mode keeps its multi-strategy flexibility, but gains dense-style power.

Tasks:

1. Add strategy/grid metadata for UI
   - Create `app/backtest/strategy_params.py`
   - Define configurable params per strategy.
   - Start with `VOL_EXPANSION_CONT`:
     - range_mult: default `[0.8, 2.0]`
     - trend: default `["none", "ema100", "ema200"]`
     - adx_min: default `[8, 24]`
     - close_extreme: default `[0.60, 0.85]`
     - body_min: default `[0.45, 0.55]`
   - Define grid defaults:
     - sl_values
     - tp_values
     - max_holds
     - min_trades_per_day = 0.33
     - min_test_trades_per_day = 0.33

2. Update `/api/options`
   - Return:
     - `strategy_param_schemas`
     - `grid_param_schema`

3. Update signal builder
   - Change:
     `build_signal_variants(df, timeframe, mode, strategies)`
   - To:
     `build_signal_variants(df, timeframe, mode, strategies, strategy_params=None)`
   - Normal mode should read custom strategy params from `search_params.strategy_params`.
   - If no custom params are sent, use dense-style defaults for `VOL_EXPANSION_CONT`.

4. Update normal mode trade density
   - In `evaluate_normal_timeframe()`, replace fixed trade count default with:
     - `min_trades = ceil(days * min_trades_per_day)`
     - `min_test_trades = ceil(test_days * min_test_trades_per_day)`
   - Default both density values to `0.33`.
   - Keep `min_full_trades` and `min_test_trades` only as explicit overrides.

5. Update normal pre-filter
   - Replace hardcoded signal count `>= 8`.
   - Use dynamic `min_trades`.
   - Apply this before and after side-mode filtering.

6. Update normal grid default
   - Normal mode should default to dense grid:
     - `dense_grid_for_timeframe(timeframe)`
   - Support override through:
     - `sl_values`
     - `tp_values`
     - `max_holds`
   - Optional:
     - `grid_profile = "dense" | "normal"`

7. Do not change
   - Entry-aware engine
   - Same-candle SL/TP logic
   - Dense mode
   - Current result columns
   - Current result filters
   - Current score logic unless explicitly requested later


## Phase 2 — Frontend: Add Strategy Settings + Grid Settings UI

Goal:
User can select strategies like now, then edit each strategy/grid setting before running.

Tasks:

1. Update frontend state
   - Add:
     - `strategyParamSchemas`
     - `strategySettings`
     - `activeStrategy`
     - `gridSettings`
     - `densitySettings`

2. Load new options
   - From `/api/options`, store:
     - `strategy_param_schemas`
     - `grid_param_schema`

3. Split Strategies panel into 2 parts
   - Left:
     - strategy list, same as current
   - Right:
     - active strategy settings
   - Clicking a strategy should:
     - select/unselect it
     - set it as `activeStrategy`
     - render its setting form

4. First UI version should be simple
   - Use min/max number inputs for ranges.
   - Use checkboxes for multi-select.
   - Use dropdown only when needed.
   - Do not build double sliders yet.

5. Split Filters panel into 2 parts
   - Top:
     - current result filters
   - Bottom:
     - search grid settings:
       - SL values
       - TP values
       - max_hold values
       - min_trades_per_day
       - min_test_trades_per_day

6. Use CSV inputs first for grid values
   - Example:
     - SL: `0.02,0.03,0.04,0.06,0.08`
     - TP: `0.005,0.0075,0.01,0.015,0.02,0.03`
     - Max hold: `16,32,64,96`

7. Send `search_params` in backtest payload
   - Add:
     - `grid_profile`
     - `sl_values`
     - `tp_values`
     - `max_holds`
     - `min_trades_per_day`
     - `min_test_trades_per_day`
     - `strategy_params`

8. Saved runs
   - Save full payload including `search_params`.
   - When loading saved run, restore:
     - selected strategies
     - strategy settings
     - grid settings
     - density settings

9. Test
   - Run normal mode with `VOL_EXPANSION_CONT`.
   - Confirm custom params affect result count.
   - Confirm normal uses dense-style grid by default.
   - Confirm normal uses dynamic trades/day filtering.
   - Confirm saved run restores the full setup.

Suggested commit message:
`Upgrade normal mode with dense-style custom search settings`
