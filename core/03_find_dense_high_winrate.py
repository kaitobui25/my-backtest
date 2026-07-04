from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.backtest.config import DENSE_MIN_TRADES_PER_DAY, DENSE_MIN_WIN_RATE, FEE_PER_SIDE, TEST_START
from app.backtest.paths import DATA_ROOT, OUT_DIR as BASE_OUT_DIR
from app.backtest.runner import run_search


OUT_DIR = BASE_OUT_DIR / "dense_high_winrate"


def write_report(df) -> None:
    report = OUT_DIR / "summary.md"
    with report.open("w", encoding="utf-8") as f:
        f.write("# Dense High-Winrate BTCUSD Search\n\n")
        f.write(f"- Data root: `{DATA_ROOT}`\n")
        f.write(f"- Test/OOS starts: `{TEST_START.date()}`\n")
        f.write(f"- Fee model: `{FEE_PER_SIDE * 100:.3f}%` per side, `{FEE_PER_SIDE * 200:.3f}%` round trip.\n")
        f.write("- Entry signals are shifted one candle and filled at next candle open.\n")
        f.write("- TP/SL use OHLC high/low. If TP and SL touch in the same candle, SL is assumed first.\n")
        f.write("- `max_hold` is capped at one day for each timeframe.\n")
        f.write(f"- Frequency filter: full and OOS `trades_per_day >= {DENSE_MIN_TRADES_PER_DAY}`.\n")
        f.write(f"- Winrate filter: full and OOS winrate >= `{DENSE_MIN_WIN_RATE}%`.\n")
        f.write("- Equity compounds trade returns only, without mark-to-market drawdown between exits.\n\n")

        if df.empty:
            f.write("No candidate passed the filters.\n")
            return

        cols = [
            "timeframe",
            "params",
            "side_mode",
            "sl",
            "tp",
            "max_hold",
            "trades",
            "win_rate",
            "profit_factor",
            "total_return",
            "max_drawdown",
            "trades_per_day",
            "max_gap_days",
            "test_trades",
            "test_win_rate",
            "test_profit_factor",
            "test_total_return",
            "test_trades_per_day",
            "test_max_gap_days",
            "score",
        ]
        f.write("## Top Candidates\n\n")
        f.write(df[cols].head(30).to_markdown(index=False))
        f.write("\n")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = run_search(mode="dense_high_winrate")
    df.to_csv(OUT_DIR / "candidates.csv", index=False)
    write_report(df)

    if df.empty:
        print("No candidates survived filters.")
        return

    print("\nTop candidates:")
    print(df.head(20).to_string(index=False))
    strict_gap = df[(df["max_gap_days"] <= 2.0) & (df["test_max_gap_days"] <= 2.0)]
    print(f"\nStrict max-gap <= 2 days candidates: {len(strict_gap)}")
    if not strict_gap.empty:
        print(strict_gap.head(20).to_string(index=False))
    print(f"\nSaved under {OUT_DIR}")


if __name__ == "__main__":
    main()
