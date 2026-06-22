# Blind Historical Test — XAUUSD M15 (Jan2022–Jul2023)

> **Mục đích**: Áp dụng các setup đã tìm được từ WFO (Sep2023–Apr2026) vào
> dataset lịch sử hoàn toàn chưa từng dùng trong training. Đây là kiểm tra tính
> tổng quát (generalization) của chiến lược.

## Thông số Blind Test

| Item                | Giá trị                               |
|---------------------|---------------------------------------|
| Holdout data        | XAUUSD_M15_before_aug2023.parquet     |
| Holdout range       | 2022-01-14 → 2023-07-31 |
| Holdout bars        | 36,352                              |
| WFO source          | Sep2023–Apr2026 (13 folds, ~672 configs) |
| Re-optimization     | **ZERO** — params locked from WFO     |
| Risk per trade      | 1% equity                             |

---

## Kết quả Blind Test vs WFO Reference

| ID | Setup | Blind WR% | WFO WR% | Δ WR | Blind Calmar | WFO Calmar | Δ Calmar | Blind Ret% | WFO Ret% | Verdict |
|----|-------|----------:|--------:|-----:|-------------:|-----------:|---------:|-----------:|---------:|---------|
| A | SUPERTREND_2 FIXED SL=2.0 RR=2.0 | 33.9 | 37.4 | -3.5 | 0.17 | 13.01 | -12.84 | 6.2 | 273.1 | WARN   ⚠️ |
| B | RSI_REV FIXED SL=1.5 RR=1.5 | 37.4 | 45.2 | -7.8 | -0.17 | 3.32 | -3.49 | -17.2 | 54.2 | FAIL   ❌ |
| C | TRIPLE_EMA FIXED SL=0.75 RR=1.5 | 40.7 | 42.5 | -1.8 | 0.26 | 4.60 | -4.34 | 9.2 | 78.7 | WARN   ⚠️ |
| D | SUPERTREND_2 FIXED SL=1.0 RR=3.0 | 22.9 | 27.3 | -4.4 | -0.69 | 7.58 | -8.27 | -68.9 | 236.1 | FAIL   ❌ |
| E | RSI_REV FIXED SL=1.5 RR=3.0 | 23.4 | 30.6 | -7.2 | -0.18 | 5.53 | -5.71 | -17.8 | 98.0 | FAIL   ❌ |

---

## Chi tiết từng Setup

### [A] SUPERTREND_2 | FIXED | SL=2.0 | RR=2.0  [Top1 Calmar=13.01]

| Metric       | Blind Test | WFO Ref  | Delta     |
|--------------|------------|----------|-----------|
| Win Rate     | 33.89%     | 37.40% | -3.51%  |
| Calmar Ratio | 0.173      | 13.010  | -12.837   |
| Sharpe       | 0.353      | —        | —         |
| Total Return | 6.20%    | 273.10% | -266.90% |
| Max Drawdown | 35.86%    | 21.00% | +14.86% |
| Avg R/trade  | 0.0167     | —        | —         |
| Trades       | 897         | —        | —         |

> **Verdict**: WARN   ⚠️  — Degraded but still positive

### [B] RSI_REV | FIXED | SL=1.5 | RR=1.5 | EMA200+ADX25  [WR>=45%, Calmar=3.32]

| Metric       | Blind Test | WFO Ref  | Delta     |
|--------------|------------|----------|-----------|
| Win Rate     | 37.35%     | 45.20% | -7.85%  |
| Calmar Ratio | -0.172      | 3.320  | -3.492   |
| Sharpe       | -0.877      | —        | —         |
| Total Return | -17.20%    | 54.20% | -71.40% |
| Max Drawdown | 27.96%    | 16.30% | +11.66% |
| Avg R/trade  | -0.0661     | —        | —         |
| Trades       | 257         | —        | —         |

> **Verdict**: FAIL   ❌  — Negative return on blind data

### [C] TRIPLE_EMA | FIXED | SL=0.75 | RR=1.5 | EMA200  [Best WFO fold5]

| Metric       | Blind Test | WFO Ref  | Delta     |
|--------------|------------|----------|-----------|
| Win Rate     | 40.73%     | 42.50% | -1.77%  |
| Calmar Ratio | 0.265      | 4.600  | -4.335   |
| Sharpe       | 0.425      | —        | —         |
| Total Return | 9.19%    | 78.70% | -69.51% |
| Max Drawdown | 34.71%    | 17.10% | +17.61% |
| Avg R/trade  | 0.0182     | —        | —         |
| Trades       | 825         | —        | —         |

> **Verdict**: WARN   ⚠️  — Degraded but still positive

### [D] SUPERTREND_2 | FIXED | SL=1.0 | RR=3.0  [Top2 Calmar=7.58]

| Metric       | Blind Test | WFO Ref  | Delta     |
|--------------|------------|----------|-----------|
| Win Rate     | 22.92%     | 27.30% | -4.38%  |
| Calmar Ratio | -0.689      | 7.580  | -8.269   |
| Sharpe       | -1.714      | —        | —         |
| Total Return | -68.92%    | 236.10% | -305.02% |
| Max Drawdown | 72.77%    | 31.10% | +41.67% |
| Avg R/trade  | -0.0831     | —        | —         |
| Trades       | 1,204         | —        | —         |

> **Verdict**: FAIL   ❌  — Negative return on blind data

### [E] RSI_REV | FIXED | SL=1.5 | RR=3.0 | EMA200+ADX25  [Top9 Calmar=5.53]

| Metric       | Blind Test | WFO Ref  | Delta     |
|--------------|------------|----------|-----------|
| Win Rate     | 23.44%     | 30.60% | -7.16%  |
| Calmar Ratio | -0.178      | 5.530  | -5.708   |
| Sharpe       | -0.590      | —        | —         |
| Total Return | -17.83%    | 98.00% | -115.83% |
| Max Drawdown | 28.36%    | 17.70% | +10.66% |
| Avg R/trade  | -0.0625     | —        | —         |
| Trades       | 256         | —        | —         |

> **Verdict**: FAIL   ❌  — Negative return on blind data

---

## Kết luận

*(Tự động generate — xem chi tiết tại `blind_test_hist_summary.csv`)*

- **0 setup(s) PASS** — metrics giữ được trên dữ liệu chưa thấy
- **2 setup(s) WARN** — degraded nhưng vẫn dương
- **3 setup(s) FAIL/WEAK** — không maintain trên holdout

### Nhận định Tổng thể
Không setup nào pass đầy đủ — **overfit cảnh báo**. Xem xét thêm regularization.

---

*Generated: 2026-04-12 22:52 JST*