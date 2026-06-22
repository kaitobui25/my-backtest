from __future__ import annotations

import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .config import BacktestConfig


def pct(value: Any, digits: int = 2) -> str:
    try:
        if value is None or pd.isna(value):
            return ""
        return f"{float(value) * 100:.{digits}f}%"
    except Exception:
        return ""


def num(value: Any, digits: int = 2) -> str:
    try:
        if value is None or pd.isna(value):
            return ""
        return f"{float(value):.{digits}f}"
    except Exception:
        return ""


def markdown_table(df: pd.DataFrame, columns: list[str] | None = None) -> str:
    if df.empty:
        return "Khong co setup phu hop.\n"
    frame = df.copy()
    if columns:
        frame = frame[[c for c in columns if c in frame.columns]]
    headers = list(frame.columns)
    rows = [headers]
    for _, row in frame.iterrows():
        rows.append(["" if pd.isna(row[col]) else str(row[col]) for col in headers])
    widths = [max(len(str(r[i])) for r in rows) for i in range(len(headers))]
    out = []
    out.append("| " + " | ".join(str(headers[i]).ljust(widths[i]) for i in range(len(headers))) + " |")
    out.append("| " + " | ".join("-" * widths[i] for i in range(len(headers))) + " |")
    for row in rows[1:]:
        out.append("| " + " | ".join(str(row[i]).ljust(widths[i]) for i in range(len(headers))) + " |")
    return "\n".join(out) + "\n"


def prepare_simple_top(top: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in top.iterrows():
        rows.append(
            {
                "setup": row["setup_id"],
                "tf": row["timeframe"],
                "indicator": row["indicator"],
                "side": row["side_mode"],
                "SL": pct(row["stop_loss_pct"], 1),
                "TP": pct(row["take_profit_pct"], 1),
                "avg_thang": pct(row["full_avg_monthly_return"], 2),
                "thang_tot": pct(row["full_best_month"], 2),
                "thang_xau": pct(row["full_worst_month"], 2),
                "max_DD": pct(row["full_max_drawdown"], 2),
                "winrate": pct(row["full_winrate"], 2),
                "lenh_thang": num(row["full_avg_trades_per_month"], 2),
                "rui_ro": row["risk_level"],
                "ket_luan": row["conclusion"],
                "dat_target": "yes" if bool(row.get("target_achieved", False)) else "no",
                "why_selected": row.get("why_selected", ""),
                "why_not_live": row.get("why_not_live_trade_yet", ""),
            }
        )
    return pd.DataFrame(rows)


def write_reports(
    result_dir: Path,
    config: BacktestConfig,
    data_audit: pd.DataFrame,
    pine_audit: pd.DataFrame,
    kept: pd.DataFrame,
    rejected: pd.DataFrame,
    detail_artifacts: list[dict[str, Any]],
    common_reasons: Counter[str],
) -> tuple[Path, Path, Path]:
    result_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(config.path, result_dir / "run_config.toml")
    simple_path = result_dir / "report_simple_vi.md"
    detail_path = result_dir / "report_detail.md"
    detail_json_path = result_dir / "report_detail.json"
    groups = split_groups(kept, rejected, config)
    _write_simple_report(simple_path, config, groups)
    _write_detail_report(detail_path, config, data_audit, pine_audit, kept, rejected, detail_artifacts, common_reasons)
    _write_detail_json(detail_json_path, config, data_audit, pine_audit, kept, rejected, detail_artifacts, common_reasons)
    return simple_path, detail_path, detail_json_path


def split_groups(kept: pd.DataFrame, rejected: pd.DataFrame, config: BacktestConfig) -> dict[str, pd.DataFrame]:
    terminal_n = int(config.reporting.get("top_n_terminal", 5))
    suspicious_n = int(config.reporting.get("suspicious_top_n", 25))
    near_n = int(config.reporting.get("near_miss_top_n", 25))
    robust = kept.sort_values("score", ascending=False).head(terminal_n) if not kept.empty else kept
    suspicious = rejected[rejected.get("candidate_group", "") == "B_high_return_suspicious"] if not rejected.empty and "candidate_group" in rejected else pd.DataFrame()
    near = rejected[rejected.get("candidate_group", "") == "C_rejected_near_miss"] if not rejected.empty and "candidate_group" in rejected else pd.DataFrame()
    if not suspicious.empty:
        suspicious = suspicious.sort_values(["full_avg_monthly_return", "oos_avg_monthly_return", "score"], ascending=[False, False, False]).head(suspicious_n)
    if not near.empty:
        near = near.sort_values(["score", "oos_profit_factor", "oos_trades"], ascending=[False, False, False]).head(near_n)
    return {"robust": robust, "suspicious": suspicious, "near": near}


def _write_simple_report(path: Path, config: BacktestConfig, groups: dict[str, pd.DataFrame]) -> None:
    robust = groups["robust"]
    suspicious = groups["suspicious"].head(5)
    near = groups["near"].head(5)
    with path.open("w", encoding="utf-8") as f:
        f.write("# Backtest V8 - Report Don Gian\n\n")
        f.write(f"- Symbol: `{config.symbol}`\n")
        f.write(f"- Data: `{config.data_path}`\n")
        f.write(f"- Timeframes: `{', '.join(config.timeframes)}`\n")
        f.write(f"- Target: `{config.target_label}`.\n")
        f.write(f"- Phi/slippage: fee `{pct(config.fee_per_side, 3)}` moi chieu, slippage `{pct(config.slippage_per_side, 3)}` moi chieu.\n\n")
        if robust.empty or not bool(robust.get("target_achieved", pd.Series(dtype=bool)).any()):
            f.write(f"**Ket luan target:** Chua co setup robust nao dat target `{config.target_label}`.\n\n")
        else:
            f.write(f"**Ket luan target:** Co setup robust dat target `{config.target_label}`, van can forward test.\n\n")
        f.write("## A. Robust / Stable Setup\n\n")
        f.write(markdown_table(prepare_simple_top(robust)))
        f.write("\n## B. High-Return But Suspicious\n\n")
        f.write(markdown_table(prepare_simple_top(suspicious)))
        f.write("\n## C. Rejected But Gan Dat\n\n")
        f.write(markdown_table(prepare_simple_top(near)))
        f.write("\n## Cach Doc Nhanh\n\n")
        f.write("- Nhom A: qua hard filters full/train/OOS, nhung cot `dat_target` moi cho biet co dat target trong config khong.\n")
        f.write("- Nhom B: return cao nhung bi filter vi DD, it lenh, gap, OOS/train lech, PF ao, hoac inactive months.\n")
        f.write("- Nhom C: bi loai nhung gan dat, dung de nghien cuu them chua dung live.\n")


def _write_detail_report(
    path: Path,
    config: BacktestConfig,
    data_audit: pd.DataFrame,
    pine_audit: pd.DataFrame,
    kept: pd.DataFrame,
    rejected: pd.DataFrame,
    detail_artifacts: list[dict[str, Any]],
    common_reasons: Counter[str],
) -> None:
    groups = split_groups(kept, rejected, config)
    top = kept.sort_values("score", ascending=False).head(25) if not kept.empty else kept
    with path.open("w", encoding="utf-8") as f:
        f.write("# Backtest V8 - Report Chi Tiet\n\n")
        f.write("## Config Da Dung\n\n")
        f.write("- Config copy: `run_config.toml`\n")
        f.write(f"- Symbol: `{config.symbol}`\n")
        f.write(f"- Asset class: `{config.market.get('asset_class', '')}`\n")
        f.write(f"- Data path: `{config.data_path}`\n")
        f.write(f"- Date filter: `{config.market.get('start')}` -> `{config.market.get('end')}`\n")
        f.write(f"- Train end: `{config.validation.get('train_end')}`; OOS start: `{config.validation.get('oos_start')}`\n")
        f.write(f"- Position size: `{config.position_size_pct:.4f}` equity per trade\n")
        f.write("- Entry signals are shifted by `execution.entry_lag_bars`; default is 1 bar to avoid same-candle lookahead.\n")
        f.write("- TP/SL uses OHLC high/low. If TP and SL touch in the same candle, config decides priority; default is SL first.\n\n")
        f.write("## Data Audit\n\n")
        f.write(markdown_table(data_audit))
        f.write("\n## Pine/TradingView Audit\n\n")
        f.write("Raw Pine is reference only. Backtest uses only indicators that exist as Python modules under `indicators/`.\n\n")
        f.write(markdown_table(pine_audit, ["file", "mapped_indicators", "status", "notes"]))
        f.write("\n## Ket Qua Tong Quan\n\n")
        f.write(f"- Setup kept: `{len(kept)}`\n")
        f.write(f"- Setup rejected: `{len(rejected)}`\n")
        f.write(f"- A robust/stable: `{len(kept)}`\n")
        f.write(f"- B high-return suspicious: `{len(rejected[rejected['candidate_group'] == 'B_high_return_suspicious']) if not rejected.empty and 'candidate_group' in rejected else 0}`\n")
        f.write(f"- C rejected near-miss: `{len(rejected[rejected['candidate_group'] == 'C_rejected_near_miss']) if not rejected.empty and 'candidate_group' in rejected else 0}`\n")
        if kept.empty or not bool(kept.get("target_achieved", pd.Series(dtype=bool)).any()):
            f.write(f"- Target `{config.target_label}`: `NOT MET` by robust setups.\n")
        else:
            f.write(f"- Target `{config.target_label}`: `MET` by at least one robust setup.\n")
        if common_reasons:
            f.write("- Ly do bi loai pho bien:\n")
            for reason, count in common_reasons.most_common(12):
                f.write(f"  - `{reason}`: {count}\n")
        f.write("\n## A. Robust / Stable Setup\n\n")
        display = top.copy()
        if not display.empty:
            for col in ["full_avg_monthly_return", "full_best_month", "full_worst_month", "full_max_drawdown", "full_winrate", "oos_avg_monthly_return", "oos_max_drawdown", "train_avg_monthly_return"]:
                if col in display:
                    display[col] = display[col].map(lambda x: pct(x))
            if "score" in display:
                display["score"] = display["score"].map(lambda x: num(x, 2))
            cols = [
                "setup_id",
                "score",
                "timeframe",
                "indicator",
                "strategy",
                "side_mode",
                "stop_loss_pct",
                "take_profit_pct",
                "max_hold_bars",
                "full_trades",
                "full_avg_monthly_return",
                "full_max_drawdown",
                "full_winrate",
                "full_profit_factor",
                "train_avg_monthly_return",
                "oos_trades",
                "oos_avg_monthly_return",
                "oos_profit_factor",
                "target_achieved",
                "risk_level",
                "why_selected",
                "why_not_live_trade_yet",
                "warnings",
            ]
            f.write(markdown_table(display, cols))
        else:
            f.write("Khong co setup nao qua filter.\n")
        f.write("\n## B. High-Return But Suspicious Setup\n\n")
        f.write(_format_group_for_detail(groups["suspicious"]))
        f.write("\n## C. Rejected But Gan Dat\n\n")
        f.write(_format_group_for_detail(groups["near"]))
        f.write("\n## Artifact Chi Tiet Cho Top Setup\n\n")
        if detail_artifacts:
            f.write(markdown_table(pd.DataFrame(detail_artifacts), ["setup_id", "trade_log", "monthly_returns", "equity_curve", "meta"]))
        else:
            f.write("Khong co artifact top setup.\n")
        f.write("\n## File CSV/JSON\n\n")
        f.write("- `kept_setups.csv`: tat ca setup qua filter.\n")
        f.write("- `rejected_setups.csv`: setup bi loai va ly do.\n")
        f.write("- `data_audit.csv`: kiem tra du lieu.\n")
        f.write("- `pine_audit.csv`: trang thai Pine reference/converted/skipped.\n")
        f.write("- `report_detail.json`: ban doc may cho ChatGPT/developer.\n")


def _format_group_for_detail(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "Khong co setup trong nhom nay.\n"
    display = frame.copy()
    for col in ["full_avg_monthly_return", "train_avg_monthly_return", "oos_avg_monthly_return", "full_max_drawdown", "oos_max_drawdown", "full_winrate"]:
        if col in display:
            display[col] = display[col].map(lambda x: pct(x))
    if "score" in display:
        display["score"] = display["score"].map(lambda x: num(x, 2))
    cols = [
        "setup_id",
        "score",
        "timeframe",
        "indicator",
        "side_mode",
        "full_avg_monthly_return",
        "train_avg_monthly_return",
        "oos_avg_monthly_return",
        "oos_trades",
        "full_profit_factor",
        "oos_profit_factor",
        "full_max_drawdown",
        "oos_max_drawdown",
        "rejection_reasons",
        "why_not_live_trade_yet",
    ]
    return markdown_table(display, cols)


def _write_detail_json(
    path: Path,
    config: BacktestConfig,
    data_audit: pd.DataFrame,
    pine_audit: pd.DataFrame,
    kept: pd.DataFrame,
    rejected: pd.DataFrame,
    detail_artifacts: list[dict[str, Any]],
    common_reasons: Counter[str],
) -> None:
    payload = {
        "config": config.raw,
        "result_files": {
            "kept_setups": "kept_setups.csv",
            "rejected_setups": "rejected_setups.csv",
            "data_audit": "data_audit.csv",
            "pine_audit": "pine_audit.csv",
        },
        "counts": {"kept": len(kept), "rejected": len(rejected), "tested": len(kept) + len(rejected)},
        "common_rejection_reasons": dict(common_reasons.most_common()),
        "top_setups": json_safe_records(kept.sort_values("score", ascending=False).head(25) if not kept.empty else kept),
        "groups": {
            "A_robust_stable": json_safe_records(kept.sort_values("score", ascending=False).head(50) if not kept.empty else kept),
            "B_high_return_suspicious": json_safe_records(split_groups(kept, rejected, config)["suspicious"]),
            "C_rejected_near_miss": json_safe_records(split_groups(kept, rejected, config)["near"]),
        },
        "detail_artifacts": detail_artifacts,
        "data_audit": json_safe_records(data_audit),
        "pine_audit": json_safe_records(pine_audit),
    }
    with path.open("w", encoding="utf-8") as f:
        json.dump(to_jsonable(payload), f, ensure_ascii=False, indent=2)


def json_safe_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return [to_jsonable(row) for row in df.to_dict(orient="records")]


def to_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_jsonable(v) for v in value]
    if isinstance(value, tuple):
        return [to_jsonable(v) for v in value]
    if isinstance(value, (pd.Timestamp, pd.Period, Path)):
        return str(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, float) and not np.isfinite(value):
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return value
