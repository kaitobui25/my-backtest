# Phase 2 Checklist — Normal Mode Robust Setup Finder

## Core Principles

- [ ] Focus only on `normal` mode.
- [ ] Keep user-facing mode as one mode: `normal`.
- [ ] Do not bring back `dense_high_winrate`.
- [ ] Do not add a second visible mode.
- [ ] Do not use random sampling.
- [ ] Do not blindly truncate candidates.
- [ ] Do not weaken filters.
- [ ] Do not optimize by hiding bad results.
- [ ] Do not change backtest execution logic silently.
- [ ] Phase 2 goal is not only speed, but better setup quality.
- [ ] Normal mode must find robust, tradeable setups, not just pretty backtest rows.

---

## 1. Redesign Normal Default Search Space

- [ ] Review current default strategy parameter ranges.
- [ ] Identify parameters that are too dense for normal mode.
- [ ] Keep normal search broad enough to find good setups.
- [ ] Avoid ultra-fine steps in default normal search.
- [ ] Do not remove important strategy families.
- [ ] Do not make normal too narrow.
- [ ] Keep all full ranges available internally or through explicit settings if needed.
- [ ] Document old vs new default search size.
- [ ] Document expected reduction in candidate count.

Example target for `VOL_EXPANSION_CONT` normal defaults:

- [ ] `range_mult`: balanced values, not every 0.1 step by default.
- [ ] `trend`: keep important options such as `none`, `ema100`, `ema200`.
- [ ] `adx_min`: use meaningful checkpoints instead of every integer.
- [ ] `close_extreme`: use meaningful checkpoints.
- [ ] `body_min`: use meaningful checkpoints.

Acceptance:

- [ ] Normal default search is much smaller than before.
- [ ] Normal default search still covers useful parameter regions.
- [ ] No strategy is accidentally disabled.
- [ ] Search space change is explicit and documented.

---

## 2. Keep Exact Simulation Inside Normal

- [ ] Normal mode must still run exact backtest logic for all generated candidates.
- [ ] Do not estimate final metrics.
- [ ] Do not rank candidates using partial simulation only.
- [ ] Do not skip full/test metrics.
- [ ] Do not skip max drawdown.
- [ ] Do not skip max gap days.
- [ ] Do not skip test/OOS validation.
- [ ] Keep fee handling unchanged unless explicitly configured.
- [ ] Keep entry/exit behavior unchanged.

Acceptance:

- [ ] Every returned row is produced by exact normal simulation.
- [ ] No approximate result appears as a final result.
- [ ] Result table remains trustworthy.

---

## 3. Add Top Candidate Verification Inside Normal

- [ ] After normal scan, select top N candidates for verification.
- [ ] N should be configurable, for example `verify_top_n`.
- [ ] Default should be reasonable, for example 100–500.
- [ ] Re-run selected candidates through the exact normal/realistic path when needed.
- [ ] Verify full metrics.
- [ ] Verify test/OOS metrics.
- [ ] Verify score.
- [ ] Verify max gap days.
- [ ] Verify drawdown.
- [ ] Mark verified candidates clearly in internal diagnostics.
- [ ] Do not expose this as a second user mode.

Acceptance:

- [ ] User still runs only `normal`.
- [ ] Top results are verified before final output.
- [ ] Diagnostics show how many candidates were verified.
- [ ] Final top rows are more reliable.

---

## 4. Add Stability Check For Top Candidates

- [ ] Add stability check only for top candidates, not for the entire search space.
- [ ] Create nearby parameter variants around each top candidate.
- [ ] Check nearby SL values.
- [ ] Check nearby TP values.
- [ ] Check nearby max_hold values.
- [ ] Check nearby strategy params when possible.
- [ ] Run exact simulation for neighbor candidates.
- [ ] Count how many neighbors pass core filters.
- [ ] Compute neighbor average profit factor.
- [ ] Compute neighbor average test profit factor.
- [ ] Compute neighbor average test win rate.
- [ ] Compute neighbor average drawdown.
- [ ] Compute a `stability_score`.
- [ ] Avoid making stability check too heavy.
- [ ] Make stability check configurable, for example `stability_top_n`.

Suggested new fields:

- [ ] `stability_score`
- [ ] `neighbor_count`
- [ ] `neighbor_pass_count`
- [ ] `neighbor_pass_rate`
- [ ] `neighbor_avg_profit_factor`
- [ ] `neighbor_avg_test_profit_factor`
- [ ] `neighbor_avg_test_win_rate`
- [ ] `neighbor_avg_max_drawdown`

Acceptance:

- [ ] Top setup with strong neighbors ranks better.
- [ ] One-point overfit setup ranks lower.
- [ ] Stability check does not slow normal mode too much.
- [ ] Stability metrics are clearly separated from core backtest metrics.

---

## 5. Improve Normal Score Ranking

- [ ] Keep old score available or documented before changing.
- [ ] Design a better normal score for tradeable setups.
- [ ] Prioritize test/OOS quality.
- [ ] Reward test profit factor.
- [ ] Reward test win rate, but do not overvalue it alone.
- [ ] Reward enough test trades.
- [ ] Reward full profit factor.
- [ ] Penalize large max drawdown.
- [ ] Penalize large max gap days.
- [ ] Penalize too few trades.
- [ ] Penalize unstable neighbor results.
- [ ] Reward high stability score.
- [ ] Avoid score being dominated by total_return only.
- [ ] Avoid score being dominated by win_rate only.

Suggested score inputs:

- [ ] `test_profit_factor`
- [ ] `test_win_rate`
- [ ] `test_trades`
- [ ] `profit_factor`
- [ ] `max_drawdown`
- [ ] `trades_per_day`
- [ ] `max_gap_days`
- [ ] `stability_score`

Acceptance:

- [ ] Top results are more realistic to test live/paper.
- [ ] Results with very few trades do not dominate.
- [ ] Results with huge gaps do not dominate.
- [ ] Results with weak test/OOS performance do not dominate.
- [ ] Results with stable neighboring params rank higher.

---

## 6. Add Robustness Flags

- [ ] Add internal flags for suspicious setups.
- [ ] Flag too few full trades.
- [ ] Flag too few test trades.
- [ ] Flag high max gap days.
- [ ] Flag unstable neighbor area.
- [ ] Flag high full/test mismatch.
- [ ] Flag high winrate but low profit factor.
- [ ] Flag high return but bad drawdown.
- [ ] Flag test result much worse than full result.

Possible fields:

- [ ] `robustness_flags`
- [ ] `full_test_pf_gap`
- [ ] `full_test_winrate_gap`
- [ ] `overfit_risk_score`

Acceptance:

- [ ] User can see why a setup may be risky.
- [ ] Suspicious setups are not silently promoted.
- [ ] Robustness flags do not replace exact metrics.

---

## 7. Keep Frontend Simple

- [ ] Keep only one visible mode: `normal`.
- [ ] Do not add dense mode UI.
- [ ] Do not add confusing research/fast/full modes.
- [ ] Show stability columns only if useful.
- [ ] Keep main result table readable.
- [ ] Optional: allow hiding advanced robustness columns.
- [ ] Optional: show a short summary panel:
  - [ ] candidates scanned
  - [ ] candidates verified
  - [ ] stability checks run
  - [ ] final rows kept
- [ ] Keep existing workflow unchanged.

Acceptance:

- [ ] User still clicks normal backtest and gets results.
- [ ] UI does not become complicated.
- [ ] New quality metrics help, not confuse.

---

## 8. Add Diagnostics For Phase 2 Quality Pipeline

- [ ] Track normal search candidate count.
- [ ] Track top candidates selected for verification.
- [ ] Track verified candidate count.
- [ ] Track stability neighbor count.
- [ ] Track stability runtime.
- [ ] Track score calculation runtime.
- [ ] Track final ranking runtime.
- [ ] Include these in diagnostics separately.

Suggested diagnostics:

- [ ] `normal_candidates_scanned`
- [ ] `top_candidates_selected`
- [ ] `verified_candidates`
- [ ] `stability_candidates_checked`
- [ ] `stability_neighbors_simulated`
- [ ] `verification_sec`
- [ ] `stability_sec`
- [ ] `ranking_sec`

Acceptance:

- [ ] It is clear how much time Phase 2 quality checks add.
- [ ] It is possible to tune top N and stability N later.

---

## 9. Tests

- [ ] Test new normal default search space generation.
- [ ] Test no strategy is accidentally removed.
- [ ] Test candidate verification returns identical metrics for the same setup.
- [ ] Test stability neighbor generation.
- [ ] Test stability score calculation.
- [ ] Test one-point overfit setup receives lower stability.
- [ ] Test robust neighbor setup receives higher stability.
- [ ] Test new score ranking.
- [ ] Test low trade count penalty.
- [ ] Test high max gap penalty.
- [ ] Test weak test/OOS penalty.
- [ ] Test frontend/API compatibility.
- [ ] Test dense mode remains untouched.

Acceptance:

- [ ] Existing tests pass.
- [ ] New Phase 2 tests pass.
- [ ] Normal result output remains stable and explainable.
- [ ] Dense behavior remains unchanged.

---

## 10. Performance Validation

- [ ] Run normal backtest before Phase 2.
- [ ] Record runtime.
- [ ] Record RAM.
- [ ] Record candidates scanned.
- [ ] Record top results.
- [ ] Record number of returned rows.
- [ ] Run normal backtest after Phase 2.
- [ ] Compare runtime.
- [ ] Compare RAM.
- [ ] Compare candidate count.
- [ ] Compare quality of top results.
- [ ] Check whether top results have better stability.
- [ ] Check whether obviously overfit rows are pushed lower.
- [ ] Document before/after.

Acceptance:

- [ ] Normal remains fast enough for web usage.
- [ ] RAM remains acceptable.
- [ ] Top results are more robust.
- [ ] No hidden approximation is used for final rows.

---

## Final Phase 2 Definition of Done

- [ ] User-facing mode is still only `normal`.
- [ ] Dense mode is still ignored/untouched.
- [ ] Normal default search space is balanced.
- [ ] Normal still uses exact simulation for final results.
- [ ] Top candidates are verified.
- [ ] Stability metrics exist for top candidates.
- [ ] Score ranking favors robust tradeable setups.
- [ ] Suspicious setups are flagged.
- [ ] UI remains simple.
- [ ] Diagnostics show verification/stability cost.
- [ ] Tests protect against overfit ranking and silent result changes.