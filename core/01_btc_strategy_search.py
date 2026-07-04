from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.backtest.config import FEE_PER_SIDE, TEST_START
from app.backtest.paths import DATA_ROOT, OUT_DIR
from app.backtest.runner import run_search, summarize_buy_hold


def write_report(df, buy_hold) -> None:
    report = OUT_DIR / "summary.md"
    with report.open("w", encoding="utf-8") as f:
        f.write("# BTCUSD Strategy Search\n\n")
        f.write(f"- Data root: `{DATA_ROOT}`\n")
        f.write(f"- Test/OOS starts: `{TEST_START.date()}`\n")
        f.write(f"- Cost model: `{FEE_PER_SIDE * 100:.3f}%` per side, `{FEE_PER_SIDE * 200:.3f}%` round trip.\n")
        f.write("- Entry signals are shifted by one candle and filled at next candle open.\n")
        f.write("- TP/SL use OHLC high/low. If TP and SL touch in the same candle, SL is assumed first.\n")
        f.write("- Equity compounds trade returns only, without mark-to-market drawdown between exits.\n\n")
        f.write("## Buy And Hold Benchmark\n\n")
        f.write(buy_hold.to_markdown(index=False))

        if df.empty:
            f.write("\n\nNo candidate survived filters.\n")
            return

        high_wr = df[
            (df["win_rate"] >= 65)
            & (df["test_win_rate"] >= 58)
            & (df["profit_factor"] >= 1.20)
            & (df["test_profit_factor"] >= 1.10)
            & (df["test_total_return"] > 0)
        ].sort_values(["test_win_rate", "test_profit_factor", "test_total_return"], ascending=[False, False, False])

        high_profit = df[
            (df["profit_factor"] >= 1.25)
            & (df["test_profit_factor"] >= 1.15)
            & (df["test_total_return"] >= 10)
            & (df["test_win_rate"] >= 50)
        ].sort_values(["test_total_return", "test_profit_factor", "score"], ascending=[False, False, False])

        f.write("\n\n## Top Score Candidates\n\n")
        f.write(df.head(30).to_markdown(index=False))
        f.write("\n\n## High Winrate Candidates\n\n")
        f.write(high_wr.head(30).to_markdown(index=False) if not high_wr.empty else "No candidate passed high-winrate filters.\n")
        f.write("\n\n## High Profit Candidates\n\n")
        f.write(high_profit.head(30).to_markdown(index=False) if not high_profit.empty else "No candidate passed high-profit filters.\n")
        f.write("\n")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    buy_hold = summarize_buy_hold()
    buy_hold.to_csv(OUT_DIR / "buy_hold_benchmark.csv", index=False)

    df = run_search(mode="normal")
    if df.empty:
        write_report(df, buy_hold)
        print("No candidates survived filters.")
        return

    df.to_csv(OUT_DIR / "btc_candidates_all.csv", index=False)

    high_wr = df[
        (df["win_rate"] >= 65)
        & (df["test_win_rate"] >= 58)
        & (df["profit_factor"] >= 1.20)
        & (df["test_profit_factor"] >= 1.10)
        & (df["test_total_return"] > 0)
    ].sort_values(["test_win_rate", "test_profit_factor", "test_total_return"], ascending=[False, False, False])
    high_wr.to_csv(OUT_DIR / "btc_candidates_high_winrate.csv", index=False)

    high_profit = df[
        (df["profit_factor"] >= 1.25)
        & (df["test_profit_factor"] >= 1.15)
        & (df["test_total_return"] >= 10)
        & (df["test_win_rate"] >= 50)
    ].sort_values(["test_total_return", "test_profit_factor", "score"], ascending=[False, False, False])
    high_profit.to_csv(OUT_DIR / "btc_candidates_high_profit.csv", index=False)

    write_report(df, buy_hold)

    print("\nTop score:")
    print(df.head(20).to_string(index=False))
    print("\nHigh winrate:")
    print((high_wr.head(20) if not high_wr.empty else high_wr).to_string(index=False))
    print("\nHigh profit:")
    print((high_profit.head(20) if not high_profit.empty else high_profit).to_string(index=False))
    print(f"\nSaved under {OUT_DIR}")


if __name__ == "__main__":
    main()
