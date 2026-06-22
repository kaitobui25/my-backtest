"""
03_fvg_m3_optimization.py
Tìm kiếm điểm tối ưu cho chiến lược FVG kết hợp các indicator trên khung M3
Mục tiêu:
- Winrate > 45%
- Lợi nhuận cao nhất có thể
- Ưu tiên chốt 1/2 vốn tại 2R

Thực hiện qua quy trình WFO (Walk-Forward Optimization) để giảm thiểu overfitting.
"""

import os
import sys
import time
import numpy as np
import pandas as pd
import warnings

warnings.filterwarnings("ignore")

# Thiết lập đường dẫn file module `core`
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CORE_DIR = os.path.join(BASE_DIR, "core")
sys.path.insert(0, CORE_DIR)

import vectorbt as vbt
from signals import calc_atr_rma, calc_adx, fvg_nb
from wfo_engine import generate_folds, run_sweep

def main():
    import sys
    if sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')

    print("=" * 72)
    print("  FVG M3 OPTIMIZATION (WR > 45%, MAX PROFIT, PARTIAL_TP@2R)  ")
    print("=" * 72)
    
    # 1. Đọc dữ liệu
    DATA_PATH = r"d:\Phong\03_Finance\trade\vectorbt-master\my-data\cache\m3\XAUUSD.sml_M3_60000_before_20251001.parquet"
    if not os.path.exists(DATA_PATH):
        print(f"[!] Không tìm thấy file dữ liệu {DATA_PATH}")
        return

    df = pd.read_parquet(DATA_PATH)
    print(f"\n[1/4] Đã tải file parquet: {len(df):,} hàng.")
    print(f"      Từ {df.index[0]} đến {df.index[-1]}")
    
    # 2. Tạo Folds (WFO)
    folds = generate_folds(df.index, train_months=2, test_months=1)
    if not folds:
        print("\n[!] Dữ liệu không đủ cho 2M Train / 1M Test. Chuyển sang 1.5M Train / 0.5M Test...")
        folds = generate_folds(df.index, train_months=1, test_months=1)
    
    print(f"      Số lượng folds (Cross-Validation) được tạo: {len(folds)}")
    for i, (tr_s, tr_e, te_s, te_e) in enumerate(folds):
        print(f"        Fold {i+1}: Train [{df.index[tr_s].date()} -> {df.index[tr_e-1].date()}] | "
              f"OOS [{df.index[te_s].date()} -> {df.index[te_e-1].date()}]")

    # 3. Tính Toán Chỉ Báo Cơ Bản (Global Indicators)
    print("\n[2/4] Tính toán các chỉ báo (Indicators)...")
    atr200 = calc_atr_rma(df["high"], df["low"], df["close"], period=200)
    adx14  = calc_adx(df["high"], df["low"], df["close"], period=14)
    
    # Tính tín hiệu FVG gốc một lần duy nhất
    fvg_raw = fvg_nb(df["high"].values, df["low"].values, df["close"].values, atr200, filter_width=0.1)
    registry = {"FVG": fvg_raw}
    
    # 4. Cài Đặt Tham Số Lưới (Grid Setup)
    sl_mults    = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]
    adx_threshs = [0, 15, 20, 25, 30]
    ema_periods = [0, 50, 100, 200]
    waits       = [2, 3, 5]
    
    all_sweep_results = []
    
    print("\n[3/4] Quét tham số chiến lược (Grid Sweep)...")
    for ema_p in ema_periods:
        print(f"      Quyét với bộ lọc EMA = {ema_p if ema_p > 0 else 'Tắt'}...")
        if ema_p > 0:
            ema_arr = vbt.MA.run(df["close"], ema_p, ewm=True).ma.values
        else:
            ema_arr = np.zeros(len(df)) # Để vượt qua rule lọc kết hợp
            
        configs = []
        for sl in sl_mults:
            for adx_t in adx_threshs:
                for wait in waits:
                    configs.append({
                        "signal":       "FVG",
                        "mode":         "PARTIAL_TP",
                        "sl_mult":      sl,
                        "rr":           2.0,   # KHÔNG quan trọng trong mode PARTIAL_TP sử dụng tp1_rr
                        "ema_filter":   ema_p, # Trick: Dùng ema_p để phân biệt tham số
                        "adx_thresh":   adx_t,
                        "wait_candles": wait,
                        "tp1_rr":       2.0,   # Chốt 1/2 vốn tại mục tiêu 2R
                    })
                    
        # Gọi hàm run_sweep từ wfo_engine
        sweep = run_sweep(
            df, atr200, adx14, ema_arr, registry, folds, configs,
            min_oos_trades=5, min_valid_folds=1
        )
        all_sweep_results.extend(sweep)
        
    print(f"\n[4/4] Đánh giá kết quả: {len(all_sweep_results)} bộ tổ hợp khả thi.")
    
    # Lọc Winrate > 45% (0.45)
    passing_wr = [r for r in all_sweep_results if r["avg_wr"] >= 0.45]
    print(f"      Số lượng cấu hình thỏa mãn OOS Winrate >= 45%: {len(passing_wr)}")
    
    if passing_wr:
        # Ưu tiên tiêu chí lợi nhuận (Total OOS Return)
        passing_wr.sort(key=lambda x: x["agg_total_ret"], reverse=True)
        top_setups = passing_wr[:20]
    else:
        print("      [Cảnh báo] Không có cấu hình nào giữ được Winrate >= 45%. Sắp xếp theo lợi nhuận mặc định...")
        # Nếu không đạt 45%, vẫn xếp hạng dựa theo Lợi Nhuận lớn nhất để tham khảo
        all_sweep_results.sort(key=lambda x: x["agg_total_ret"], reverse=True)
        top_setups = all_sweep_results[:20]
        
    # Kết quả
    print("\n" + "=" * 88)
    print(f"{'TOP CẤU HÌNH KẾT HỢP FVG M3 (Sắp xếp theo Lợi Nhuận Net)':^88}")
    print("=" * 88)
    hdr = (f"{'Hạng':>5} {'Chế độ':<11} {'SL(ATR)':>8} {'EMA':>5} {'ADX':>5} "
           f"{'Wait':>5} | {'WR%':>6} {'LợiNhuận%':>10} {'DD%':>7} "
           f"{'Calmar':>7} {'Trades':>6}")
    print(hdr)
    print("-" * 88)
    
    for i, r in enumerate(top_setups, 1):
        c = r["cfg"]
        print(f"{i:>5} {c['mode']:<11} {c['sl_mult']:>8.2f} {c['ema_filter']:>5} {c['adx_thresh']:>5} "
              f"{c['wait_candles']:>5} | {r['avg_wr']*100:>6.1f} {r['agg_total_ret']*100:>10.1f} "
              f"{r['agg_max_dd']*100:>7.1f} {r['agg_calmar']:>7.2f} {r['total_oos_trades']:>6}")
        
    # Export thành phần Output
    RESULT_DIR = os.path.join(BASE_DIR, "result")
    os.makedirs(RESULT_DIR, exist_ok=True)
    out_path = os.path.join(RESULT_DIR, "03_fvg_m3_top_strategies.csv")
    
    rows = []
    for rank, r in enumerate(top_setups, 1):
        c = r["cfg"]
        rows.append({
            "rank": rank,
            "signal": c["signal"],
            "mode": c["mode"],
            "sl_mult": c["sl_mult"],
            "ema_filter": c["ema_filter"],
            "adx_thresh": c["adx_thresh"],
            "wait_candles": c["wait_candles"],
            "tp1_rr": c["tp1_rr"],
            "avg_wr_pct": round(r["avg_wr"]*100, 2),
            "agg_total_ret_pct": round(r["agg_total_ret"]*100, 2),
            "agg_max_dd_pct": round(r["agg_max_dd"]*100, 2),
            "agg_calmar": round(r["agg_calmar"], 3),
            "agg_sharpe": round(r["agg_sharpe"], 3),
            "total_oos_trades": r["total_oos_trades"]
        })
        
    df_out = pd.DataFrame(rows)
    df_out.to_csv(out_path, index=False)
    print(f"\n[OK] Đã lưu kết quả chi tiết vào: {out_path}")


if __name__ == "__main__":
    main()
