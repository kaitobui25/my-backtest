from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .engine import SimResult


@dataclass(frozen=True)
class MetricsPeriod:
    index_ns: np.ndarray
    month_ord_by_bar: np.ndarray
    start_ns: int
    end_ns: int
    start_month_ord: int
    month_count: int
    position_size_pct: float
    initial_equity: float


def month_periods(start: pd.Timestamp, end: pd.Timestamp) -> pd.PeriodIndex:
    return pd.period_range(start=start.to_period("M"), end=end.to_period("M"), freq="M")


def monthly_returns_from_trades(equity_returns: np.ndarray, exit_times: pd.DatetimeIndex, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    periods = month_periods(start, end)
    keys = exit_times.to_period("M") if equity_returns.size else pd.PeriodIndex([], freq="M")
    rows: list[dict[str, Any]] = []
    for period in periods:
        mask = keys == period
        month_returns = equity_returns[mask] if equity_returns.size else np.asarray([], dtype=float)
        ret = float(np.prod(1.0 + month_returns) - 1.0) if month_returns.size else 0.0
        rows.append({"month": str(period), "return": ret, "return_pct": ret * 100.0, "trades": int(month_returns.size)})
    monthly = pd.DataFrame(rows)
    if not monthly.empty:
        monthly["equity_index"] = (1.0 + monthly["return"]).cumprod()
    return monthly


def equity_curve_from_trades(index: pd.DatetimeIndex, exit_idx: np.ndarray, equity_returns: np.ndarray, initial_equity: float) -> pd.DataFrame:
    equity = np.full(len(index), initial_equity, dtype=float)
    current = initial_equity
    trade_ptr = 0
    for i in range(len(index)):
        while trade_ptr < exit_idx.size and int(exit_idx[trade_ptr]) == i:
            current *= 1.0 + float(equity_returns[trade_ptr])
            trade_ptr += 1
        equity[i] = current
    curve = pd.DataFrame({"time": index, "equity": equity})
    curve["peak"] = curve["equity"].cummax()
    curve["drawdown"] = curve["equity"] / curve["peak"] - 1.0
    curve["drawdown_pct"] = curve["drawdown"] * 100.0
    return curve


def build_metrics_period(
    index: pd.DatetimeIndex,
    position_size_pct: float,
    initial_equity: float,
    start: pd.Timestamp | None = None,
    end: pd.Timestamp | None = None,
) -> MetricsPeriod:
    idx = pd.DatetimeIndex(index).astype("datetime64[ns]")
    if start is None:
        start = pd.Timestamp(idx.min())
    if end is None:
        end = pd.Timestamp(idx.max())
    start = pd.Timestamp(start)
    end = pd.Timestamp(end)
    month_period_index = idx.to_period("M")
    month_ord_by_bar = month_period_index.year.astype(np.int64) * 12 + month_period_index.month.astype(np.int64) - 1
    start_month_ord = timestamp_month_ord(start)
    end_month_ord = timestamp_month_ord(end)
    return MetricsPeriod(
        index_ns=idx.asi8.astype(np.int64, copy=False),
        month_ord_by_bar=np.asarray(month_ord_by_bar, dtype=np.int64),
        start_ns=int(start.value),
        end_ns=int(end.value),
        start_month_ord=start_month_ord,
        month_count=max(0, end_month_ord - start_month_ord + 1),
        position_size_pct=float(position_size_pct),
        initial_equity=float(initial_equity),
    )


def timestamp_month_ord(ts: pd.Timestamp) -> int:
    ts = pd.Timestamp(ts)
    return int(ts.year) * 12 + int(ts.month) - 1


def summarize_simulation_fast(sim: SimResult, period: MetricsPeriod) -> dict[str, Any]:
    if sim.returns.size:
        exit_ns = period.index_ns[sim.exit_idx]
        mask = (exit_ns >= period.start_ns) & (exit_ns <= period.end_ns)
        returns = sim.returns[mask]
        exit_idx = sim.exit_idx[mask]
    else:
        returns = np.asarray([], dtype=float)
        exit_idx = np.asarray([], dtype=np.int64)
    equity_returns = returns * period.position_size_pct
    monthly_returns, monthly_trades = monthly_arrays_from_exit_idx(equity_returns, exit_idx, period)
    return summarize_arrays_from_monthly_arrays(
        returns,
        equity_returns,
        monthly_returns,
        monthly_trades,
        period.initial_equity,
    )


def monthly_arrays_from_exit_idx(equity_returns: np.ndarray, exit_idx: np.ndarray, period: MetricsPeriod) -> tuple[np.ndarray, np.ndarray]:
    monthly_growth = np.ones(period.month_count, dtype=float)
    monthly_trades = np.zeros(period.month_count, dtype=np.int64)
    if equity_returns.size and period.month_count:
        month_offsets = period.month_ord_by_bar[exit_idx] - period.start_month_ord
        for j in range(equity_returns.size):
            month_i = int(month_offsets[j])
            if 0 <= month_i < period.month_count:
                monthly_growth[month_i] *= 1.0 + float(equity_returns[j])
                monthly_trades[month_i] += 1
    return monthly_growth - 1.0, monthly_trades


def summarize_simulation(
    sim: SimResult,
    df: pd.DataFrame,
    position_size_pct: float,
    initial_equity: float,
    start: pd.Timestamp | None = None,
    end: pd.Timestamp | None = None,
) -> dict[str, Any]:
    period = build_metrics_period(pd.DatetimeIndex(df.index), position_size_pct, initial_equity, start, end)
    return summarize_simulation_fast(sim, period)


def summarize_arrays(notional_returns: np.ndarray, equity_returns: np.ndarray, monthly: pd.DataFrame, initial_equity: float) -> dict[str, Any]:
    return summarize_arrays_from_monthly_arrays(
        notional_returns,
        equity_returns,
        monthly["return"].to_numpy(float) if not monthly.empty else np.asarray([], dtype=float),
        monthly["trades"].to_numpy(np.int64) if not monthly.empty else np.asarray([], dtype=np.int64),
        initial_equity,
    )


def summarize_arrays_from_monthly_arrays(
    notional_returns: np.ndarray,
    equity_returns: np.ndarray,
    monthly_returns: np.ndarray,
    monthly_trades: np.ndarray,
    initial_equity: float,
) -> dict[str, Any]:
    trades = int(notional_returns.size)
    wins = notional_returns[notional_returns > 0]
    losses = notional_returns[notional_returns <= 0]
    gross_profit = float(wins.sum()) if wins.size else 0.0
    gross_loss = float(-losses.sum()) if losses.size else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (np.inf if gross_profit > 0 else 0.0)
    winrate = float(wins.size / trades) if trades else 0.0
    expectancy = float(notional_returns.mean()) if trades else 0.0
    equity_index = np.cumprod(1.0 + equity_returns) if trades else np.asarray([], dtype=float)
    total_return = float(equity_index[-1] - 1.0) if equity_index.size else 0.0
    if equity_index.size:
        peak = np.maximum.accumulate(equity_index)
        drawdown = equity_index / peak - 1.0
        max_drawdown = float(drawdown.min())
        ulcer_index = float(np.sqrt(np.mean(np.square(np.minimum(drawdown, 0.0)))))
        smoothness_r2 = equity_smoothness_r2(equity_index)
    else:
        max_drawdown = 0.0
        ulcer_index = 0.0
        smoothness_r2 = 0.0
    months = int(monthly_returns.size)
    if months:
        avg_monthly = float(monthly_returns.mean())
        median_monthly = float(np.median(monthly_returns))
        monthly_std = float(monthly_returns.std(ddof=0))
        best_month = float(monthly_returns.max())
        worst_month = float(monthly_returns.min())
        positive_month_rate = float((monthly_returns > 0).mean())
        avg_trades_per_month = float(monthly_trades.mean())
        max_trades_month = float(monthly_trades.max())
        min_trades_month = float(monthly_trades.min())
        no_trade_months = int((monthly_trades == 0).sum())
        no_trade_month_ratio = float(no_trade_months / months)
    else:
        avg_monthly = median_monthly = monthly_std = best_month = worst_month = positive_month_rate = 0.0
        avg_trades_per_month = max_trades_month = min_trades_month = no_trade_months = no_trade_month_ratio = 0.0
    top1, top2 = profit_concentration(notional_returns)
    return {
        "trades": trades,
        "months": months,
        "winrate": winrate,
        "total_return": total_return,
        "profit_factor": profit_factor,
        "expectancy": expectancy,
        "max_drawdown": max_drawdown,
        "avg_win": float(wins.mean()) if wins.size else 0.0,
        "avg_loss": float(losses.mean()) if losses.size else 0.0,
        "avg_monthly_return": avg_monthly,
        "median_monthly_return": median_monthly,
        "monthly_return_std": monthly_std,
        "best_month": best_month,
        "worst_month": worst_month,
        "positive_month_rate": positive_month_rate,
        "avg_trades_per_month": avg_trades_per_month,
        "max_trades_month": max_trades_month,
        "min_trades_month": min_trades_month,
        "no_trade_months": no_trade_months,
        "no_trade_month_ratio": no_trade_month_ratio,
        "top_trade_profit_share": top1,
        "top2_trade_profit_share": top2,
        "ulcer_index": ulcer_index,
        "smoothness_r2": smoothness_r2,
        "ending_equity": initial_equity * (1.0 + total_return),
    }


def profit_concentration(returns: np.ndarray) -> tuple[float, float]:
    wins = np.sort(returns[returns > 0])[::-1]
    if wins.size == 0:
        return 0.0, 0.0
    gross_profit = float(wins.sum())
    if gross_profit <= 0:
        return 0.0, 0.0
    return float(wins[0] / gross_profit), float(wins[:2].sum() / gross_profit)


def equity_smoothness_r2(equity_index: np.ndarray) -> float:
    if equity_index.size < 3 or np.any(equity_index <= 0):
        return 0.0
    x = np.arange(equity_index.size, dtype=float)
    y = np.log(equity_index)
    x_centered = x - float(x.mean())
    y_centered = y - float(y.mean())
    y_denom = float(np.dot(y_centered, y_centered))
    if y_denom <= 0.0:
        return 0.0
    denom = float(np.sqrt(np.dot(x_centered, x_centered) * y_denom))
    if denom <= 0.0:
        return 0.0
    corr = float(np.dot(x_centered, y_centered) / denom)
    return float(corr * corr)


def prefix_metrics(prefix: str, metrics: dict[str, Any]) -> dict[str, Any]:
    return {f"{prefix}_{k}": v for k, v in metrics.items()}
