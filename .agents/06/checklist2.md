PHASE 2 CHECKLIST — Backend Strategy Settings + VOL_EXPANSION_CONT Auto Trend

Files:
[ ] app/backtest/strategy_params.py
[ ] app/backtest/signals.py
[ ] app/backtest/runner.py
[ ] app/api/routes_options.py
[ ] tests/

Goal:
[ ] Add editable settings for all strategies.
[ ] Make backend actually use those settings.
[ ] Add trend=auto for VOL_EXPANSION_CONT.
[ ] Keep default behavior as close as possible to current behavior.
[ ] Do not break existing frontend/API payload shape.

============================================================
1. Add strategy schemas for all strategies
============================================================

Current problem:
[ ] Only VOL_EXPANSION_CONT has strategy settings.
[ ] Other strategies have no editable settings in the frontend.

Required:
[ ] Add schema for EMA_PULLBACK.
[ ] Add schema for DONCHIAN_BREAKOUT.
[ ] Add schema for BB_RSI_REVERT.
[ ] Add schema for IBS_REVERT.
[ ] Add schema for SUPERTREND.
[ ] Add schema for MACD_CROSS.
[ ] Add schema for WAVETREND.
[ ] Add schema for SQUEEZE_MOM.
[ ] Add schema for WILLIAMS_VIX_FIX.
[ ] Keep existing VOL_EXPANSION_CONT schema and extend it.

Schema rules:
[ ] Use the same format already used by VOL_EXPANSION_CONT.
[ ] Use type="range" for numeric ranges.
[ ] Use type="select" for fixed options.
[ ] Defaults should reproduce current hardcoded signal behavior.
[ ] Do not invent aggressive new parameter ranges yet.

Acceptance:
[ ] GET /api/options returns strategy_param_schemas for all strategies.
[ ] Frontend can open settings for every strategy.
[ ] No strategy should show an empty settings panel if it has a schema.

============================================================
2. Move hardcoded strategy params into schema defaults
============================================================

Current problem:
[ ] signals.py has many hardcoded loops.
[ ] UI settings will be fake unless signals.py consumes strategy_params.

Required:
[ ] For each strategy, read params from strategy_params.
[ ] If no params are provided, use schema defaults.
[ ] Default output should stay close to old behavior.

Implementation:
[ ] Add helper: get_strategy_params(strategy_name, strategy_params)
[ ] Add helper: schema_defaults(strategy_name)
[ ] Add helper: expand_range(value, step)
[ ] Add helper: normalize_select(value)
[ ] Add helper: normalize_optional_number(value)
[ ] Replace hardcoded lists with values from strategy params.

Acceptance:
[ ] Changing EMA_PULLBACK settings changes generated signal variants.
[ ] Changing BB_RSI_REVERT settings changes generated signal variants.
[ ] Changing MACD_CROSS settings changes generated signal variants.
[ ] Empty strategy_params still works.
[ ] Old/default behavior is preserved as much as possible.

============================================================
3. Strategy-specific parameter checklist
============================================================

EMA_PULLBACK:
[ ] fast: 34, 50
[ ] trend: ema200
[ ] rsi_lo: 40, 45
[ ] rsi_hi: 55, 60
[ ] adx_min: 12, 18
[ ] atr_mult: 0.60, 0.90
[ ] use_vol: false

DONCHIAN_BREAKOUT:
[ ] window: 40, 80
[ ] trend: ema200
[ ] adx_min: 18, 24
[ ] use_vol: false

BB_RSI_REVERT:
[ ] window: 20, 40
[ ] z: 2.0, 2.4
[ ] rsi_lo: 25, 30
[ ] rsi_hi: 70, 75
[ ] trend_mode: trend, range
[ ] adx_max: none, 24

IBS_REVERT:
[ ] ibs_lo: 0.05, 0.10, 0.20
[ ] ibs_hi: 0.80, 0.90, 0.95
[ ] trend_mode: trend, range
[ ] adx_max: none, 24

VOL_EXPANSION_CONT:
[ ] range_mult: current default range
[ ] trend: auto, none, ema20, ema50, ema100, ema200, ema300
[ ] adx_min: current default range
[ ] close_extreme: current default range
[ ] body_min: current default range

SUPERTREND:
[ ] period: 10, 14, 20
[ ] mult: 2.0, 3.0, 4.0
[ ] trend: none, ema200

MACD_CROSS:
[ ] preset: 8/21/5, 12/26/9, 5/34/5
[ ] trend: none, ema200
[ ] adx_min: 12, 18

WAVETREND:
[ ] preset: 10/21, 10/11, 14/21
[ ] ob_os: 53/-53, 60/-60
[ ] trend_mode: trend, range

SQUEEZE_MOM:
[ ] length: 20, 30
[ ] bb_mult: 2.0
[ ] kc_mult: 1.5, 2.0
[ ] trend: none, ema200

WILLIAMS_VIX_FIX:
[ ] pd_len: 22, 30
[ ] bbl: 20
[ ] ph: 0.85, 0.90
[ ] trend_mode: trend, range

============================================================
4. Add VOL_EXPANSION_CONT trend=auto
============================================================

Current problem:
[ ] VOL_EXPANSION_CONT trend is currently limited.
[ ] User wants auto trend search.

Required:
[ ] Add trend option: auto.
[ ] If trend=auto, backend expands to:
    [ ] none
    [ ] ema20
    [ ] ema50
    [ ] ema100
    [ ] ema200
    [ ] ema300

Implementation:
[ ] Update VOL_EXPANSION_CONT schema.
[ ] Update normal VOL_EXPANSION_CONT signal builder.
[ ] Update dense VOL_EXPANSION_CONT signal builder.
[ ] Use existing EMA arrays already calculated in signals.py.
[ ] Keep params string clear, for example:
    [ ] trend=ema20
    [ ] trend=ema50
    [ ] trend=ema100
    [ ] trend=ema200
    [ ] trend=ema300
    [ ] trend=none

Acceptance:
[ ] Selecting trend=auto generates multiple trend variants.
[ ] Selecting trend=ema200 generates only ema200 variant.
[ ] Result table clearly shows which trend was used.
[ ] Dense mode also respects trend=auto.

============================================================
5. Dense mode strategy_params support
============================================================

Current problem:
[ ] Normal mode passes strategy_params.
[ ] Dense mode may ignore strategy_params.
[ ] Dense VOL builder currently uses hardcoded values.

Required:
[ ] Pass strategy_params into dense mode.
[ ] Dense VOL_EXPANSION_CONT must consume frontend settings.
[ ] Dense VOL_EXPANSION_CONT must support trend=auto.

Implementation:
[ ] Update runner dense path to pass strategy_params.
[ ] Update build_signal_variants dense path to accept strategy_params.
[ ] Update dense VOL builder function signature.
[ ] Replace dense hardcoded VOL values with schema/default/user params.
[ ] Keep dense filters and dense grid behavior unchanged.

Acceptance:
[ ] Dense mode respects VOL range_mult settings.
[ ] Dense mode respects VOL adx_min settings.
[ ] Dense mode respects VOL trend=auto.
[ ] Dense mode still runs successfully.

============================================================
6. Dense mode behavior for non-VOL strategies
============================================================

Current problem:
[ ] Dense mode currently appears VOL-focused.
[ ] Selecting non-VOL strategies in dense mode may silently produce confusing results.

Required:
[ ] Do not silently fail.
[ ] Decide one clear behavior.

Preferred minimal behavior:
[ ] Dense mode supports VOL_EXPANSION_CONT first.
[ ] For unsupported dense strategies, skip them clearly.
[ ] Return warning metadata if possible.
[ ] Do not crash.

Optional better behavior:
[ ] Dense mode can reuse normal signal builders.
[ ] Then apply dense grid/filter/scoring.
[ ] Only do this if low risk.

Acceptance:
[ ] Dense mode with VOL_EXPANSION_CONT still works.
[ ] Dense mode with non-VOL strategy does not crash.
[ ] Behavior is clear and intentional.

============================================================
7. API compatibility
============================================================

Checklist:
[ ] /api/options still returns the same top-level keys.
[ ] strategy_param_schemas contains more strategies, but shape stays compatible.
[ ] Existing frontend does not need payload shape changes.
[ ] run_backtest payload shape stays compatible.
[ ] Existing saved runs do not break.
[ ] Missing strategy_params should be allowed.
[ ] Missing individual strategy setting should fallback to default.

Acceptance:
[ ] Old saved run can still load.
[ ] Running without selected strategies still works.
[ ] Running with selected strategies still works.
[ ] Running with no strategy_params still works.

============================================================
8. Tests
============================================================

Add/update tests:
[ ] test_options_contains_all_strategy_schemas
[ ] test_strategy_schema_defaults_are_valid
[ ] test_build_signals_uses_strategy_params
[ ] test_vol_auto_expands_trend_variants
[ ] test_vol_single_trend_does_not_expand_all
[ ] test_dense_mode_passes_strategy_params
[ ] test_missing_strategy_params_fallback_to_defaults
[ ] test_unknown_strategy_param_does_not_crash

Manual tests:
[ ] Start backend.
[ ] Open frontend.
[ ] Confirm every strategy has settings.
[ ] Select EMA_PULLBACK and change settings.
[ ] Run backtest.
[ ] Confirm params in result reflect changed settings.
[ ] Select VOL_EXPANSION_CONT.
[ ] Set trend=auto.
[ ] Run normal mode.
[ ] Confirm multiple trend variants appear.
[ ] Run dense mode.
[ ] Confirm trend=auto also works in dense.
[ ] Load old saved run.
[ ] Confirm no crash.

============================================================
9. Safety rules
============================================================

Do not:
[ ] Do not change frontend UX from Phase 1 unless required.
[ ] Do not change table columns unless required.
[ ] Do not change saved run format unless required.
[ ] Do not remove existing strategies.
[ ] Do not remove existing default behavior.
[ ] Do not make dense mode much slower without warning.
[ ] Do not silently ignore user settings.

============================================================
10. Suggested commit
============================================================

Commit message:
backend: add strategy parameter schemas and VOL auto trend

Phase 2 done when:
[ ] All strategies have editable settings.
[ ] Backend consumes those settings.
[ ] VOL_EXPANSION_CONT supports trend=auto.
[ ] Dense VOL mode respects user settings.
[ ] Defaults stay close to current results.
[ ] Tests pass.
