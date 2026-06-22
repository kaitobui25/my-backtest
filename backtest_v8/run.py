from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from core.config import BacktestConfig, load_config
from core.data import audit_data, load_ohlcv
from core.engine import (
    build_trade_log,
    iter_execution_grid,
    shift_entries,
    side_mode_arrays,
    simulate_trades,
)
from core.metrics import build_metrics_period, equity_curve_from_trades, monthly_returns_from_trades, prefix_metrics, summarize_simulation_fast
from core.pine_audit import audit_pine_sources
from core.registry import discover_indicators
from core.reports import pct, write_reports
from core.scoring import (
    conclusion,
    rejection_reasons,
    risk_level,
    score_setup,
    setup_group,
    target_achieved as setup_target_achieved,
    warnings_for_setup,
    why_not_live_trade_yet,
    why_selected,
)


LOGGER = logging.getLogger("backtest_v8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest V8 configurable strategy search")
    parser.add_argument("--config", default=str(THIS_DIR / "config.toml"), help="Path to TOML config")
    parser.add_argument("--run-id", default=None, help="Optional run id for result folder")
    return parser.parse_args()


def setup_logging(result_dir: Path) -> None:
    log_dir = THIS_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    result_dir.mkdir(parents=True, exist_ok=True)
    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_dir / f"{result_dir.name}.log", encoding="utf-8"),
        logging.FileHandler(result_dir / "run.log", encoding="utf-8"),
    ]
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        handlers=handlers,
        force=True,
    )


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def setup_id_for(row: dict[str, Any]) -> str:
    key = canonical_json(
        {
            "symbol": row["symbol"],
            "timeframe": row["timeframe"],
            "indicator": row["indicator"],
            "strategy": row["strategy"],
            "indicator_params": row["indicator_params"],
            "side_mode": row["side_mode"],
            "sl": row["stop_loss_pct"],
            "tp": row["take_profit_pct"],
            "max_hold": row["max_hold_bars"],
        }
    )
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]


def sanitize(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in value.lower())


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    result_dir = THIS_DIR / "result" / run_id
    setup_logging(result_dir)
    LOGGER.info("Starting backtest_v8 run_id=%s", run_id)
    LOGGER.info("Config=%s", config.path)

    registry = discover_indicators()
    enabled_names = {name for name, cfg in config.indicators.items() if bool(cfg.get("enabled", False))}
    missing = sorted(enabled_names - set(registry.keys()))
    if missing:
        LOGGER.warning("Enabled indicators missing Python implementations: %s", ", ".join(missing))

    data_audit = audit_data(config)
    pine_audit = audit_pine_sources(config, enabled_names)
    data_audit.to_csv(result_dir / "data_audit.csv", index=False)
    pine_audit.to_csv(result_dir / "pine_audit.csv", index=False)
    data_quality_by_tf = build_data_quality_map(data_audit, config)

    kept_rows: list[dict[str, Any]] = []
    rejected_rows: list[dict[str, Any]] = []
    signal_cache: dict[tuple[str, str, str], Any] = {}
    df_cache: dict[str, pd.DataFrame] = {}

    for timeframe in config.timeframes:
        try:
            df = load_ohlcv(config, timeframe)
        except Exception:
            LOGGER.exception("Skipping timeframe %s due to data load error", timeframe)
            continue
        df_cache[timeframe] = df
        data_quality = data_quality_by_tf.get(timeframe, {})
        metric_periods = {
            "full": build_metrics_period(df.index, config.position_size_pct, config.initial_equity, config.start, config.end),
            "train": build_metrics_period(df.index, config.position_size_pct, config.initial_equity, config.start, config.train_end),
            "oos": build_metrics_period(df.index, config.position_size_pct, config.initial_equity, config.oos_start, config.end),
        }
        grid = iter_execution_grid(config.grid_for_timeframe(timeframe))
        LOGGER.info("%s: loaded %s bars from %s to %s; grid=%d", timeframe, f"{len(df):,}", df.index.min(), df.index.max(), len(grid))

        for indicator_name in sorted(enabled_names):
            indicator = registry.get(indicator_name)
            indicator_cfg = config.indicators.get(indicator_name, {})
            if indicator is None:
                continue
            try:
                signals = indicator.generate(df, indicator_cfg)
            except Exception:
                LOGGER.exception("%s %s: indicator generation failed", timeframe, indicator_name)
                continue
            LOGGER.info("%s %s: generated %d signal variants", timeframe, indicator_name, len(signals))

            for signal in signals:
                params_json = canonical_json(signal.params)
                signal_cache[(timeframe, indicator_name, params_json)] = signal
                long_entries, short_entries = shift_entries(
                    signal.long_signal,
                    signal.short_signal,
                    int(config.execution["entry_lag_bars"]),
                    str(config.execution["signal_conflict"]).lower(),
                )
                if not bool(config.execution["allow_long"]):
                    long_entries[:] = False
                if not bool(config.execution["allow_short"]):
                    short_entries[:] = False
                raw_signal_count = int(long_entries.sum() + short_entries.sum())
                if raw_signal_count == 0:
                    continue

                for execution_params in grid:
                    row_base = {
                        "symbol": config.symbol,
                        "asset_class": config.market.get("asset_class", ""),
                        "timeframe": timeframe,
                        "indicator": indicator_name,
                        "indicator_display": indicator.metadata.display_name,
                        "strategy": signal.strategy,
                        "indicator_params": params_json,
                        "side_mode": execution_params["side_mode"],
                        "stop_loss_pct": execution_params["stop_loss_pct"],
                        "take_profit_pct": execution_params["take_profit_pct"],
                        "max_hold_bars": execution_params["max_hold_bars"],
                        "raw_signal_count": raw_signal_count,
                        "indicator_repaint_risk": indicator.metadata.repaint_risk,
                        "indicator_source": indicator.metadata.source,
                        "data_gap_count": data_quality.get("gap_count", 0),
                        "data_missing_bar_ratio": data_quality.get("missing_bar_ratio", 0.0),
                        "data_gap_penalty": data_quality.get("gap_penalty", 0.0),
                        "data_gap_warning": data_quality.get("warning", ""),
                    }
                    longs, shorts = side_mode_arrays(long_entries, short_entries, execution_params["side_mode"])
                    if not longs.any() and not shorts.any():
                        continue
                    min_tp_cost_multiple = float(config.filters.get("min_take_profit_cost_multiple", 2.5))
                    if execution_params["take_profit_pct"] <= min_tp_cost_multiple * (config.fee_per_side + config.slippage_per_side):
                        row = dict(row_base)
                        row["setup_id"] = setup_id_for(row)
                        row["rejection_reasons"] = "tp_too_small_vs_cost"
                        row["warnings"] = ""
                        row["score"] = -1e9
                        row["candidate_group"] = "D_rejected"
                        row["why_selected"] = ""
                        row["why_not_live_trade_yet"] = "take-profit is too small versus fee+slippage"
                        rejected_rows.append(row)
                        continue

                    sim = simulate_trades(
                        df,
                        longs,
                        shorts,
                        execution_params["stop_loss_pct"],
                        execution_params["take_profit_pct"],
                        config.fee_per_side,
                        config.slippage_per_side,
                        execution_params["max_hold_bars"],
                        str(config.execution["same_bar_exit_priority"]).lower(),
                    )
                    full = summarize_simulation_fast(sim, metric_periods["full"])
                    train = summarize_simulation_fast(sim, metric_periods["train"])
                    oos = summarize_simulation_fast(sim, metric_periods["oos"])
                    reasons = rejection_reasons(full, train, oos, config)
                    warnings = warnings_for_setup(
                        full,
                        train,
                        oos,
                        config,
                        data_gap_warning=str(data_quality.get("warning", "")),
                        timeframe=timeframe,
                    )
                    warnings.extend(signal.warnings)
                    if indicator.metadata.repaint_risk != "low":
                        warnings.append(f"indicator_repaint_risk_{indicator.metadata.repaint_risk}")
                    score = score_setup(
                        full,
                        train,
                        oos,
                        config,
                        timeframe=timeframe,
                        data_gap_penalty=float(data_quality.get("gap_penalty", 0.0)),
                    )

                    row = dict(row_base)
                    row.update(prefix_metrics("full", full))
                    row.update(prefix_metrics("train", train))
                    row.update(prefix_metrics("oos", oos))
                    row["target_achieved"] = setup_target_achieved(full, train, oos, config)
                    row["score"] = score
                    row["rejection_reasons"] = ",".join(reasons)
                    unique_warnings = sorted(set(warnings))
                    row["warnings"] = ",".join(unique_warnings)
                    row["risk_level"] = risk_level(full, oos, config)
                    row["conclusion"] = conclusion(full, train, oos, warnings, bool(reasons), config)
                    row["setup_id"] = setup_id_for(row)
                    row["candidate_group"] = setup_group(full, train, oos, bool(reasons), reasons, config)
                    row["why_selected"] = why_selected(row, bool(reasons), config)
                    row["why_not_live_trade_yet"] = why_not_live_trade_yet(row, unique_warnings, reasons, config)
                    if reasons:
                        rejected_rows.append(row)
                    else:
                        kept_rows.append(row)

    kept = pd.DataFrame(kept_rows)
    rejected = pd.DataFrame(rejected_rows)
    if not kept.empty:
        kept = kept.sort_values("score", ascending=False)
    kept.to_csv(result_dir / "kept_setups.csv", index=False)
    if bool(config.reporting.get("save_all_rejected", True)):
        rejected.to_csv(result_dir / "rejected_setups.csv", index=False)
    else:
        rejected.head(1000).to_csv(result_dir / "rejected_setups.csv", index=False)
    write_group_csvs(result_dir, kept, rejected)

    common_reasons = count_rejection_reasons(rejected)
    detail_artifacts = write_detail_artifacts(result_dir, config, kept, registry, df_cache, signal_cache)
    simple_path, detail_path, detail_json_path = write_reports(
        result_dir,
        config,
        data_audit,
        pine_audit,
        kept,
        rejected,
        detail_artifacts,
        common_reasons,
    )
    print_terminal_summary(config, kept, len(kept) + len(rejected), len(rejected), common_reasons, simple_path, detail_path, detail_json_path)
    LOGGER.info("Completed backtest_v8 run_id=%s", run_id)


def count_rejection_reasons(rejected: pd.DataFrame) -> Counter[str]:
    counter: Counter[str] = Counter()
    if rejected.empty or "rejection_reasons" not in rejected:
        return counter
    for value in rejected["rejection_reasons"].fillna(""):
        for reason in str(value).split(","):
            reason = reason.strip()
            if reason:
                counter[reason] += 1
    return counter


def build_data_quality_map(data_audit: pd.DataFrame, config: BacktestConfig) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    max_gap_count = max(1, int(config.data_quality.get("max_gap_count_warn", 20)))
    max_missing_ratio = max(1e-9, float(config.data_quality.get("max_missing_bar_ratio_warn", 0.05)))
    for _, row in data_audit.iterrows():
        timeframe = str(row.get("timeframe", "")).upper()
        gap_count = int(row.get("gap_count_gt_1_5x", 0) or 0)
        missing_ratio = float(row.get("missing_bar_ratio", 0.0) or 0.0)
        penalty = min(1.0, max(gap_count / max_gap_count, missing_ratio / max_missing_ratio))
        out[timeframe] = {
            "gap_count": gap_count,
            "missing_bar_ratio": missing_ratio,
            "gap_penalty": penalty,
            "warning": str(row.get("data_gap_warning", "") or ""),
        }
    return out


def write_group_csvs(result_dir: Path, kept: pd.DataFrame, rejected: pd.DataFrame) -> None:
    if not kept.empty and "score" in kept:
        kept.sort_values("score", ascending=False).to_csv(result_dir / "group_A_robust_stable.csv", index=False)
    else:
        kept.to_csv(result_dir / "group_A_robust_stable.csv", index=False)
    if not rejected.empty and "candidate_group" in rejected:
        rejected[rejected["candidate_group"] == "B_high_return_suspicious"].sort_values(
            ["full_avg_monthly_return", "oos_avg_monthly_return", "score"],
            ascending=[False, False, False],
        ).to_csv(result_dir / "group_B_high_return_suspicious.csv", index=False)
        rejected[rejected["candidate_group"] == "C_rejected_near_miss"].sort_values(
            ["score", "oos_profit_factor", "oos_trades"],
            ascending=[False, False, False],
        ).to_csv(result_dir / "group_C_rejected_near_miss.csv", index=False)
    else:
        pd.DataFrame().to_csv(result_dir / "group_B_high_return_suspicious.csv", index=False)
        pd.DataFrame().to_csv(result_dir / "group_C_rejected_near_miss.csv", index=False)


def write_detail_artifacts(
    result_dir: Path,
    config: BacktestConfig,
    kept: pd.DataFrame,
    registry: dict[str, Any],
    df_cache: dict[str, pd.DataFrame],
    signal_cache: dict[tuple[str, str, str], Any],
) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    if kept.empty:
        return artifacts
    setups_dir = result_dir / "setups"
    setups_dir.mkdir(parents=True, exist_ok=True)
    top_n = int(config.reporting.get("top_n_detail", 10))
    for _, row in kept.sort_values("score", ascending=False).head(top_n).iterrows():
        timeframe = str(row["timeframe"])
        indicator_name = str(row["indicator"])
        params_json = str(row["indicator_params"])
        df = df_cache.get(timeframe)
        if df is None:
            df = load_ohlcv(config, timeframe)
            df_cache[timeframe] = df
        signal = signal_cache.get((timeframe, indicator_name, params_json))
        if signal is None:
            indicator = registry[indicator_name]
            for candidate in indicator.generate(df, config.indicators[indicator_name]):
                if canonical_json(candidate.params) == params_json:
                    signal = candidate
                    break
        if signal is None:
            LOGGER.warning("Could not regenerate signal for setup %s", row["setup_id"])
            continue
        long_entries, short_entries = shift_entries(
            signal.long_signal,
            signal.short_signal,
            int(config.execution["entry_lag_bars"]),
            str(config.execution["signal_conflict"]).lower(),
        )
        if not bool(config.execution["allow_long"]):
            long_entries[:] = False
        if not bool(config.execution["allow_short"]):
            short_entries[:] = False
        longs, shorts = side_mode_arrays(long_entries, short_entries, str(row["side_mode"]))
        sim = simulate_trades(
            df,
            longs,
            shorts,
            float(row["stop_loss_pct"]),
            float(row["take_profit_pct"]),
            config.fee_per_side,
            config.slippage_per_side,
            int(row["max_hold_bars"]),
            str(config.execution["same_bar_exit_priority"]).lower(),
        )
        slug = sanitize(f"{row['setup_id']}_{timeframe}_{indicator_name}_{row['side_mode']}")
        trade_log = build_trade_log(df, sim, config.position_size_pct, config.initial_equity)
        equity_returns = sim.returns * config.position_size_pct
        equity_curve = equity_curve_from_trades(df.index, sim.exit_idx, equity_returns, config.initial_equity)
        exit_times = pd.DatetimeIndex(df.index[sim.exit_idx]) if sim.exit_idx.size else pd.DatetimeIndex([])
        monthly = monthly_returns_from_trades(equity_returns, exit_times, config.start or pd.Timestamp(df.index.min()), config.end or pd.Timestamp(df.index.max()))
        trade_path = setups_dir / f"{slug}_trades.csv"
        equity_path = setups_dir / f"{slug}_equity_curve.csv"
        monthly_path = setups_dir / f"{slug}_monthly_returns.csv"
        meta_path = setups_dir / f"{slug}_meta.json"
        trade_log.to_csv(trade_path, index=False)
        equity_curve.to_csv(equity_path, index=False)
        monthly.to_csv(monthly_path, index=False)
        with meta_path.open("w", encoding="utf-8") as f:
            json.dump(row.to_dict(), f, ensure_ascii=False, indent=2, default=str)
        artifacts.append(
            {
                "setup_id": row["setup_id"],
                "trade_log": str(trade_path.relative_to(result_dir)),
                "monthly_returns": str(monthly_path.relative_to(result_dir)),
                "equity_curve": str(equity_path.relative_to(result_dir)),
                "meta": str(meta_path.relative_to(result_dir)),
            }
        )
    return artifacts


def print_terminal_summary(
    config: BacktestConfig,
    kept: pd.DataFrame,
    tested_count: int,
    rejected_count: int,
    common_reasons: Counter[str],
    simple_path: Path,
    detail_path: Path,
    detail_json_path: Path,
) -> None:
    print("\n=== Backtest V8 completed ===")
    print(f"Setups tested: {tested_count}")
    print(f"Setups kept: {len(kept)}")
    print(f"Setups rejected: {rejected_count}")
    if not kept.empty:
        target_count = int(kept["target_achieved"].fillna(False).sum()) if "target_achieved" in kept else 0
        print(f"Robust setups reaching target ({config.target_label}): {target_count}")
    print("\nTop 5 setups:")
    if kept.empty:
        print("No setup passed the filters. Check rejected_setups.csv and relax config if needed.")
    else:
        top = kept.sort_values("score", ascending=False).head(int(config.reporting.get("top_n_terminal", 5)))
        for _, row in top.iterrows():
            print(
                f"- {row['setup_id']} | {row['timeframe']} {row['indicator']} {row['side_mode']} "
                f"SL {pct(row['stop_loss_pct'], 1)} TP {pct(row['take_profit_pct'], 1)} "
                f"score {float(row['score']):.2f} | avg/month {pct(row['full_avg_monthly_return'])} "
                f"DD {pct(row['full_max_drawdown'])} WR {pct(row['full_winrate'])} "
                f"trades/mo {float(row['full_avg_trades_per_month']):.2f} | risk {row['risk_level']} | {row['conclusion']}"
            )
        if not bool(top["target_achieved"].any()):
            print(f"Target ({config.target_label}) was NOT met in the kept top setups.")
    print("\nCommon rejection reasons:")
    if common_reasons:
        for reason, count in common_reasons.most_common(8):
            print(f"- {reason}: {count}")
    else:
        print("- none")
    print(f"\nSimple report: {simple_path}")
    print(f"Detailed report: {detail_path}")
    print(f"Detailed JSON: {detail_json_path}")


if __name__ == "__main__":
    main()
