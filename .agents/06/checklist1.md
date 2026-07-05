PHASE 1 CHECKLIST — Frontend UX + State Fixes

Files:
[ ] frontend/src/state.js
[ ] frontend/src/main.js
[ ] frontend/src/style.css

Goal:
[ ] Fix strategy click behavior.
[ ] Fill Search Grid defaults automatically.
[ ] Make Search Grid Profile actually update values.
[ ] Highlight changed setup controls after running / while running.

============================================================
1. Strategy click vs double-click
============================================================

Current problem:
[ ] Single click currently opens settings AND adds/removes the strategy.
[ ] This is wrong because user cannot only inspect/edit strategy settings.

Required behavior:
[ ] Single click on a strategy opens its settings only.
[ ] Single click must NOT add/remove the strategy from selected setup.
[ ] Double click on a strategy adds/removes it from selected setup.
[ ] Double click should also keep that strategy active in the settings panel.

Implementation checklist:
[ ] In frontend/src/main.js, replace current toggleStrategy behavior.
[ ] Create function activateStrategy(strategyName).
[ ] Create function toggleSelectedStrategy(strategyName).
[ ] activateStrategy(strategyName) should:
    [ ] Set state.activeStrategy = strategyName.
    [ ] Initialize default settings for that strategy if missing.
    [ ] Re-render strategy list.
    [ ] Re-render strategy settings panel.
[ ] toggleSelectedStrategy(strategyName) should:
    [ ] Add strategy if not selected.
    [ ] Remove strategy if already selected.
    [ ] Keep state.activeStrategy = strategyName.
    [ ] Initialize settings if missing.
    [ ] Re-render strategy list.
    [ ] Re-render selected setup.
    [ ] Update Run button state.
[ ] Change #strategy-list click event:
    [ ] click => activateStrategy(strategyName)
[ ] Add #strategy-list double-click event:
    [ ] dblclick => toggleSelectedStrategy(strategyName)
[ ] Update selected strategies placeholder text:
    [ ] From "Click strategies to add"
    [ ] To "Double-click strategies to add"

UI checklist:
[ ] Add active class for the strategy being edited.
[ ] Keep selected class for strategies included in setup.
[ ] Active and selected should be visually different.
[ ] A strategy can be active but not selected.
[ ] A strategy can be selected and active at the same time.

CSS checklist:
[ ] Add .item.active style.
[ ] Keep .item.selected style.
[ ] Make sure .item.active.selected still looks understandable.

Acceptance test:
[ ] Click VOL_EXPANSION_CONT once.
    [ ] Settings panel opens.
    [ ] VOL_EXPANSION_CONT is NOT added to selected setup.
[ ] Double-click VOL_EXPANSION_CONT.
    [ ] VOL_EXPANSION_CONT is added to selected setup.
    [ ] Settings panel remains visible.
[ ] Click EMA_PULLBACK once.
    [ ] Settings panel changes to EMA_PULLBACK.
    [ ] Selected setup does not change.
[ ] Double-click EMA_PULLBACK.
    [ ] EMA_PULLBACK is added to selected setup.
[ ] Double-click EMA_PULLBACK again.
    [ ] EMA_PULLBACK is removed from selected setup.

============================================================
2. Search Grid default values
============================================================

Current problem:
[ ] SL values input is blank on first load.
[ ] TP values input is blank on first load.
[ ] Max Hold input is blank on first load.
[ ] Backend already has grid defaults, but frontend does not apply them.

Required behavior:
[ ] Search Grid fields must be filled automatically after /api/options loads.
[ ] Defaults should come from state.gridParamSchema.
[ ] If backend schema is missing, frontend should still use safe fallback defaults.

Implementation checklist:
[ ] In frontend/src/state.js, keep gridSettings but do not rely on empty strings forever.
[ ] Add helper function formatCsvDefault(value).
[ ] Add helper function getGridDefaults(profile).
[ ] Add helper function applyGridDefaults(overwrite).
[ ] In init(), after:
    [ ] state.gridParamSchema = opts.grid_param_schema || {};
[ ] Call:
    [ ] applyGridDefaults(true)
[ ] Then call renderAll().
[ ] Make sure renderSearchGrid() receives filled values.

Fallback default checklist:
[ ] Dense fallback SL:
    [ ] 0.02, 0.03, 0.04, 0.06, 0.08
[ ] Dense fallback TP:
    [ ] 0.005, 0.0075, 0.01, 0.015, 0.02, 0.03
[ ] Dense fallback Max Hold:
    [ ] 16, 32, 64, 96
[ ] Normal fallback SL:
    [ ] 0.01, 0.02, 0.04, 0.06
[ ] Normal fallback TP:
    [ ] 0.005, 0.01, 0.02, 0.03
[ ] Normal fallback Max Hold:
    [ ] 48, 96, 0

Acceptance test:
[ ] Open frontend.
[ ] Check Search Grid.
[ ] SL values is not blank.
[ ] TP values is not blank.
[ ] Max Hold is not blank.
[ ] Run backtest without editing Search Grid.
[ ] Payload contains sl_values.
[ ] Payload contains tp_values.
[ ] Payload contains max_holds.

============================================================
3. Search Grid Profile switching
============================================================

Current problem:
[ ] Changing Profile only updates state.gridSettings.profile.
[ ] It does not update SL values.
[ ] It does not update TP values.
[ ] It does not update Max Hold.

Required behavior:
[ ] Changing Profile to Dense updates grid fields to dense defaults.
[ ] Changing Profile to Normal updates grid fields to normal defaults.
[ ] User can manually edit values after profile is applied.
[ ] If user changes profile again, profile defaults overwrite the previous grid fields.

Implementation checklist:
[ ] Update #search-grid change event.
[ ] When target.id === "grid-profile":
    [ ] Set state.gridSettings.profile = target.value.
    [ ] Call applyGridDefaults(true).
    [ ] Re-render Search Grid.
    [ ] Mark grid profile as changed if dirty tracking is active.
[ ] Use selected timeframe when possible for timeframe-specific defaults.
[ ] If multiple timeframes are selected, use the first selected timeframe.
[ ] If no timeframe is selected, use common fallback defaults.
[ ] Changing timeframe should optionally refresh profile defaults only if user has not manually edited grid values.

Acceptance test:
[ ] Open frontend.
[ ] Profile is Dense by default.
[ ] Dense grid values are visible.
[ ] Change Profile to Normal.
[ ] SL values change.
[ ] TP values change.
[ ] Max Hold changes.
[ ] Change Profile back to Dense.
[ ] Dense values come back.
[ ] Manually edit SL values.
[ ] SL values stay edited until Profile is changed again.

============================================================
4. Highlight changed setup controls after run / while running
============================================================

Current problem:
[ ] User can run backtest and get results.
[ ] Then user can change settings.
[ ] Table still shows old result, but UI does not warn clearly which setting changed.

Required behavior:
[ ] While backtest is running, changed setup controls become light pink.
[ ] After backtest result exists but is not saved, changed setup controls become light pink.
[ ] After saving result, dirty highlight clears.
[ ] After running again, dirty highlight clears and new snapshot is stored.

Controls to track:
[ ] Timeframes.
[ ] Selected strategies.
[ ] Mode.
[ ] Filters.
[ ] Search Grid Profile.
[ ] Search Grid SL values.
[ ] Search Grid TP values.
[ ] Search Grid Max Hold.
[ ] Search Grid min_trades_per_day.
[ ] Search Grid min_test_trades_per_day.
[ ] Strategy setting range min/max.
[ ] Strategy setting checkbox/select values.

State checklist:
[ ] In frontend/src/state.js, add:
    [ ] lastRunConfigSnapshot: null
    [ ] changedConfigKeys: []
[ ] Do not use Set directly if saved/loaded JSON may touch it.
[ ] Use array or plain object for easier rendering.

Helper checklist:
[ ] Add snapshotCurrentConfig().
[ ] Add hasTrackableResult().
[ ] Add markConfigChanged(key).
[ ] Add clearConfigChanged().
[ ] Add isConfigChanged(key).
[ ] Add normalizeConfigForCompare(config).
[ ] After successful run:
    [ ] state.lastRunConfigSnapshot = snapshotCurrentConfig()
    [ ] clearConfigChanged()
[ ] After save:
    [ ] clearConfigChanged()
[ ] After loading saved run:
    [ ] clearConfigChanged()
    [ ] state.lastRunConfigSnapshot = snapshotCurrentConfig()

Dirty tracking rules:
[ ] If state.loading is true:
    [ ] Mark changed controls.
[ ] If table rows exist and current result is not saved:
    [ ] Mark changed controls.
[ ] If no result exists and not running:
    [ ] Do not show pink highlight.
[ ] If result is already saved:
    [ ] Do not keep pink highlight after save.

CSS checklist:
[ ] Add:
    [ ] .config-dirty
[ ] Use light pink background:
    [ ] background: #ffe6ea !important;
[ ] Use soft pink border:
    [ ] border-color: #f3a6b3 !important;
[ ] Make sure inputs, selects, strategy items, timeframe items can receive this class.

Render checklist:
[ ] renderTimeframes() should add config-dirty class when timeframe selection changed.
[ ] renderStrategies() should add config-dirty class when selected strategies changed.
[ ] renderFilters() should add config-dirty class when filters changed.
[ ] renderSearchGrid() should add config-dirty class per changed grid field.
[ ] renderStrategySettings() should add config-dirty class per changed strategy setting.
[ ] Mode radio buttons should get config-dirty indication when mode changed.

Acceptance test:
[ ] Run backtest.
[ ] Change SL values.
    [ ] SL input becomes light pink.
[ ] Change TP values.
    [ ] TP input becomes light pink.
[ ] Change Max Hold.
    [ ] Max Hold input becomes light pink.
[ ] Change Profile.
    [ ] Profile select becomes light pink.
    [ ] Grid values update.
[ ] Change timeframe.
    [ ] Timeframe area/item becomes light pink.
[ ] Change selected strategy.
    [ ] Strategy area/item becomes light pink.
[ ] Change strategy setting.
    [ ] Changed setting becomes light pink.
[ ] Click Save.
    [ ] Pink highlights disappear.
[ ] Run backtest again.
    [ ] Pink highlights disappear after new result is loaded.

============================================================
5. Small cleanup
============================================================

Checklist:
[ ] Rename old toggleStrategy if it no longer matches behavior.
[ ] Avoid duplicated initialization logic for strategy settings.
[ ] Keep renderAll() stable.
[ ] Do not break current saved run loading.
[ ] Do not break current table rendering.
[ ] Do not change backend in Phase 1 unless absolutely necessary.
[ ] Keep API payload shape unchanged.
[ ] Keep old backtest behavior unchanged.

============================================================
6. Final Phase 1 manual QA
============================================================

Manual QA:
[ ] Page loads without console errors.
[ ] /api/options loads correctly.
[ ] Timeframe click still adds/removes timeframe.
[ ] Strategy click only opens settings.
[ ] Strategy double-click adds/removes strategy.
[ ] Selected strategy tags still remove correctly.
[ ] Run button enables when at least one timeframe is selected.
[ ] Run backtest still works.
[ ] Save run still works.
[ ] Load saved run still works.
[ ] Delete saved run still works.
[ ] Export CSV link still works.
[ ] Search Grid defaults are visible.
[ ] Search Grid Profile switching changes values.
[ ] Dirty pink highlight works after run.
[ ] Dirty pink highlight clears after save.
[ ] No backend behavior is changed in Phase 1.

Suggested commit message:
frontend: fix strategy selection UX and grid dirty state

Phase 1 done when:
[ ] UI strategy selection is no longer confusing.
[ ] Search Grid never starts blank.
[ ] Profile switching actually changes grid values.
[ ] User can clearly see when current results no longer match changed settings.
