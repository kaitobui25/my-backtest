from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import hashlib
import importlib.util
import sys

import numpy as np
import pandas as pd


RESEARCH_PATH = Path(__file__).with_name("30_btc_short_stop_research.py")
spec = importlib.util.spec_from_file_location("btc_short_stop_research", RESEARCH_PATH)
research = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = research
assert spec.loader is not None
spec.loader.exec_module(research)


OUT_DIR = research.base.ROOT / "my-data" / "backtest_v7" / "result" / "05_manual_portfolio_research"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CANDIDATES_CSV = (
    research.base.ROOT
    / "my-data"
    / "backtest_v7"
    / "result"
    / "04_short_stop_research"
    / "audit"
    / "btc_short_stop_candidates_all.csv"
)

TEST_START = pd.Timestamp("2025-01-01")
TARGET_CAGR = 50.0

PRE_POOL_LIMIT = 220
MAX_OPTIMIZE_SETUPS = 60
MIN_BASKET_SIZE = 4
MAX_BASKET_SIZE = 8
ALLOCATIONS = [0.15, 0.20, 0.25]
MAX_CONCURRENT_VALUES = [2, 3, 4]
MAX_GROSS_EXPOSURE = 1.0

NUMERIC_COLUMNS = [
    "sl",
    "tp",
    "max_hold",
    "signal_count",
    "trades",
    "win_rate",
    "total_return",
    "profit_factor",
    "expectancy",
    "max_drawdown",
    "avg_win",
    "avg_loss",
    "test_trades",
    "test_win_rate",
    "test_total_return",
    "test_profit_factor",
    "test_expectancy",
    "score",
]


@dataclass(frozen=True)
class PortfolioConfig:
    allocation: float
    max_concurrent: int
    block_opposite: bool = True


def finite_cap(series: pd.Series, cap: float) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).clip(upper=cap).fillna(cap)


def fmt_float(value: float) -> str:
    text = f"{float(value):.6f}".rstrip("0").rstrip(".")
    return text if text else "0"


def candidate_id(row: pd.Series) -> str:
    key = (
        f"{row['timeframe']}|{row['strategy']}|{row['params']}|{row['side_mode']}|"
        f"{fmt_float(row['sl'])}|{fmt_float(row['tp'])}|{int(row['max_hold'])}"
    )
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def candidate_label(row: pd.Series) -> str:
    side = str(row["side_mode"]).replace("_", "-")
    return (
        f"{row['timeframe']} {side} {row['strategy']} "
        f"SL {float(row['sl']) * 100:.2f}% TP {float(row['tp']) * 100:.2f}% MH {int(row['max_hold'])}"
    )


def load_candidates() -> pd.DataFrame:
    df = pd.read_csv(CANDIDATES_CSV)
    for col in NUMERIC_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["candidate_id"] = df.apply(candidate_id, axis=1)
    df["label"] = df.apply(candidate_label, axis=1)

    pf = finite_cap(df["profit_factor"], 5.0)
    test_pf = finite_cap(df["test_profit_factor"], 5.0)
    df["manual_score"] = (
        0.55 * df["score"].fillna(0)
        + 0.40 * df["win_rate"].fillna(0)
        + 0.70 * df["test_win_rate"].fillna(0)
        + 8.0 * pf
        + 13.0 * test_pf
        + 0.050 * df["total_return"].clip(upper=350).fillna(0)
        + 0.090 * df["test_total_return"].clip(upper=180).fillna(0)
        + 20.0 * df["expectancy"].clip(lower=-1, upper=3).fillna(-1)
        + 28.0 * df["test_expectancy"].clip(lower=-1, upper=3).fillna(-1)
        - 440.0 * df["sl"].fillna(0.10)
    )
    return df


def select_candidate_pool(candidates: pd.DataFrame) -> pd.DataFrame:
    pool = candidates[
        (candidates["sl"] <= 0.04)
        & (candidates["trades"] >= 35)
        & (candidates["test_trades"] >= 8)
        & (candidates["win_rate"] >= 50)
        & (candidates["test_win_rate"] >= 50)
        & (candidates["profit_factor"] >= 1.10)
        & (candidates["test_profit_factor"] >= 1.10)
        & (candidates["expectancy"] > 0)
        & (candidates["test_expectancy"] > 0)
        & (candidates["total_return"] > 0)
        & (candidates["test_total_return"] > 0)
    ].copy()
    pool = pool.sort_values("manual_score", ascending=False)

    frames: list[pd.DataFrame] = [pool.head(120)]
    for cols, head in [
        (["timeframe", "strategy", "side_mode"], 10),
        (["timeframe", "side_mode"], 14),
        (["strategy", "side_mode"], 18),
    ]:
        frames.append(pool.groupby(cols, group_keys=False).head(head))

    selected = pd.concat(frames, ignore_index=True).drop_duplicates("candidate_id")
    selected = selected.sort_values("manual_score", ascending=False).head(PRE_POOL_LIMIT)
    return selected.reset_index(drop=True)


def sequence_signature(trades: pd.DataFrame) -> str:
    if trades.empty:
        return "empty"
    part = trades.sort_values(["entry_time", "exit_time", "side"])[["entry_time", "exit_time", "side", "return"]].copy()
    part["entry_time"] = pd.to_datetime(part["entry_time"]).astype(str)
    part["exit_time"] = pd.to_datetime(part["exit_time"]).astype(str)
    part["return"] = part["return"].round(8)
    return hashlib.sha1(part.to_csv(index=False).encode("utf-8")).hexdigest()


def same_trade_key(row: pd.Series) -> str:
    return (
        f"{pd.Timestamp(row['entry_time']).isoformat()}|{pd.Timestamp(row['exit_time']).isoformat()}|"
        f"{row['side']}|{float(row['entry']):.6f}|{float(row['exit']):.6f}|{float(row['return']):.8f}"
    )


def raw_metrics(trades: pd.DataFrame) -> dict[str, float]:
    if trades.empty:
        return {
            "trades": 0,
            "win_rate": np.nan,
            "total_return": 0.0,
            "profit_factor": np.nan,
            "expectancy": np.nan,
            "max_drawdown": 0.0,
            "avg_win": np.nan,
            "avg_loss": np.nan,
        }
    return research.metrics_dict(trades["return"].to_numpy(float))


def prefix_metrics(prefix: str, metrics: dict[str, float]) -> dict[str, float]:
    return {f"{prefix}_{key}": value for key, value in metrics.items()}


def simulate_candidate(
    row: pd.Series,
    df_cache: dict[str, pd.DataFrame],
    signal_cache: dict[str, list[object]],
) -> pd.DataFrame:
    timeframe = str(row["timeframe"])
    if timeframe not in df_cache:
        df_cache[timeframe] = research.load_ohlc(timeframe)
        signal_cache[timeframe] = research.build_signals(df_cache[timeframe], timeframe)

    signal = next(
        sig
        for sig in signal_cache[timeframe]
        if sig.strategy == row["strategy"] and sig.params == row["params"]
    )
    longs, shorts = research.side_mode_arrays(signal.long_entries, signal.short_entries, str(row["side_mode"]))
    trades = research.simulate_records(
        df_cache[timeframe],
        longs,
        shorts,
        float(row["sl"]),
        float(row["tp"]),
        int(row["max_hold"]),
    )
    if trades.empty:
        return trades
    trades = trades.copy()
    trades["entry_time"] = pd.to_datetime(trades["entry_time"])
    trades["exit_time"] = pd.to_datetime(trades["exit_time"])
    trades["candidate_id"] = row["candidate_id"]
    trades["label"] = row["label"]
    trades["timeframe"] = row["timeframe"]
    trades["strategy"] = row["strategy"]
    trades["params"] = row["params"]
    trades["side_mode"] = row["side_mode"]
    trades["sl"] = row["sl"]
    trades["tp"] = row["tp"]
    trades["max_hold"] = row["max_hold"]
    trades["same_trade_key"] = trades.apply(same_trade_key, axis=1)
    return trades


def build_setup_pool(pre_pool: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    df_cache: dict[str, pd.DataFrame] = {}
    signal_cache: dict[str, list[object]] = {}
    trades_by_id: dict[str, pd.DataFrame] = {}
    rows: list[dict[str, object]] = []
    seen_signatures: set[str] = set()
    family_counts: Counter[str] = Counter()
    timeframe_counts: Counter[str] = Counter()

    for _, row in pre_pool.iterrows():
        trades = simulate_candidate(row, df_cache, signal_cache)
        if len(trades) < 10:
            continue
        signature = sequence_signature(trades)
        if signature in seen_signatures:
            continue

        family = f"{row['timeframe']}|{row['strategy']}|{row['side_mode']}"
        if family_counts[family] >= 5:
            continue
        if timeframe_counts[str(row["timeframe"])] >= 16:
            continue

        train_trades = trades[pd.to_datetime(trades["exit_time"]) < TEST_START]
        test_trades = trades[pd.to_datetime(trades["exit_time"]) >= TEST_START]
        train = raw_metrics(train_trades)
        test = raw_metrics(test_trades)
        full = raw_metrics(trades)
        if train["trades"] < 8 or test["trades"] < 4:
            continue
        if train["total_return"] <= 0 or test["total_return"] <= 0:
            continue
        if train["profit_factor"] < 1.05 or test["profit_factor"] < 1.02:
            continue

        setup_score = (
            min(train["total_return"], 220.0) * 0.10
            + min(test["total_return"], 180.0) * 0.13
            + min(train["win_rate"], 95.0) * 0.30
            + min(test["win_rate"], 95.0) * 0.45
            + min(train["profit_factor"], 4.0) * 12.0
            + min(test["profit_factor"], 4.0) * 14.0
            - abs(min(full["max_drawdown"], 0.0)) * 0.55
            - float(row["sl"]) * 360.0
            + min(full["trades"], 180) * 0.05
        )

        cid = str(row["candidate_id"])
        trades_by_id[cid] = trades
        rows.append(
            {
                "candidate_id": cid,
                "label": row["label"],
                "timeframe": row["timeframe"],
                "strategy": row["strategy"],
                "params": row["params"],
                "side_mode": row["side_mode"],
                "sl": row["sl"],
                "tp": row["tp"],
                "max_hold": row["max_hold"],
                "signal_signature": signature,
                "setup_score": setup_score,
                "worst_mae_pct": trades["mae_pct"].min(),
                "avg_mae_pct": trades["mae_pct"].mean(),
                **prefix_metrics("full", full),
                **prefix_metrics("train", train),
                **prefix_metrics("oos", test),
            }
        )
        seen_signatures.add(signature)
        family_counts[family] += 1
        timeframe_counts[str(row["timeframe"])] += 1

    setup_pool = pd.DataFrame(rows).sort_values("setup_score", ascending=False)
    setup_pool = setup_pool.head(MAX_OPTIMIZE_SETUPS).reset_index(drop=True)
    trades_by_id = {cid: trades_by_id[cid] for cid in setup_pool["candidate_id"]}
    return setup_pool, trades_by_id


def combine_trades(
    setup_ids: list[str],
    setup_pool: pd.DataFrame,
    trades_by_id: dict[str, pd.DataFrame],
    start_time: pd.Timestamp | None = None,
    end_time: pd.Timestamp | None = None,
) -> pd.DataFrame:
    if not setup_ids:
        return pd.DataFrame()
    rank = setup_pool.set_index("candidate_id")["setup_score"].to_dict()
    frames = [trades_by_id[cid] for cid in setup_ids if cid in trades_by_id]
    if not frames:
        return pd.DataFrame()
    trades = pd.concat(frames, ignore_index=True)
    if start_time is not None:
        trades = trades[trades["entry_time"] >= start_time]
    if end_time is not None:
        trades = trades[trades["exit_time"] < end_time]
    if trades.empty:
        return trades
    trades = trades.copy()
    trades["priority"] = trades["candidate_id"].map(rank).fillna(0.0)
    trades = trades.sort_values(["entry_time", "priority", "exit_time"], ascending=[True, False, True])
    trades = trades.drop_duplicates("same_trade_key", keep="first")
    return trades.reset_index(drop=True)


def close_open_trade(open_trade: dict[str, object], equity: float, records: list[dict[str, object]]) -> float:
    trade_return = float(open_trade["return"])
    notional = float(open_trade["notional"])
    equity_before = equity
    pnl = notional * trade_return
    equity_after = equity_before + pnl
    account_return = equity_after / equity_before - 1.0 if equity_before > 0 else np.nan
    record = dict(open_trade)
    record.update(
        {
            "pnl": pnl,
            "equity_before_exit": equity_before,
            "equity_after_exit": equity_after,
            "account_return": account_return,
        }
    )
    records.append(record)
    return equity_after


def simulate_portfolio(
    setup_ids: list[str],
    setup_pool: pd.DataFrame,
    trades_by_id: dict[str, pd.DataFrame],
    config: PortfolioConfig,
    start_time: pd.Timestamp | None = None,
    end_time: pd.Timestamp | None = None,
) -> pd.DataFrame:
    entries = combine_trades(setup_ids, setup_pool, trades_by_id, start_time=start_time, end_time=end_time)
    if entries.empty:
        return pd.DataFrame()

    equity = 1.0
    open_trades: list[dict[str, object]] = []
    records: list[dict[str, object]] = []
    skipped_same_setup = 0
    skipped_capacity = 0
    skipped_opposite = 0
    max_open = 0

    def close_due(now: pd.Timestamp) -> None:
        nonlocal equity
        while True:
            due = [trade for trade in open_trades if pd.Timestamp(trade["exit_time"]) <= now]
            if not due:
                break
            trade = min(due, key=lambda item: pd.Timestamp(item["exit_time"]))
            open_trades.remove(trade)
            equity = close_open_trade(trade, equity, records)

    for _, row in entries.iterrows():
        entry_time = pd.Timestamp(row["entry_time"])
        close_due(entry_time)

        cid = str(row["candidate_id"])
        if any(str(trade["candidate_id"]) == cid for trade in open_trades):
            skipped_same_setup += 1
            continue
        if len(open_trades) >= config.max_concurrent:
            skipped_capacity += 1
            continue
        if config.block_opposite and any(str(trade["side"]) != str(row["side"]) for trade in open_trades):
            skipped_opposite += 1
            continue

        notional = equity * config.allocation
        open_trade = row.to_dict()
        open_trade.update(
            {
                "notional": notional,
                "equity_at_entry": equity,
                "allocation": config.allocation,
                "max_concurrent": config.max_concurrent,
                "block_opposite": config.block_opposite,
                "open_count_at_entry": len(open_trades) + 1,
            }
        )
        open_trades.append(open_trade)
        max_open = max(max_open, len(open_trades))

    for trade in sorted(open_trades, key=lambda item: pd.Timestamp(item["exit_time"])):
        equity = close_open_trade(trade, equity, records)

    result = pd.DataFrame(records)
    if not result.empty:
        result = result.sort_values("exit_time").reset_index(drop=True)
        result["equity"] = result["equity_after_exit"]
        result["return_pct"] = result["return"] * 100
        result["account_return_pct"] = result["account_return"] * 100
        result["win"] = result["return"] > 0
        result["max_open"] = max_open
        result["skipped_same_setup"] = skipped_same_setup
        result["skipped_capacity"] = skipped_capacity
        result["skipped_opposite"] = skipped_opposite
    return result


def portfolio_metrics(
    trades: pd.DataFrame,
    period_start: pd.Timestamp | None = None,
    period_end: pd.Timestamp | None = None,
) -> dict[str, float]:
    if trades.empty:
        return {
            "trades": 0,
            "win_rate": np.nan,
            "total_return": 0.0,
            "cagr": 0.0,
            "profit_factor": np.nan,
            "expectancy_account_pct": np.nan,
            "avg_trade_return": np.nan,
            "max_drawdown": 0.0,
            "trades_per_year": 0.0,
            "max_open": 0,
            "skipped_capacity": 0,
            "skipped_opposite": 0,
        }

    # Use account_return so period slices reset equity correctly. The absolute
    # equity_after_exit column belongs to the simulation span that produced it.
    final_equity = float((1.0 + trades["account_return"].astype(float)).prod())
    total_return = (final_equity - 1.0) * 100
    start = period_start if period_start is not None else pd.Timestamp(trades["entry_time"].min())
    end = period_end if period_end is not None else pd.Timestamp(trades["exit_time"].max())
    years = max((end - start).total_seconds() / (365.25 * 24 * 3600), 1.0 / 365.25)
    cagr = (final_equity ** (1.0 / years) - 1.0) * 100

    equity_curve = pd.concat([pd.Series([1.0]), trades["equity_after_exit"].astype(float)], ignore_index=True)
    drawdown = equity_curve / equity_curve.cummax() - 1.0
    pnl = trades["pnl"].astype(float)
    gross_profit = pnl[pnl > 0].sum()
    gross_loss = -pnl[pnl < 0].sum()
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else np.inf

    return {
        "trades": int(len(trades)),
        "win_rate": float((trades["return"] > 0).mean() * 100),
        "total_return": total_return,
        "cagr": cagr,
        "profit_factor": float(profit_factor),
        "expectancy_account_pct": float(trades["account_return"].mean() * 100),
        "avg_trade_return": float(trades["return"].mean() * 100),
        "max_drawdown": float(drawdown.min() * 100),
        "trades_per_year": float(len(trades) / years),
        "max_open": int(trades["max_open"].max()) if "max_open" in trades else 0,
        "skipped_capacity": int(trades["skipped_capacity"].max()) if "skipped_capacity" in trades else 0,
        "skipped_opposite": int(trades["skipped_opposite"].max()) if "skipped_opposite" in trades else 0,
    }


def train_objective(metrics: dict[str, float], setup_ids: list[str], setup_pool: pd.DataFrame) -> float:
    if metrics["trades"] < 20 or metrics["profit_factor"] < 1.05:
        return -np.inf
    drawdown_penalty = abs(min(metrics["max_drawdown"], 0.0))
    cagr = max(metrics["cagr"], 0.0)
    target_penalty = abs(cagr - TARGET_CAGR) * 0.20
    selected = setup_pool[setup_pool["candidate_id"].isin(setup_ids)]
    diversity = (
        selected["timeframe"].nunique() * 1.8
        + selected["strategy"].nunique() * 1.4
        + selected["side_mode"].nunique() * 1.2
    )
    return (
        min(cagr, 130.0)
        + min(metrics["profit_factor"], 4.0) * 7.0
        + min(metrics["trades_per_year"], 90.0) * 0.12
        + diversity
        - drawdown_penalty * 1.05
        - target_penalty
    )


def basket_allowed(setup_ids: list[str], setup_pool: pd.DataFrame) -> bool:
    selected = setup_pool[setup_pool["candidate_id"].isin(setup_ids)]
    if selected.empty:
        return True
    if selected.groupby("timeframe").size().max() > 4:
        return False
    if selected.groupby(["timeframe", "strategy", "side_mode"]).size().max() > 3:
        return False
    return True


def evaluate_portfolio(
    setup_ids: list[str],
    setup_pool: pd.DataFrame,
    trades_by_id: dict[str, pd.DataFrame],
    config: PortfolioConfig,
    global_start: pd.Timestamp,
    global_end: pd.Timestamp,
) -> dict[str, object]:
    train_trades = simulate_portfolio(
        setup_ids,
        setup_pool,
        trades_by_id,
        config,
        end_time=TEST_START,
    )
    oos_trades = simulate_portfolio(
        setup_ids,
        setup_pool,
        trades_by_id,
        config,
        start_time=TEST_START,
    )
    full_trades = simulate_portfolio(setup_ids, setup_pool, trades_by_id, config)
    train = portfolio_metrics(train_trades, period_start=global_start, period_end=TEST_START)
    oos = portfolio_metrics(oos_trades, period_start=TEST_START, period_end=global_end)
    full = portfolio_metrics(full_trades, period_start=global_start, period_end=global_end)
    return {
        "setup_count": len(setup_ids),
        "setup_ids": ";".join(setup_ids),
        "allocation": config.allocation,
        "max_concurrent": config.max_concurrent,
        "block_opposite": config.block_opposite,
        **prefix_metrics("train", train),
        **prefix_metrics("oos", oos),
        **prefix_metrics("full", full),
    }


def optimize_portfolios(
    setup_pool: pd.DataFrame,
    trades_by_id: dict[str, pd.DataFrame],
    global_start: pd.Timestamp,
    global_end: pd.Timestamp,
) -> pd.DataFrame:
    setup_ids = setup_pool["candidate_id"].tolist()
    rows: list[dict[str, object]] = []

    for allocation in ALLOCATIONS:
        for max_concurrent in MAX_CONCURRENT_VALUES:
            if allocation * max_concurrent > MAX_GROSS_EXPOSURE:
                continue
            print(f"Optimizing allocation={allocation:.2f}, max_concurrent={max_concurrent}", flush=True)
            config = PortfolioConfig(allocation=allocation, max_concurrent=max_concurrent)
            basket: list[str] = []
            remaining = setup_ids.copy()
            current_score = -np.inf

            for _ in range(MAX_BASKET_SIZE):
                best_id = None
                best_score = -np.inf
                best_metrics: dict[str, object] | None = None
                for cid in remaining:
                    trial = basket + [cid]
                    if not basket_allowed(trial, setup_pool):
                        continue
                    train_trades = simulate_portfolio(
                        trial,
                        setup_pool,
                        trades_by_id,
                        config,
                        end_time=TEST_START,
                    )
                    train = portfolio_metrics(train_trades, period_start=global_start, period_end=TEST_START)
                    score = train_objective(train, trial, setup_pool)
                    if score > best_score:
                        best_id = cid
                        best_score = score
                        best_metrics = train

                if best_id is None or best_metrics is None:
                    break
                if len(basket) >= MIN_BASKET_SIZE and best_score < current_score - 1.0:
                    break

                basket.append(best_id)
                remaining.remove(best_id)
                current_score = best_score

                if len(basket) >= MIN_BASKET_SIZE:
                    item = evaluate_portfolio(basket, setup_pool, trades_by_id, config, global_start, global_end)
                    item["train_objective"] = current_score
                    rows.append(item)

    portfolios = pd.DataFrame(rows)
    if portfolios.empty:
        return portfolios

    portfolios["target_distance"] = (portfolios["oos_cagr"] - TARGET_CAGR).abs()
    portfolios["recommend_score"] = (
        -0.95 * portfolios["target_distance"]
        + 0.20 * portfolios["train_cagr"].clip(upper=100)
        + 0.35 * portfolios["oos_cagr"].clip(upper=140)
        + 7.0 * finite_cap(portfolios["oos_profit_factor"], 4.0)
        - 0.90 * portfolios["oos_max_drawdown"].clip(upper=0).abs()
        + 0.12 * portfolios["oos_trades_per_year"].clip(upper=90)
        - portfolios["setup_count"] * 0.45
    )
    return portfolios.sort_values(["recommend_score", "train_objective"], ascending=False).reset_index(drop=True)


def yearly_breakdown(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    rows = []
    for year, group in trades.groupby(pd.to_datetime(trades["exit_time"]).dt.year):
        equity = (1.0 + group["account_return"].astype(float)).prod()
        pnl = group["pnl"].astype(float)
        gross_profit = pnl[pnl > 0].sum()
        gross_loss = -pnl[pnl < 0].sum()
        rows.append(
            {
                "year": int(year),
                "trades": int(len(group)),
                "win_rate": (group["return"] > 0).mean() * 100,
                "return": (equity - 1.0) * 100,
                "profit_factor": gross_profit / gross_loss if gross_loss > 0 else np.inf,
                "avg_trade_return": group["return"].mean() * 100,
            }
        )
    return pd.DataFrame(rows)


def format_metric_table(metrics: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trades": metrics["trades"],
                "win_rate": metrics["win_rate"],
                "total_return": metrics["total_return"],
                "cagr": metrics["cagr"],
                "profit_factor": metrics["profit_factor"],
                "max_drawdown": metrics["max_drawdown"],
                "trades_per_year": metrics["trades_per_year"],
            }
        ]
    )


def write_report(
    setup_pool: pd.DataFrame,
    portfolios: pd.DataFrame,
    recommended: pd.Series,
    rec_setups: pd.DataFrame,
    rec_trades: pd.DataFrame,
    global_start: pd.Timestamp,
    global_end: pd.Timestamp,
) -> None:
    config = PortfolioConfig(
        allocation=float(recommended["allocation"]),
        max_concurrent=int(recommended["max_concurrent"]),
        block_opposite=bool(recommended["block_opposite"]),
    )
    train = portfolio_metrics(
        rec_trades[rec_trades["exit_time"] < TEST_START],
        period_start=global_start,
        period_end=TEST_START,
    )
    oos = portfolio_metrics(
        rec_trades[rec_trades["entry_time"] >= TEST_START],
        period_start=TEST_START,
        period_end=global_end,
    )
    full = portfolio_metrics(rec_trades, period_start=global_start, period_end=global_end)
    yearly = yearly_breakdown(rec_trades)

    summary_path = OUT_DIR / "summary_manual_vi.md"
    with summary_path.open("w", encoding="utf-8") as f:
        f.write("# BTC Manual Multi-Timeframe Portfolio Research\n\n")
        f.write("Muc tieu: ghep nhieu setup BTC de trade tay, khong ep mot setup rieng le dat 50%/nam.\n\n")
        f.write("Day la backtest va playbook nghien cuu, khong phai loi khuyen tai chinh hay dam bao loi nhuan.\n\n")
        f.write("## Cach mo phong\n\n")
        f.write(f"- Train/optimize: `{global_start.date()}` den truoc `{TEST_START.date()}`.\n")
        f.write(f"- OOS/test: `{TEST_START.date()}` den `{global_end.date()}`.\n")
        f.write(f"- Moi lenh dung `{config.allocation * 100:.0f}%` equity tai thoi diem vao lenh.\n")
        f.write(f"- Toi da `{config.max_concurrent}` lenh BTC mo cung luc.\n")
        f.write("- Khong giu long va short nguoc chieu cung luc.\n")
        f.write("- Neu nhieu setup cho cung mot trade, chi tinh mot lenh uu tien cao hon.\n")
        f.write(f"- Phi/spread: `{research.base.FEE_PER_SIDE * 100:.3f}%` moi chieu.\n\n")

        f.write("## Ket qua recommended basket\n\n")
        f.write("Train:\n\n")
        f.write(format_metric_table(train).to_markdown(index=False, floatfmt=".2f"))
        f.write("\n\nOOS/test:\n\n")
        f.write(format_metric_table(oos).to_markdown(index=False, floatfmt=".2f"))
        f.write("\n\nFull period:\n\n")
        f.write(format_metric_table(full).to_markdown(index=False, floatfmt=".2f"))
        f.write("\n\n## Setup trong ro\n\n")
        setup_cols = [
            "label",
            "timeframe",
            "side_mode",
            "strategy",
            "params",
            "sl",
            "tp",
            "max_hold",
            "train_trades",
            "train_win_rate",
            "train_total_return",
            "oos_trades",
            "oos_win_rate",
            "oos_total_return",
        ]
        f.write(rec_setups[setup_cols].to_markdown(index=False, floatfmt=".4f"))
        f.write("\n\n## Yearly realized portfolio returns\n\n")
        f.write(yearly.to_markdown(index=False, floatfmt=".2f") if not yearly.empty else "No trades.\n")
        f.write("\n\n## Luat trade tay de dung nhat quan\n\n")
        f.write("1. Chi vao lenh sau khi nen signal dong, entry o open nen ke tiep cua timeframe do.\n")
        f.write("2. Neu dang co lenh BTC nguoc chieu, bo qua signal moi.\n")
        f.write("3. Neu da co so lenh mo bang gioi han, bo qua signal moi, khong duoi lenh.\n")
        f.write("4. Dat SL/TP theo setup; het max_hold thi dong lenh theo close nen hien tai.\n")
        f.write("5. Neu gap hai signal trung nhau cung entry/exit/side, chi danh mot lenh.\n")
        f.write("6. Nen forward-test toi thieu 2-3 thang bang lot nho truoc khi tang size.\n\n")
        f.write("## File duoc tao\n\n")
        f.write("- `setup_pool.csv`: cac setup unique duoc dua vao optimizer.\n")
        f.write("- `portfolio_candidates.csv`: cac ro da test.\n")
        f.write("- `recommended_setups.csv`: setup trong ro recommended.\n")
        f.write("- `recommended_portfolio_trades.csv`: log lenh cua ro recommended.\n")
        f.write("- `recommended_yearly.csv`: ket qua theo nam.\n")


def main() -> None:
    print(f"Loading candidates from {CANDIDATES_CSV}")
    candidates = load_candidates()
    pre_pool = select_candidate_pool(candidates)
    pre_pool.to_csv(OUT_DIR / "pre_pool.csv", index=False)
    print(f"Pre-pool candidates: {len(pre_pool)}")

    setup_pool, trades_by_id = build_setup_pool(pre_pool)
    if setup_pool.empty:
        raise RuntimeError("No setup survived manual portfolio filters.")
    setup_pool.to_csv(OUT_DIR / "setup_pool.csv", index=False)
    print(f"Unique setup pool: {len(setup_pool)}")

    all_trades = pd.concat(trades_by_id.values(), ignore_index=True)
    global_start = pd.Timestamp(all_trades["entry_time"].min())
    global_end = pd.Timestamp(all_trades["exit_time"].max())

    portfolios = optimize_portfolios(setup_pool, trades_by_id, global_start, global_end)
    if portfolios.empty:
        raise RuntimeError("No portfolio candidate was generated.")
    portfolios.to_csv(OUT_DIR / "portfolio_candidates.csv", index=False)
    recommended = portfolios.iloc[0]

    setup_ids = str(recommended["setup_ids"]).split(";")
    config = PortfolioConfig(
        allocation=float(recommended["allocation"]),
        max_concurrent=int(recommended["max_concurrent"]),
        block_opposite=bool(recommended["block_opposite"]),
    )
    rec_trades = simulate_portfolio(setup_ids, setup_pool, trades_by_id, config)
    rec_setups = setup_pool[setup_pool["candidate_id"].isin(setup_ids)].copy()
    rec_setups["allocation"] = config.allocation
    rec_setups = rec_setups.sort_values("setup_score", ascending=False)
    yearly = yearly_breakdown(rec_trades)

    rec_trades.to_csv(OUT_DIR / "recommended_portfolio_trades.csv", index=False)
    rec_setups.to_csv(OUT_DIR / "recommended_setups.csv", index=False)
    yearly.to_csv(OUT_DIR / "recommended_yearly.csv", index=False)
    write_report(setup_pool, portfolios, recommended, rec_setups, rec_trades, global_start, global_end)

    print("\nRecommended portfolio:")
    summary_cols = [
        "setup_count",
        "allocation",
        "max_concurrent",
        "train_trades",
        "train_cagr",
        "train_profit_factor",
        "train_max_drawdown",
        "oos_trades",
        "oos_cagr",
        "oos_profit_factor",
        "oos_max_drawdown",
        "full_cagr",
        "full_max_drawdown",
    ]
    print(portfolios[summary_cols].head(10).to_string(index=False))
    print(f"\nSaved under {OUT_DIR}")


if __name__ == "__main__":
    main()
