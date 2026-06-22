from __future__ import annotations

from typing import Any

import numpy as np

from .config import BacktestConfig


TARGET_CRITERION_SUFFIXES = (
    ("_abs_max", "abs_max"),
    ("_abs_min", "abs_min"),
    ("_min", "min"),
    ("_max", "max"),
)


def cfg_float(values: dict[str, Any], key: str, default: float) -> float:
    return float(values.get(key, default))


def cfg_int(values: dict[str, Any], key: str, default: int) -> int:
    return int(values.get(key, default))


def cfg_bool(values: dict[str, Any], key: str, default: bool) -> bool:
    value = values.get(key, default)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def target_achieved(full: dict[str, Any], train: dict[str, Any], oos: dict[str, Any], config: BacktestConfig) -> bool:
    metrics_by_scope = {"full": full, "train": train, "oos": oos}
    for criterion, threshold in config.target_achievement.items():
        scope, metric, op = parse_target_criterion(criterion)
        if scope not in metrics_by_scope:
            raise ValueError(f"Unknown target scope in config target criterion: {criterion}")
        if metric not in metrics_by_scope[scope]:
            raise ValueError(f"Unknown metric in config target criterion: {criterion}")
        value = float(metrics_by_scope[scope][metric])
        target = float(threshold)
        if op == "min" and value < target:
            return False
        if op == "max" and value > target:
            return False
        if op == "abs_min" and abs(value) < target:
            return False
        if op == "abs_max" and abs(value) > target:
            return False
    return True


def parse_target_criterion(criterion: str) -> tuple[str, str, str]:
    parts = criterion.split("_", 1)
    if len(parts) != 2:
        raise ValueError(f"Target criterion must start with full_, train_, or oos_: {criterion}")
    scope, rest = parts
    for suffix, op in TARGET_CRITERION_SUFFIXES:
        if rest.endswith(suffix):
            metric = rest[: -len(suffix)]
            if not metric:
                break
            return scope, metric, op
    raise ValueError(f"Target criterion must end with _min, _max, _abs_min, or _abs_max: {criterion}")


def hard_rejection_reasons(full: dict[str, Any], train: dict[str, Any], oos: dict[str, Any], config: BacktestConfig) -> list[str]:
    hard = config.hard_filters
    reasons: list[str] = []
    if full["avg_monthly_return"] < float(hard.get("full_min_avg_monthly_return", 0.02)):
        reasons.append("hard_full_avg_monthly_below_min")
    if train["avg_monthly_return"] < float(hard.get("train_min_avg_monthly_return", 0.015)):
        reasons.append("hard_train_avg_monthly_below_min")
    if oos["avg_monthly_return"] < float(hard.get("oos_min_avg_monthly_return", 0.015)):
        reasons.append("hard_oos_avg_monthly_below_min")
    if oos["trades"] < int(hard.get("oos_min_trades", 40)):
        reasons.append("hard_oos_trades_below_min")
    if oos["months"] < int(hard.get("oos_min_months", 12)):
        reasons.append("hard_oos_months_below_min")
    if oos["profit_factor"] < float(hard.get("oos_min_profit_factor", 1.4)):
        reasons.append("hard_oos_profit_factor_below_min")
    if full["profit_factor"] < float(hard.get("full_min_profit_factor", 1.3)):
        reasons.append("hard_full_profit_factor_below_min")
    if oos["no_trade_month_ratio"] > float(hard.get("oos_max_no_trade_month_ratio", 0.10)):
        reasons.append("hard_oos_no_trade_month_ratio_above_max")
    if full["no_trade_month_ratio"] > float(hard.get("full_max_no_trade_month_ratio", 0.15)):
        reasons.append("hard_full_no_trade_month_ratio_above_max")
    if abs(float(full["max_drawdown"])) > float(hard.get("full_max_drawdown", 0.22)):
        reasons.append("hard_full_max_drawdown_above_max")
    if abs(float(oos["max_drawdown"])) > float(hard.get("oos_max_drawdown", 0.18)):
        reasons.append("hard_oos_max_drawdown_above_max")
    return reasons


def rejection_reasons(full: dict[str, Any], train: dict[str, Any], oos: dict[str, Any], config: BacktestConfig) -> list[str]:
    reasons = hard_rejection_reasons(full, train, oos, config)
    filters = config.filters
    targets = config.targets
    if full["trades"] < int(filters["min_total_trades"]):
        reasons.append("too_few_total_trades")
    if full["avg_trades_per_month"] < float(targets["min_trades_per_month"]):
        reasons.append("too_few_trades_per_month")
    if full["avg_trades_per_month"] > float(targets["max_trades_per_month"]):
        reasons.append("too_many_trades_per_month")
    if full["monthly_return_std"] > float(filters["max_monthly_return_std"]):
        reasons.append("monthly_return_too_volatile")
    if full["top_trade_profit_share"] > float(filters["max_top_trade_profit_share"]):
        reasons.append("profit_depends_on_one_trade")
    if full["top2_trade_profit_share"] > float(filters["max_top2_trade_profit_share"]):
        reasons.append("profit_depends_on_two_trades")
    if (
        cfg_bool(filters, "enable_oos_too_beautiful_filter", True)
        and train["avg_monthly_return"] > 0
        and oos["avg_monthly_return"] > train["avg_monthly_return"] * cfg_float(filters, "max_oos_train_return_ratio_with_limited_trades", 2.5)
        and full["trades"] < cfg_int(filters, "limited_trades_for_oos_ratio_check", 160)
    ):
        reasons.append("oos_too_beautiful_vs_train_with_limited_trades")
    return list(dict.fromkeys(reasons))


def warnings_for_setup(
    full: dict[str, Any],
    train: dict[str, Any],
    oos: dict[str, Any],
    config: BacktestConfig,
    *,
    data_gap_warning: str = "",
    timeframe: str = "",
) -> list[str]:
    targets = config.targets
    warning_cfg = config.warning_thresholds
    warnings: list[str] = []
    if not target_achieved(full, train, oos, config):
        warnings.append("target_not_met")
    if cfg_bool(warning_cfg, "warn_above_monthly_return_max", True) and full["avg_monthly_return"] > float(targets["monthly_return_max"]):
        warnings.append("avg_monthly_return_above_target_check_overfit")
    if full["profit_factor"] >= cfg_float(warning_cfg, "high_profit_factor", 3.0) and full["trades"] < cfg_int(warning_cfg, "high_profit_factor_max_full_trades", 160):
        warnings.append("high_profit_factor_with_limited_trades")
    if oos["profit_factor"] >= cfg_float(warning_cfg, "high_oos_profit_factor", 3.0) and oos["trades"] < cfg_int(warning_cfg, "high_oos_profit_factor_max_trades", 80):
        warnings.append("high_oos_profit_factor_with_limited_oos_trades")
    if full["top_trade_profit_share"] > cfg_float(warning_cfg, "profit_concentration_notice_share", 0.30):
        warnings.append("profit_concentration_notice")
    if full["no_trade_month_ratio"] > cfg_float(warning_cfg, "many_inactive_months_ratio", 0.10):
        warnings.append("many_inactive_months")
    if train["avg_monthly_return"] > 0 and oos["avg_monthly_return"] > train["avg_monthly_return"] * cfg_float(warning_cfg, "oos_much_better_than_train_ratio", 2.0):
        warnings.append("oos_much_better_than_train_check_regime_or_luck")
    if oos["avg_monthly_return"] < train["avg_monthly_return"] * cfg_float(warning_cfg, "oos_much_weaker_than_train_ratio", 0.50) and train["avg_monthly_return"] > 0:
        warnings.append("oos_much_weaker_than_train")
    if full["smoothness_r2"] < cfg_float(warning_cfg, "smoothness_r2_min", 0.25):
        warnings.append("equity_curve_not_smooth")
    if cfg_bool(warning_cfg, "warn_non_preferred_timeframe", True) and timeframe.upper() not in config.preferred_timeframes:
        warnings.append("non_preferred_timeframe_for_daily_btc_trading")
    if data_gap_warning:
        warnings.append(data_gap_warning)
    return warnings


def risk_level(full: dict[str, Any], oos: dict[str, Any], config: BacktestConfig) -> str:
    risk = config.risk_thresholds
    dd = abs(float(full["max_drawdown"]))
    if (
        dd <= cfg_float(risk, "low_max_full_drawdown", 0.12)
        and full["top_trade_profit_share"] <= cfg_float(risk, "low_max_top_trade_profit_share", 0.22)
        and oos["avg_monthly_return"] >= cfg_float(risk, "low_min_oos_avg_monthly_return", float(config.hard_filters.get("oos_min_avg_monthly_return", 0.015)))
        and full["no_trade_month_ratio"] <= cfg_float(risk, "low_max_full_no_trade_month_ratio", 0.10)
    ):
        return "thap"
    if (
        dd > cfg_float(risk, "high_max_full_drawdown", float(config.hard_filters.get("full_max_drawdown", 0.22)))
        or abs(float(oos["max_drawdown"])) > cfg_float(risk, "high_max_oos_drawdown", float(config.hard_filters.get("oos_max_drawdown", 0.18)))
        or full["top_trade_profit_share"] > cfg_float(risk, "high_max_top_trade_profit_share", 0.35)
        or oos["avg_monthly_return"] < cfg_float(risk, "high_oos_avg_monthly_return_below", cfg_float(risk, "high_min_oos_avg_monthly_return", 0.0))
    ):
        return "cao"
    return "vua"


def conclusion(full: dict[str, Any], train: dict[str, Any], oos: dict[str, Any], warnings: list[str], rejected: bool, config: BacktestConfig) -> str:
    if rejected:
        return "khong nen dung"
    if target_achieved(full, train, oos, config) and risk_level(full, oos, config) != "cao":
        return "nen xem xet"
    if "target_not_met" in warnings:
        return "robust nhung chua dat target"
    return "can test them"


def setup_group(full: dict[str, Any], train: dict[str, Any], oos: dict[str, Any], rejected: bool, reasons: list[str], config: BacktestConfig) -> str:
    if not rejected:
        return "A_robust_stable"
    if target_achieved(full, train, oos, config):
        return "B_high_return_suspicious"
    filters = config.filters
    if (
        near_miss_count(reasons) <= cfg_int(filters, "near_miss_max_fail_count", 3)
        and full["avg_monthly_return"] >= cfg_float(filters, "near_miss_min_avg_monthly_return", 0.01)
        and oos["trades"] >= cfg_int(filters, "near_miss_min_oos_trades", 20)
    ):
        return "C_rejected_near_miss"
    return "D_rejected"


def near_miss_count(reasons: list[str]) -> int:
    return len([r for r in reasons if r.startswith("hard_") or r in {"too_few_total_trades", "too_few_trades_per_month"}])


def why_selected(row: dict[str, Any], rejected: bool, config: BacktestConfig) -> str:
    if rejected:
        return ""
    pieces = [
        "passed strict full/train/OOS hard filters",
        f"OOS trades={int(row.get('oos_trades', 0))}",
        f"OOS PF={float(row.get('oos_profit_factor', 0.0)):.2f}",
        f"full DD={float(row.get('full_max_drawdown', 0.0)) * 100:.2f}%",
    ]
    if row.get("target_achieved"):
        pieces.append(f"target reached: {config.target_label}")
    else:
        pieces.append(f"stable candidate, but target is not reached: {config.target_label}")
    return "; ".join(pieces)


def why_not_live_trade_yet(row: dict[str, Any], warnings: list[str], reasons: list[str], config: BacktestConfig) -> str:
    notes: list[str] = []
    if reasons:
        notes.append("failed filters: " + ",".join(reasons[:6]))
    if not row.get("target_achieved", False):
        notes.append(f"target not met: {config.target_label}")
    if "large_data_gaps" in warnings:
        notes.append("BTC data has large/weekend gaps; verify with 24/7 exchange data")
    if "high_profit_factor_with_limited_trades" in warnings or "high_oos_profit_factor_with_limited_oos_trades" in warnings:
        notes.append("PF is high relative to trade count")
    if "oos_much_better_than_train_check_regime_or_luck" in warnings:
        notes.append("OOS is much better than train; possible regime/luck effect")
    if row.get("indicator_repaint_risk") and row.get("indicator_repaint_risk") != "low":
        notes.append(f"indicator repaint risk is {row.get('indicator_repaint_risk')}")
    return "; ".join(dict.fromkeys(notes)) if notes else "paper trade / forward test before live"


def score_setup(
    full: dict[str, Any],
    train: dict[str, Any],
    oos: dict[str, Any],
    config: BacktestConfig,
    *,
    timeframe: str = "",
    data_gap_penalty: float = 0.0,
) -> float:
    weights = config.scoring_weights
    params = config.scoring_params
    score = 0.0
    score += weights.get("monthly_return_fit", 30.0) * monthly_return_fit(full["avg_monthly_return"], config)
    score += weights.get("trade_frequency", 15.0) * trade_frequency_fit(full["avg_trades_per_month"], config)
    score += weights.get("drawdown", 15.0) * drawdown_fit(full["max_drawdown"], config)
    score += weights.get("oos", 20.0) * oos_fit(train, oos, config)
    score += weights.get("smoothness", 10.0) * smoothness_fit(full, config)
    score += weights.get("profit_factor", 7.0) * clipped_ratio(
        full["profit_factor"],
        cfg_float(params, "profit_factor_score_min", float(config.hard_filters.get("full_min_profit_factor", 1.3))),
        cfg_float(params, "profit_factor_score_max", 2.5),
    )
    score += weights.get("winrate", 3.0) * clipped_ratio(
        full["winrate"],
        float(config.targets["min_winrate"]),
        cfg_float(params, "winrate_score_max", 0.75),
    )
    score -= weights.get("risk_penalty", 25.0) * risk_penalty_value(full, train, oos, config)
    score -= weights.get("target_shortfall_penalty", 35.0) * target_shortfall_penalty(full, oos, config)
    score -= weights.get("timeframe_penalty", 15.0) * timeframe_penalty(timeframe, full, oos, config)
    score -= weights.get("gap_penalty", 35.0) * min(1.0, max(0.0, data_gap_penalty))
    if not np.isfinite(score):
        return -1e9
    return float(score)


def monthly_return_fit(value: float, config: BacktestConfig) -> float:
    low = float(config.targets["monthly_return_min"])
    high = float(config.targets["monthly_return_max"])
    if value <= 0:
        return 0.0
    if value < low:
        return 0.25 * clipped_ratio(value, 0.0, low)
    if value <= high:
        return 1.0
    return max(0.0, 0.65 - clipped_ratio(value - high, 0.0, high))


def trade_frequency_fit(value: float, config: BacktestConfig) -> float:
    low = float(config.targets["min_trades_per_month"])
    high = float(config.targets["max_trades_per_month"])
    if value < low:
        return clipped_ratio(value, 0.0, low)
    if value > high:
        return max(0.0, 1.0 - clipped_ratio(value - high, 0.0, high))
    return 1.0


def drawdown_fit(max_drawdown: float, config: BacktestConfig) -> float:
    return max(0.0, 1.0 - abs(float(max_drawdown)) / max(float(config.hard_filters.get("full_max_drawdown", 0.22)), 1e-9))


def oos_fit(train: dict[str, Any], oos: dict[str, Any], config: BacktestConfig) -> float:
    hard = config.hard_filters
    params = config.scoring_params
    target = cfg_float(params, "oos_return_score_target", float(config.targets["monthly_return_min"]))
    oos_return_score = clipped_ratio(oos["avg_monthly_return"], float(hard.get("oos_min_avg_monthly_return", 0.015)), target)
    pf_score = clipped_ratio(oos["profit_factor"], float(hard.get("oos_min_profit_factor", 1.4)), cfg_float(params, "oos_profit_factor_score_max", 2.2))
    trade_score = clipped_ratio(
        oos["trades"],
        float(hard.get("oos_min_trades", 40)),
        float(hard.get("oos_min_trades", 40)) * cfg_float(params, "oos_trade_score_multiplier", 3.0),
    )
    gap = abs(train["avg_monthly_return"] - oos["avg_monthly_return"])
    gap_penalty = clipped_ratio(gap, 0.0, cfg_float(params, "oos_train_gap_penalty_max", 0.12))
    return max(
        0.0,
        cfg_float(params, "oos_return_score_weight", 0.40) * oos_return_score
        + cfg_float(params, "oos_profit_factor_score_weight", 0.35) * pf_score
        + cfg_float(params, "oos_trade_score_weight", 0.25) * trade_score
        - cfg_float(params, "oos_train_gap_penalty_weight", 0.30) * gap_penalty,
    )


def smoothness_fit(full: dict[str, Any], config: BacktestConfig) -> float:
    std_score = max(0.0, 1.0 - full["monthly_return_std"] / max(float(config.filters["max_monthly_return_std"]), 1e-9))
    no_trade_score = max(0.0, 1.0 - full["no_trade_month_ratio"] / max(float(config.hard_filters.get("full_max_no_trade_month_ratio", 0.15)), 1e-9))
    return max(0.0, min(1.0, 0.40 * full["smoothness_r2"] + 0.25 * std_score + 0.20 * full["positive_month_rate"] + 0.15 * no_trade_score))


def risk_penalty_value(full: dict[str, Any], train: dict[str, Any], oos: dict[str, Any], config: BacktestConfig) -> float:
    hard = config.hard_filters
    filters = config.filters
    params = config.scoring_params
    warning_cfg = config.warning_thresholds
    dd = clipped_ratio(abs(float(full["max_drawdown"])), 0.0, float(hard.get("full_max_drawdown", 0.22)))
    oos_dd = clipped_ratio(abs(float(oos["max_drawdown"])), 0.0, float(hard.get("oos_max_drawdown", 0.18)))
    no_trade = max(
        clipped_ratio(full["no_trade_month_ratio"], 0.0, float(hard.get("full_max_no_trade_month_ratio", 0.15))),
        clipped_ratio(oos["no_trade_month_ratio"], 0.0, float(hard.get("oos_max_no_trade_month_ratio", 0.10))),
    )
    concentration = max(
        clipped_ratio(full["top_trade_profit_share"], 0.0, float(config.filters["max_top_trade_profit_share"])),
        clipped_ratio(full["top2_trade_profit_share"], 0.0, float(config.filters["max_top2_trade_profit_share"])),
    )
    oos_luck = (
        1.0
        if train["avg_monthly_return"] > 0
        and oos["avg_monthly_return"] > train["avg_monthly_return"] * cfg_float(filters, "max_oos_train_return_ratio_with_limited_trades", 2.5)
        and full["trades"] < cfg_int(filters, "limited_trades_for_oos_ratio_check", 160)
        else 0.0
    )
    pf_low_trades = (
        1.0
        if (full["profit_factor"] >= cfg_float(warning_cfg, "high_profit_factor", 3.0) and full["trades"] < cfg_int(warning_cfg, "high_profit_factor_max_full_trades", 160))
        or (oos["profit_factor"] >= cfg_float(warning_cfg, "high_oos_profit_factor", 3.0) and oos["trades"] < cfg_int(warning_cfg, "high_oos_profit_factor_max_trades", 80))
        else 0.0
    )
    return min(
        1.0,
        cfg_float(params, "risk_penalty_full_drawdown_weight", 0.25) * dd
        + cfg_float(params, "risk_penalty_oos_drawdown_weight", 0.20) * oos_dd
        + cfg_float(params, "risk_penalty_no_trade_weight", 0.20) * no_trade
        + cfg_float(params, "risk_penalty_concentration_weight", 0.15) * concentration
        + cfg_float(params, "risk_penalty_oos_luck_weight", 0.10) * oos_luck
        + cfg_float(params, "risk_penalty_pf_low_trades_weight", 0.10) * pf_low_trades,
    )


def target_shortfall_penalty(full: dict[str, Any], oos: dict[str, Any], config: BacktestConfig) -> float:
    target = float(config.targets["monthly_return_min"])
    full_gap = max(0.0, target - full["avg_monthly_return"]) / max(target, 1e-9)
    oos_gap = max(0.0, target - oos["avg_monthly_return"]) / max(target, 1e-9)
    return min(1.0, 0.55 * full_gap + 0.45 * oos_gap)


def timeframe_penalty(timeframe: str, full: dict[str, Any], oos: dict[str, Any], config: BacktestConfig) -> float:
    if timeframe.upper() in config.preferred_timeframes:
        return 0.0
    params = config.scoring_params
    low_trade_penalty = (
        cfg_float(params, "timeframe_low_trade_penalty", 1.0)
        if oos["trades"] < cfg_int(params, "timeframe_low_oos_trades", 60)
        or full["avg_trades_per_month"] < cfg_float(params, "timeframe_low_avg_trades_per_month", 2.0)
        else cfg_float(params, "timeframe_default_penalty", 0.35)
    )
    return low_trade_penalty


def clipped_ratio(value: float, low: float, high: float) -> float:
    if high <= low:
        return 1.0 if value >= high else 0.0
    return float(min(1.0, max(0.0, (value - low) / (high - low))))
