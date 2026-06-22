from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import importlib.util
import sys

import numpy as np
import pandas as pd


SEARCH_PATH = Path(__file__).with_name("20_btc_strategy_search.py")
spec = importlib.util.spec_from_file_location("btc_strategy_search", SEARCH_PATH)
search = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = search
assert spec.loader is not None
spec.loader.exec_module(search)


OUT_DIR = search.ROOT / "my-data" / "backtest_v7" / "result" / "02_validation"
OUT_DIR.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class Setup:
    slug: str
    label: str
    timeframe: str
    ibs_lo: float
    ibs_hi: float
    trend_mode: str
    adx_max: int | None
    side_mode: str
    sl: float
    tp: float
    max_hold: int


SETUPS = [
    Setup(
        slug="h4_ibs_range_profit",
        label="H4 IBS Range Profit",
        timeframe="H4",
        ibs_lo=0.10,
        ibs_hi=0.90,
        trend_mode="range",
        adx_max=None,
        side_mode="both",
        sl=0.10,
        tp=0.10,
        max_hold=0,
    ),
    Setup(
        slug="h4_ibs_range_high_wr",
        label="H4 IBS Range High Winrate",
        timeframe="H4",
        ibs_lo=0.05,
        ibs_hi=0.90,
        trend_mode="range",
        adx_max=None,
        side_mode="both",
        sl=0.18,
        tp=0.10,
        max_hold=0,
    ),
    Setup(
        slug="d1_ibs_trend_aggressive",
        label="D1 IBS Trend Aggressive",
        timeframe="D1",
        ibs_lo=0.10,
        ibs_hi=0.80,
        trend_mode="trend",
        adx_max=None,
        side_mode="both",
        sl=0.30,
        tp=0.04,
        max_hold=0,
    ),
    Setup(
        slug="d1_ibs_trend_high_wr",
        label="D1 IBS Trend High Winrate",
        timeframe="D1",
        ibs_lo=0.10,
        ibs_hi=0.80,
        trend_mode="trend",
        adx_max=None,
        side_mode="both",
        sl=0.18,
        tp=0.03,
        max_hold=0,
    ),
]


def build_ibs_entries(df: pd.DataFrame, setup: Setup) -> tuple[np.ndarray, np.ndarray, pd.Series]:
    close = df["close"]
    high = df["high"]
    low = df["low"]
    ema200 = search.ema(close, 200)
    adx14 = search.adx(df, 14)
    ibs = (close - low) / (high - low).replace(0, np.nan)
    long_sig = ibs <= setup.ibs_lo
    short_sig = ibs >= setup.ibs_hi

    if setup.trend_mode == "trend":
        long_sig &= close > ema200
        short_sig &= close < ema200
    elif setup.trend_mode == "range":
        long_sig &= adx14 <= 18
        short_sig &= adx14 <= 18
    elif setup.trend_mode == "counter":
        long_sig &= close < ema200
        short_sig &= close > ema200
    else:
        raise ValueError(setup.trend_mode)

    if setup.adx_max is not None:
        long_sig &= adx14 <= setup.adx_max
        short_sig &= adx14 <= setup.adx_max

    long_entries = search.shift_signal(long_sig)
    short_entries = search.shift_signal(short_sig)
    return (*search.side_mode_arrays(long_entries, short_entries, setup.side_mode), ibs)


def simulate_records(df: pd.DataFrame, setup: Setup, long_entries: np.ndarray, short_entries: np.ndarray) -> pd.DataFrame:
    records = []
    in_pos = False
    direction = 0
    entry = 0.0
    entry_i = 0
    entry_time = None

    open_ = df["open"].to_numpy(float)
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    close = df["close"].to_numpy(float)
    times = df.index

    def excursions(exit_i: int) -> tuple[float, float]:
        lo = low[entry_i : exit_i + 1].min()
        hi = high[entry_i : exit_i + 1].max()
        if direction == 1:
            mae = (lo / entry - 1.0) * 100
            mfe = (hi / entry - 1.0) * 100
        else:
            mae = (entry / hi - 1.0) * 100
            mfe = (entry / lo - 1.0) * 100
        return mae, mfe

    for i in range(len(df)):
        if in_pos:
            held = i - entry_i
            should_time_exit = setup.max_hold > 0 and held >= setup.max_hold
            if direction == 1:
                sl_price = entry * (1.0 - setup.sl)
                tp_price = entry * (1.0 + setup.tp)
                hit_sl = low[i] <= sl_price
                hit_tp = high[i] >= tp_price
                if hit_sl or hit_tp or should_time_exit:
                    if hit_sl:
                        exit_price = sl_price
                        reason = "sl"
                    elif hit_tp:
                        exit_price = tp_price
                        reason = "tp"
                    else:
                        exit_price = close[i]
                        reason = "time"
                    ret = (exit_price / entry - 1.0) - 2.0 * search.FEE_PER_SIDE
                    mae, mfe = excursions(i)
                    records.append((entry_time, times[i], "long", entry, exit_price, held, reason, ret, mae, mfe))
                    in_pos = False
            else:
                sl_price = entry * (1.0 + setup.sl)
                tp_price = entry * (1.0 - setup.tp)
                hit_sl = high[i] >= sl_price
                hit_tp = low[i] <= tp_price
                if hit_sl or hit_tp or should_time_exit:
                    if hit_sl:
                        exit_price = sl_price
                        reason = "sl"
                    elif hit_tp:
                        exit_price = tp_price
                        reason = "tp"
                    else:
                        exit_price = close[i]
                        reason = "time"
                    ret = (entry / exit_price - 1.0) - 2.0 * search.FEE_PER_SIDE
                    mae, mfe = excursions(i)
                    records.append((entry_time, times[i], "short", entry, exit_price, held, reason, ret, mae, mfe))
                    in_pos = False

        if not in_pos:
            if long_entries[i]:
                in_pos = True
                direction = 1
                entry = open_[i]
                entry_i = i
                entry_time = times[i]
            elif short_entries[i]:
                in_pos = True
                direction = -1
                entry = open_[i]
                entry_i = i
                entry_time = times[i]

    if in_pos:
        if direction == 1:
            ret = (close[-1] / entry - 1.0) - 2.0 * search.FEE_PER_SIDE
            side = "long"
        else:
            ret = (entry / close[-1] - 1.0) - 2.0 * search.FEE_PER_SIDE
            side = "short"
        mae, mfe = excursions(len(df) - 1)
        records.append((entry_time, times[-1], side, entry, close[-1], len(df) - 1 - entry_i, "end", ret, mae, mfe))

    trades = pd.DataFrame(
        records,
        columns=["entry_time", "exit_time", "side", "entry", "exit", "bars_held", "exit_reason", "return", "mae_pct", "mfe_pct"],
    )
    if not trades.empty:
        trades["return_pct"] = trades["return"] * 100
        trades["equity"] = (1 + trades["return"]).cumprod()
        trades["win"] = trades["return"] > 0
    return trades


def metrics_dict(returns: np.ndarray) -> dict[str, float]:
    trades, wr, total, pf, exp, dd, avg_win, avg_loss = search.metrics(returns)
    return {
        "trades": trades,
        "win_rate": wr,
        "total_return": total,
        "profit_factor": pf,
        "expectancy": exp,
        "max_drawdown": dd,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
    }


def period_breakdown(trades: pd.DataFrame, period: str) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    key = pd.to_datetime(trades["exit_time"]).dt.to_period(period).astype(str)
    rows = []
    for name, group in trades.groupby(key):
        returns = group["return"].to_numpy(float)
        stats = metrics_dict(returns)
        stats["period"] = name
        rows.append(stats)
    return pd.DataFrame(rows)[["period", "trades", "win_rate", "total_return", "profit_factor", "expectancy", "max_drawdown"]]


def validate(setup: Setup) -> dict[str, float | str]:
    df = search.load_ohlc(setup.timeframe)
    long_entries, short_entries, ibs = build_ibs_entries(df, setup)
    trades = simulate_records(df, setup, long_entries, short_entries)
    returns = trades["return"].to_numpy(float)
    full = metrics_dict(returns)

    test_mask = pd.to_datetime(trades["exit_time"]) >= search.TEST_START
    test = metrics_dict(trades.loc[test_mask, "return"].to_numpy(float))

    trades.to_csv(OUT_DIR / f"{setup.slug}_trades.csv", index=False)
    period_breakdown(trades, "Y").to_csv(OUT_DIR / f"{setup.slug}_yearly.csv", index=False)
    period_breakdown(trades, "M").to_csv(OUT_DIR / f"{setup.slug}_monthly.csv", index=False)

    side_rows = []
    for side, group in trades.groupby("side"):
        row = metrics_dict(group["return"].to_numpy(float))
        row["side"] = side
        side_rows.append(row)
    pd.DataFrame(side_rows).to_csv(OUT_DIR / f"{setup.slug}_side.csv", index=False)

    summary = {
        "slug": setup.slug,
        "label": setup.label,
        "timeframe": setup.timeframe,
        "rules": f"IBS long <= {setup.ibs_lo}, short >= {setup.ibs_hi}, trend={setup.trend_mode}, side={setup.side_mode}, SL={setup.sl:.0%}, TP={setup.tp:.0%}, max_hold={setup.max_hold}",
        "worst_mae_pct": trades["mae_pct"].min() if not trades.empty else np.nan,
        "avg_mae_pct": trades["mae_pct"].mean() if not trades.empty else np.nan,
        "best_mfe_pct": trades["mfe_pct"].max() if not trades.empty else np.nan,
        **{f"full_{k}": v for k, v in full.items()},
        **{f"test_{k}": v for k, v in test.items()},
    }
    return summary


def main() -> None:
    summaries = [validate(setup) for setup in SETUPS]
    summary_df = pd.DataFrame(summaries)
    summary_df.to_csv(OUT_DIR / "validation_summary.csv", index=False)

    report = OUT_DIR / "validation_summary.md"
    with report.open("w", encoding="utf-8") as f:
        f.write("# BTCUSD Candidate Validation\n\n")
        f.write(f"- Fee model: `{search.FEE_PER_SIDE * 100:.3f}%` per side.\n")
        f.write(f"- OOS/test starts: `{search.TEST_START.date()}`.\n")
        f.write("- Same-candle TP/SL conflict assumes SL first.\n\n")
        cols = [
            "label",
            "timeframe",
            "rules",
            "full_trades",
            "full_win_rate",
            "full_total_return",
            "full_profit_factor",
            "full_max_drawdown",
            "worst_mae_pct",
            "test_trades",
            "test_win_rate",
            "test_total_return",
            "test_profit_factor",
        ]
        f.write(summary_df[cols].to_markdown(index=False))
        f.write("\n")

    print(summary_df.to_string(index=False))
    print(f"Saved validation under {OUT_DIR}")


if __name__ == "__main__":
    main()
