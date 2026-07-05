# Plan nâng cấp normal mode giống dense_high_winrate

## Mục tiêu

Nâng cấp normal mode để dùng engine:
simulate_many_configs_with_entries_summary()

Sau nâng cấp, normal mode phải có hành vi giống dense_high_winrate ở phần engine:

1. Khi mở lệnh tại open_[i], check luôn hit_sl / hit_tp trong cùng candle entry.
2. Nếu vừa entry vừa hit SL/TP trong candle đó:
   - đóng lệnh ngay tại candle i
   - bars_held = 0
   - entry_idx = i
   - exit_idx = i
3. Nếu cùng candle vừa hit SL vừa hit TP thì ưu tiên SL trước, giống dense.
4. Normal result phải có đủ:
   - trades_per_day
   - max_gap_days
   - avg_bars_held
   - test_trades_per_day
   - test_max_gap_days
   - test_avg_bars_held
5. Giữ nguyên filter/score normal hiện tại, không biến normal thành dense filter.

---

## File cần sửa

### 1. app/backtest/runner.py

Hiện tại:
- normal dùng simulate_many_configs_summary()
- dense dùng simulate_many_configs_with_entries_summary()

Cần sửa evaluate_normal_timeframe().

Trong evaluate_normal_timeframe(), sau đoạn:

open_ = df["open"].to_numpy(np.float64)
high = df["high"].to_numpy(np.float64)
low = df["low"].to_numpy(np.float64)
close = df["close"].to_numpy(np.float64)
test_start_idx = int(np.searchsorted(df.index.to_numpy(), np.datetime64(TEST_START), side="left"))

thêm:

index_ns = df.index.astype("datetime64[ns]").asi8.astype(np.int64, copy=False)
is_test_exit = index_ns >= np.datetime64(TEST_START).astype("datetime64[ns]").astype(np.int64)
days = calendar_days_ns(index_ns)
test_days = calendar_days_ns(index_ns, is_test_exit)

Sau đó thay call:

simulate_many_configs_summary(...)

bằng:

simulate_many_configs_with_entries_summary(
    open_, high, low, close, longs, shorts,
    sl_arr, tp_arr, mh_arr, FEE_PER_SIDE,
    test_start_idx, index_ns, days, test_days,
)

Nhận thêm các output:

(
    tr_arr, wr_arr, tre_arr, pf_arr, exp_arr, mdd_arr, aw_arr, al_arr,
    tpd_arr, mgd_arr, abh_arr,
    ttr_arr, twr_arr, tre2_arr, tpf2_arr, texp_arr,
    ttpd_arr, tmgd_arr, tabh_arr,
)

Sau đó truyền thêm các array mới vào batch_to_normal_rows().

Lưu ý:
- Không đổi min_full_trades/min_test_trades của normal.
- Không đổi min_test_win_rate, min_profit_factor, min_test_profit_factor.
- Không dùng min_trades_per_day làm filter bắt buộc cho normal, trừ khi user truyền filter ngoài API.

---

### 2. app/backtest/result_builder.py

Hiện tại batch_to_normal_rows() chỉ nhận metric cơ bản:

trades, win_rate, total_return, profit_factor, expectancy, max_drawdown,
avg_win, avg_loss,
test_trades, test_win_rate, test_total_return, test_profit_factor, test_expectancy

Cần mở rộng signature của batch_to_normal_rows() để nhận thêm:

trades_per_day_arr
max_gap_days_arr
avg_bars_held_arr
test_trades_per_day_arr
test_max_gap_days_arr
test_avg_bars_held_arr

Trong row append, thêm:

"trades_per_day": trades_per_day_arr[c],
"max_gap_days": float(max_gap_days_arr[c]),
"avg_bars_held": float(avg_bars_held_arr[c]),
"test_trades_per_day": test_trades_per_day_arr[c],
"test_max_gap_days": float(test_max_gap_days_arr[c]),
"test_avg_bars_held": float(test_avg_bars_held_arr[c]),

Giữ score normal hiện tại:

score_candidate(...)

Không chuyển sang score_dense_candidate(), vì nếu đổi score thì thứ tự normal sẽ thay đổi quá mạnh.

---

### 3. app/backtest/batch_engine.py

Không nhất thiết phải sửa nếu simulate_many_configs_with_entries_summary() đã ổn.

Nhưng cần kiểm tra kỹ logic hiện tại:

Long entry:
- entry = open_[i]
- sl_price = entry * (1.0 - sl)
- tp_price = entry * (1.0 + tp)
- hit_sl = low[i] <= sl_price
- hit_tp = high[i] >= tp_price
- nếu hit_sl hoặc hit_tp thì đóng ngay, bars_buf = 0

Short entry:
- entry = open_[i]
- sl_price = entry * (1.0 + sl)
- tp_price = entry * (1.0 - tp)
- hit_sl = high[i] >= sl_price
- hit_tp = low[i] <= tp_price
- nếu hit_sl hoặc hit_tp thì đóng ngay, bars_buf = 0

Nếu cả SL và TP cùng hit, logic đang ưu tiên SL vì check:

if hit_sl:
    exit_price = sl_price
else:
    exit_price = tp_price

=> Giữ nguyên.

---

### 4. app/backtest/config.py

Có thể không cần sửa.

REQUIRED_COLUMNS hiện đã có sẵn:
- trades_per_day
- max_gap_days
- avg_bars_held
- test_trades_per_day
- test_max_gap_days
- test_avg_bars_held

Nghĩa là API/table đã có chỗ chứa cột, nhưng normal hiện tại đang bị NaN vì batch_to_normal_rows() không xuất các field này.

---

### 5. app/api/routes_options.py

Có thể không cần sửa.

FILTER_FIELDS hiện đã có sẵn:
- trades_per_day
- max_gap_days
- avg_bars_held
- test_trades_per_day
- test_max_gap_days
- test_avg_bars_held

Sau khi normal trả đủ field, frontend/API filter sẽ dùng được luôn.

---

## Test cần làm

### Test 1: normal mode không còn NaN ở cột dense-style

Gọi API:

POST /api/backtest
{
  "symbol": "BTCUSD",
  "timeframes": ["M15"],
  "mode": "normal",
  "strategies": ["EMA_PULLBACK"],
  "filters": [],
  "limit": 20
}

Kỳ vọng:
- columns có:
  - trades_per_day
  - max_gap_days
  - avg_bars_held
  - test_trades_per_day
  - test_max_gap_days
  - test_avg_bars_held
- các row normal có giá trị số, không còn toàn null/NaN.

---

### Test 2: same-candle entry SL/TP

Tạo unit test nhỏ cho engine:

Data giả:
- open[0] = 100
- high[0] = 106
- low[0] = 94
- close[0] = 101
- long_entries[0] = True
- sl = 0.05
- tp = 0.05

Vì candle entry vừa hit SL 95 vừa hit TP 105.
Kỳ vọng:
- trade count = 1
- return là SL trước, khoảng -5% trừ fee
- bars_held = 0
- entry_idx = 0
- exit_idx = 0

Với normal sau nâng cấp, kết quả phải giống dense.

---

### Test 3: compare normal trước/sau

Chạy cùng request normal trước và sau sửa.

Kỳ vọng:
- Số candidate có thể thay đổi.
- win_rate/return có thể thay đổi.
- Lý do: trước đây lệnh entry ở open_[i] nhưng không check high/low của candle i, nên có thể bỏ sót SL/TP ngay candle entry.
- Đây là thay đổi đúng, không phải bug.

---

## Thứ tự làm hợp lý

1. Sửa runner.py trước.
2. Sửa result_builder.py để nhận thêm metric.
3. Chạy backend import check:
   python -m compileall app
4. Chạy API normal M15 limit nhỏ.
5. So sánh normal với dense xem columns đồng nhất.
6. Thêm unit test same-candle entry.
7. Commit với message:
   "Use entry-aware batch engine for normal mode"

---

## Lưu ý quan trọng cho agent

Không được sửa signal logic.
Không được sửa grid normal.
Không được đổi score normal sang score_dense_candidate().
Không được biến normal thành dense filter.
Chỉ thay engine normal từ simulate_many_configs_summary() sang simulate_many_configs_with_entries_summary() và map thêm các metric mới vào row.
