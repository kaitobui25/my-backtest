Phase 1 Checklist — Unified Signal Builder Layer

Files to touch:
- app/backtest/signals.py
- app/backtest/runner.py only if needed for import test
- optional: app/backtest/signal_builder.py

Checklist:

[ ] Create SignalVariant dataclass:
    - strategy: str
    - params: str
    - long_entries: np.ndarray
    - short_entries: np.ndarray
    - side_modes: tuple[str, ...]

[ ] Decide location:
    - Option A: keep in app/backtest/signals.py
    - Option B: create app/backtest/signal_builder.py
    - Prefer Option B if signals.py is already too large

[ ] Add build_signal_variants(df, timeframe, mode, strategies=None)

[ ] Inside build_signal_variants():
    - normalize strategies to set[str] or None
    - validate mode: "normal" or "dense_high_winrate"
    - collect only supported strategy builders
    - skip unsupported strategy/mode combinations safely

[ ] Create strategy registry:
    STRATEGY_BUILDERS = {
        "VOL_EXPANSION_CONT": {
            "normal": build_vol_expansion_normal,
            "dense_high_winrate": build_vol_expansion_dense,
        },
        ...
    }

[ ] Refactor normal build_signals():
    - keep old logic working
    - wrap returned tuples into SignalVariant
    - preserve strategy name
    - preserve params string
    - preserve long_entries / short_entries / side_modes

[ ] Refactor dense build_vol_expansion_signals():
    - return SignalVariant
    - include strategy="VOL_EXPANSION_CONT"
    - remove anonymous dense tuple format

[ ] Do not change backtest result logic yet.
    - no metric changes
    - no API changes
    - no filter changes
    - no simulator changes

[ ] Add small local smoke test:
    - build_signal_variants(df, "M15", "normal", ["VOL_EXPANSION_CONT"])
    - build_signal_variants(df, "M15", "dense_high_winrate", ["VOL_EXPANSION_CONT"])
    - build_signal_variants(df, "M15", "dense_high_winrate", ["EMA_PULLBACK"])

[ ] Expected results:
    - normal returns SignalVariant list
    - dense VOL_EXPANSION_CONT returns SignalVariant list
    - dense unsupported strategy returns empty list, not crash
    - every SignalVariant has a valid strategy name
    - runner can later consume the same object format for both modes

Done when:
[ ] No dense signal is missing strategy name
[ ] No anonymous dense tuple remains
[ ] build_signal_variants() is the only public signal entry point for runner
[ ] Adding a new dense strategy only requires adding a builder + registry entry
