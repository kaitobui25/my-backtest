from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.backtest.runner import REQUIRED_COLUMNS, run_search


def assert_required_columns(df) -> None:
    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise AssertionError(f"Missing required columns: {missing}")


def main() -> None:
    normal = run_search(
        timeframes=["M15"],
        mode="normal",
        filters={
            "max_signal_variants": 2,
            "sl_values": [0.010],
            "tp_values": [0.005],
            "max_holds": [48],
            "min_full_trades": {"M15": 0},
            "min_test_trades": {"M15": 0},
            "min_profit_factor": 0.0,
            "min_test_profit_factor": 0.0,
            "min_test_win_rate": 0.0,
        },
    )
    assert_required_columns(normal)

    dense = run_search(
        timeframes=["M15"],
        mode="dense_high_winrate",
        filters={
            "max_signal_variants": 2,
            "sl_values": [0.020],
            "tp_values": [0.0050],
            "max_holds": [16],
            "min_trades_per_day": 0.0,
            "min_test_trades_per_day": 0.0,
            "min_win_rate": 0.0,
            "min_test_win_rate": 0.0,
        },
    )
    assert_required_columns(dense)

    print(f"normal rows={len(normal)}, columns={len(normal.columns)}")
    print(f"dense rows={len(dense)}, columns={len(dense.columns)}")


if __name__ == "__main__":
    main()
