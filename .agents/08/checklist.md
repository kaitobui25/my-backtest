```text
UI BACKTEST CONFIG PROTECTION CHECKLIST

[ ] 1. Update top layout to 5 columns

[ ] frontend/index.html
    [ ] Keep column 1 as Timeframes.
    [ ] Keep column 2 as Strategies + Strategy Settings.
    [ ] Keep column 3 as Selected Setup.
    [ ] Move Execution from column 4 into column 3.
    [ ] Move Risk / Leverage from column 4 into column 3.
    [ ] Keep column 4 for Result Filters + Search Grid only.
    [ ] Add column 5 panel.
    [ ] Set column 5 title to Active Backtest Config.
    [ ] Add read-only body element: running-config-view.

[ ] frontend/src/style.css
    [ ] Change #top-bar from 4 columns to 5 columns.
    [ ] Example:
        grid-template-columns: 120px 2fr 1.6fr 1.8fr 1.8fr;
    [ ] Add compact styling for the Active Backtest Config panel.
    [ ] Add readable style for JSON/pre blocks.
    [ ] Allow long config text to wrap or scroll.
    [ ] Make the panel look read-only.

[ ] 2. Lock settings while backtest is running

[ ] frontend/src/main.js
    [ ] Add helper:
        function isConfigLocked() {
          return state.loading;
        }

[ ] renderSearchGrid()
    [ ] Disable Profile select while state.loading is true.
    [ ] Disable SL values input while state.loading is true.
    [ ] Disable TP values input while state.loading is true.
    [ ] Disable Max Hold input while state.loading is true.
    [ ] Disable Min trades/day input while state.loading is true.
    [ ] Disable Min test trades/day input while state.loading is true.

[ ] renderExecutionSettings()
    [ ] Disable Entry next open checkbox while state.loading is true.
    [ ] Disable Use spread/slippage checkbox while state.loading is true.
    [ ] Disable Spread % input while state.loading is true.
    [ ] Disable Slippage % input while state.loading is true.

[ ] renderRiskSettings()
    [ ] Disable Position sizing checkbox while state.loading is true.
    [ ] Disable Risk % per trade input while state.loading is true.
    [ ] Disable Use leverage checkbox while state.loading is true.
    [ ] Disable Leverage input while state.loading is true.
    [ ] Disable Liquidation checkbox while state.loading is true.
    [ ] Disable Maint. margin % input while state.loading is true.

[ ] Event guards
    [ ] In search-grid change handler, add:
        if (state.loading) return;
    [ ] In search-grid input handler, add:
        if (state.loading) return;
    [ ] In execution-settings change handler, add:
        if (state.loading) return;
    [ ] In execution-settings input handler, add:
        if (state.loading) return;
    [ ] In risk-settings change handler, add:
        if (state.loading) return;
    [ ] In risk-settings input handler, add:
        if (state.loading) return;

[ ] 3. Add real backtest config snapshot

[ ] frontend/src/state.js
    [ ] Add new state field:
        runningConfigSnapshot: null,

[ ] Snapshot rule
    [ ] The Active Backtest Config panel must read only from runningConfigSnapshot.
    [ ] It must not read directly from selectedTimeframes.
    [ ] It must not read directly from selectedStrategies.
    [ ] It must not read directly from filters.
    [ ] It must not read directly from gridSettings.
    [ ] It must not read directly from executionSettings.
    [ ] It must not read directly from riskSettings.

[ ] 4. Update handleRun()

[ ] frontend/src/main.js
    [ ] Build filters as usual.
    [ ] Build payload as usual.
    [ ] Copy selectedTimeframes with [...state.selectedTimeframes].
    [ ] Copy selectedStrategies with [...state.selectedStrategies].
    [ ] Keep payload format compatible with current API.
    [ ] Store exact run payload into runningConfigSnapshot before calling API.
    [ ] Use structuredClone(payload) if available.
    [ ] Call renderRunningConfig() immediately after setting the snapshot.
    [ ] Then call runBacktestAPI(payload, controller.signal).

[ ] Example logic
    [ ] Use this structure:

        const payload = {
          symbol: "BTCUSD",
          timeframes: [...state.selectedTimeframes],
          mode: state.mode,
          strategies: state.selectedStrategies.length > 0 ? [...state.selectedStrategies] : null,
          filters,
          limit: 500,
          search_params: buildSearchParams(),
        };

        state.runningConfigSnapshot = structuredClone(payload);
        renderRunningConfig();

        const result = await runBacktestAPI(payload, controller.signal);

[ ] 5. Render Active Backtest Config panel

[ ] frontend/src/main.js
    [ ] Add function:
        renderRunningConfig()

[ ] renderRunningConfig()
    [ ] If runningConfigSnapshot is null, show:
        No active backtest config yet
    [ ] Show Symbol.
    [ ] Show Mode.
    [ ] Show Timeframes.
    [ ] Show Strategies.
    [ ] Show Result Filters.
    [ ] Show Search Grid values.
    [ ] Show Execution values.
    [ ] Show Risk / Leverage values.
    [ ] Keep it read-only.
    [ ] Keep it compact.

[ ] Search Grid values to show
    [ ] grid_profile
    [ ] sl_values
    [ ] tp_values
    [ ] max_holds
    [ ] min_trades_per_day
    [ ] min_test_trades_per_day

[ ] Execution values to show
    [ ] entry_mode
    [ ] use_spread_slippage
    [ ] spread_pct
    [ ] slippage_pct

[ ] Risk / Leverage values to show
    [ ] use_position_sizing
    [ ] risk_per_trade_pct
    [ ] use_leverage
    [ ] leverage
    [ ] use_liquidation
    [ ] maintenance_margin_pct

[ ] Call renderRunningConfig()
    [ ] Inside renderAll().
    [ ] Inside handleRun() after setting runningConfigSnapshot.
    [ ] Inside handleLoadSavedRun() if saved run metadata should be displayed.

[ ] 6. Save/load compatibility

[ ] Save run
    [ ] Keep lastRunPayload behavior unchanged.
    [ ] Keep metadata.search_params behavior unchanged.
    [ ] Do not change API payload format.
    [ ] Do not break existing saved run format.

[ ] Load saved run
    [ ] If saved run has metadata, optionally rebuild runningConfigSnapshot from metadata.
    [ ] If metadata is incomplete, keep panel fallback safe.
    [ ] Do not crash when older saved runs do not have full config data.

[ ] 7. Manual tests

[ ] Layout tests
    [ ] UI shows 5 columns.
    [ ] Execution appears in column 3.
    [ ] Risk / Leverage appears in column 3.
    [ ] Column 4 only contains Result Filters and Search Grid.
    [ ] Column 5 shows Active Backtest Config.

[ ] Running lock tests
    [ ] Start a backtest.
    [ ] Search Grid cannot be edited while running.
    [ ] Execution cannot be edited while running.
    [ ] Risk / Leverage cannot be edited while running.
    [ ] Run button still shows Running...
    [ ] Save button remains disabled while running.

[ ] Snapshot tests
    [ ] Click Run.
    [ ] Column 5 shows the exact config used by that run.
    [ ] After run finishes, change Timeframes.
    [ ] Column 5 does not change.
    [ ] Change Strategies.
    [ ] Column 5 does not change.
    [ ] Change Result Filters.
    [ ] Column 5 does not change.
    [ ] Change Search Grid.
    [ ] Column 5 does not change.
    [ ] Change Execution.
    [ ] Column 5 does not change.
    [ ] Change Risk / Leverage.
    [ ] Column 5 does not change.
    [ ] Click Run again.
    [ ] Column 5 updates to the new config.

[ ] Regression tests
    [ ] Normal mode still runs.
    [ ] Dense High WR mode still runs.
    [ ] Empty selectedStrategies still means all strategies.
    [ ] Filters still apply correctly.
    [ ] Search Grid values still reach the backend correctly.
    [ ] Execution values still reach the backend correctly.
    [ ] Risk / Leverage values still reach the backend correctly.
    [ ] Save run still works.
    [ ] Load saved run still works.
```
