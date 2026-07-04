IMPLEMENT PLAN - INTERNAL BTC BACKTEST WEB API

Mục tiêu tổng thể:
Build web API nội bộ để chạy backtest BTC dễ nhìn, dễ lọc, sau này có UI kéo thả và lưu kết quả vào SQLite.
Ưu tiên: code gọn, dễ sửa module, không đụng nhiều file khi thêm indicator/strategy mới.

==================================================
PHASE 1 - REFACTOR BACKTEST CORE
==================================================

Mục tiêu:
Tách code backtest từ file 01 và 03 thành module sạch.
Không làm web, không làm SQLite, không làm UI.
Không đổi logic backtest hiện tại.

Cấu trúc cần tạo:

app/
  backtest/
    __init__.py
    config.py
    paths.py
    data_loader.py
    indicators.py
    signals.py
    engine.py
    metrics.py
    runner.py

Nội dung từng file:

1. app/backtest/config.py
- Chứa:
  - SYMBOL = "BTCUSD"
  - TEST_START
  - FEE_PER_SIDE
  - MIN_FULL_TRADES
  - MIN_TEST_TRADES
  - TIMEFRAMES
  - danh sách strategy hợp lệ
- Không chứa logic chạy backtest.

2. app/backtest/paths.py
- Chứa:
  - resolve_paths()
  - ROOT
  - DATA_ROOT
  - OUT_DIR
- Không tự ghi file output ngoài việc tạo folder nếu cần.

3. app/backtest/data_loader.py
- Chứa:
  - load_ohlc(timeframe: str) -> pd.DataFrame
- Lấy logic từ file 01.
- Nhiệm vụ:
  - đọc parquet
  - sort index
  - convert timezone nếu cần
  - trả về open/high/low/close/volume dạng float
- Không build signal ở đây.

4. app/backtest/indicators.py
- Chứa các indicator:
  - ema
  - rsi
  - atr
  - adx
  - calculate_supertrend
  - supertrend
  - macd
  - wavetrend
  - fast_linreg_val
  - squeeze_momentum
  - williams_vix_fix
- Giữ nguyên công thức hiện tại.
- Không thêm indicator mới trong phase này.

5. app/backtest/signals.py
- Chứa:
  - shift_signal
  - side_mode_arrays
  - build_signals
  - build_vol_expansion_signals
- `build_signals(df, timeframe)` trả list signal giống file 01.
- `build_vol_expansion_signals(df)` trả signal giống file 03.
- Không ghi CSV.
- Không print quá nhiều.
- Không chạy backtest trong file này.

6. app/backtest/engine.py
- Chứa Numba kernel:
  - simulate_trades
  - simulate_trades_with_entries
- Giữ nguyên rule:
  - entry signal shift 1 candle
  - fill ở next candle open
  - TP/SL dùng high/low
  - nếu TP và SL cùng chạm trong 1 candle thì SL trước
  - fee tính 2 chiều
- Không trả DataFrame ở kernel.
- Kernel chỉ trả numpy arrays.

7. app/backtest/metrics.py
- Chứa:
  - metrics
  - score_candidate
  - score_dense_candidate nếu cần
  - helper filter metric nếu cần
- Không phụ thuộc FastAPI.
- Không ghi file.

8. app/backtest/runner.py
- Đây là API nội bộ cho phase sau gọi.
- Cần có hàm chính:

  run_search(
      timeframes: list[str],
      mode: str = "normal",
      strategies: list[str] | None = None,
      filters: list[dict] | None = None,
      limit: int | None = None,
  ) -> pd.DataFrame

- mode:
  - "normal": dùng build_signals từ file 01
  - "dense_high_winrate": dùng build_vol_expansion_signals từ file 03
- Trả về DataFrame có cột chuẩn:

  timeframe
  strategy
  params
  side_mode
  sl
  tp
  max_hold
  trades
  win_rate
  total_return
  profit_factor
  expectancy
  max_drawdown
  avg_win
  avg_loss
  test_trades
  test_win_rate
  test_total_return
  test_profit_factor
  test_expectancy
  score

- Nếu mode dense có thêm:
  trades_per_day
  max_gap_days
  avg_bars_held
  test_trades_per_day
  test_max_gap_days
  test_avg_bars_held

- runner.py được phép dùng pandas DataFrame.
- runner.py không lưu CSV mặc định.
- Nếu cần wrapper script cũ thì wrapper mới gọi runner.py rồi tự save CSV riêng.

Smoke test Phase 1:
Tạo script:

scripts/smoke_backtest_core.py

Nội dung test:
- chạy run_search(timeframes=["M15"], mode="normal", strategies=["VOL_EXPANSION_CONT"], limit=20)
- assert DataFrame không lỗi
- assert có đủ cột chính
- print head
- không yêu cầu có candidate, vì filter có thể làm rỗng

Lệnh chạy:

python scripts/smoke_backtest_core.py

Done Phase 1 khi:
- Import module không lỗi.
- Smoke test chạy được.
- Kết quả logic không lệch bất thường so với file cũ.
- File 01/03 cũ nếu còn thì chỉ đóng vai trò wrapper, không còn là core chính.


==================================================
PHASE 2 - BUILD FASTAPI INTERNAL WEB API
==================================================

Mục tiêu:
Tạo API local để frontend gọi chạy backtest.
Chưa làm UI kéo thả.
Chưa SQLite.
Chưa save/load kết quả.
Không đổi logic backtest.

Cấu trúc cần tạo:

app/
  main.py
  api/
    __init__.py
    schemas.py
    routes_options.py
    routes_backtest.py
  backtest/
    ... core từ phase 1 ...

1. app/main.py
- Tạo FastAPI app.
- Add CORS cho local frontend:
  - http://localhost:3000
  - http://127.0.0.1:3000
  - http://localhost:5173
  - http://127.0.0.1:5173
- Include routers:
  - options router
  - backtest router
- Có endpoint:

  GET /api/health

Response:

  {"status": "ok"}

2. app/api/schemas.py
- Tạo Pydantic models:

BacktestFilter:
  field: str
  op: str
  value: float | int | str

BacktestRequest:
  symbol: str = "BTCUSD"
  timeframes: list[str]
  mode: str = "normal"
  strategies: list[str] | None = None
  filters: list[BacktestFilter] = []
  limit: int = 500

BacktestResponse:
  run_temp_id: str
  row_count: int
  columns: list[str]
  rows: list[dict]

3. app/api/routes_options.py
- Endpoint:

  GET /api/options

Response:

{
  "symbols": ["BTCUSD"],
  "timeframes": ["M15", "M30", "H1", "H2", "H4", "D1"],
  "modes": ["normal", "dense_high_winrate"],
  "indicators": [
    "EMA_PULLBACK",
    "DONCHIAN_BREAKOUT",
    "BB_RSI_REVERT",
    "IBS_REVERT",
    "VOL_EXPANSION_CONT",
    "SUPERTREND",
    "MACD_CROSS",
    "WAVETREND",
    "SQUEEZE_MOM",
    "WILLIAMS_VIX_FIX"
  ],
  "filter_fields": [
    "win_rate",
    "total_return",
    "profit_factor",
    "expectancy",
    "max_drawdown",
    "test_win_rate",
    "test_total_return",
    "test_profit_factor",
    "test_expectancy",
    "score"
  ],
  "operators": [">", ">=", "<", "<=", "=", "~"]
}

4. app/api/routes_backtest.py
- Endpoint:

  POST /api/backtest

Request mẫu:

{
  "symbol": "BTCUSD",
  "timeframes": ["M15", "M30"],
  "mode": "normal",
  "strategies": ["VOL_EXPANSION_CONT", "IBS_REVERT"],
  "filters": [
    {"field": "win_rate", "op": ">=", "value": 65},
    {"field": "profit_factor", "op": ">=", "value": 1.2}
  ],
  "limit": 500
}

Response mẫu:

{
  "run_temp_id": "uuid",
  "row_count": 123,
  "columns": ["timeframe", "strategy", "params", "..."],
  "rows": [
    {
      "timeframe": "M15",
      "strategy": "VOL_EXPANSION_CONT",
      "params": "...",
      "side_mode": "both",
      "sl": 0.03,
      "tp": 0.01,
      "max_hold": 96,
      "trades": 120,
      "win_rate": 75.2,
      "total_return": 88.5,
      "profit_factor": 1.35,
      "expectancy": 0.21,
      "max_drawdown": -12.3,
      "test_trades": 40,
      "test_win_rate": 76.1,
      "test_total_return": 20.5,
      "test_profit_factor": 1.25,
      "test_expectancy": 0.18,
      "score": 123.4
    }
  ]
}

Yêu cầu backend:
- Gọi app.backtest.runner.run_search(...)
- Không ghi SQLite.
- Không ghi CSV.
- Không giữ signal arrays.
- run_temp_id chỉ là UUID tạm để frontend biết đây là lần chạy nào.
- Kết quả chỉ trả về JSON.

Validate:
- symbol khác BTCUSD thì báo 400.
- timeframe không nằm trong options thì báo 400.
- mode không hợp lệ thì báo 400.
- filter field không hợp lệ thì báo 400.
- operator không hợp lệ thì báo 400.
- limit <= 0 thì báo 400.
- limit quá lớn thì cap hoặc báo 400, ví dụ max 5000.

JSON clean:
- NaN -> null
- inf -> null hoặc string "inf", ưu tiên null
- datetime -> string
- numpy int/float -> Python int/float

Helper cần có:
- dataframe_to_json_rows(df)
- apply_filters(df, filters)
- validate_backtest_request(request)

Lệnh chạy dev:

uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

Test bằng browser:
- http://127.0.0.1:8000/docs
- GET /api/health
- GET /api/options
- POST /api/backtest

Done Phase 2 khi:
- Swagger mở được.
- /api/health trả ok.
- /api/options trả đủ options.
- /api/backtest chạy được với request mẫu.
- Response không lỗi JSON vì NaN/inf.
- Không có SQLite trong phase này.


==================================================
PHASE 3 - SIMPLE FRONTEND UI
==================================================

Mục tiêu:
Tạo UI nội bộ đơn giản để gọi API.
Chưa cần đẹp.
Ưu tiên dùng được.

Cấu trúc đề xuất:

frontend/
  index.html
  src/
    main.js
    api.js
    state.js
    dragdrop.js
    table.js
    style.css

Giao diện:
Chia 2 phần trên dưới.

Phần trên:
- Cột 1: Timeframes
- Cột 2: Indicators/Strategies
- Cột 3: Selected setup
- Cột 4: Filters

Cột 1:
- M15
- M30
- H1
- H2
- H4
- D1

Cột 2:
- EMA_PULLBACK
- DONCHIAN_BREAKOUT
- BB_RSI_REVERT
- IBS_REVERT
- VOL_EXPANSION_CONT
- SUPERTREND
- MACD_CROSS
- WAVETREND
- SQUEEZE_MOM
- WILLIAMS_VIX_FIX

Cột 3:
- Kéo timeframe và strategy vào đây.
- Có nút remove từng item.
- Có nút clear.

Cột 4:
- Filter row gồm:
  - field select
  - operator select: >, >=, <, <=, =, ~
  - value input
- Có nút add filter
- Có nút remove filter

Nút:
- Run Backtest

Khi bấm Run Backtest:
- Gọi POST /api/backtest
- Hiện loading
- Disable nút trong lúc chạy
- Nhận response
- Render bảng kết quả xuống phần dưới

Phần dưới:
- Result table
- Có:
  - sort column
  - search text
  - hide/show column
  - copy selected rows
  - checkbox mỗi dòng
  - rating 1-5 sao mỗi dòng
  - font size + / -
  - Save button nhưng Phase 3 có thể để disabled hoặc alert "Phase 4"

Table columns mặc định nên hiện:
- selected
- rating
- timeframe
- strategy
- params
- side_mode
- sl
- tp
- max_hold
- trades
- win_rate
- total_return
- profit_factor
- expectancy
- max_drawdown
- test_trades
- test_win_rate
- test_total_return
- test_profit_factor
- score

Không làm:
- Không chart.
- Không login.
- Không SQLite.
- Không lưu lâu dài.
- Không dùng framework phức tạp nếu không cần.

Done Phase 3 khi:
- Chọn timeframe/strategy được.
- Gọi API được.
- Bảng hiện kết quả.
- Check/rating hoạt động trong frontend state tạm.
- Reload trang thì mất kết quả, chấp nhận.


==================================================
PHASE 4 - SQLITE SAVE/LOAD RESULT
==================================================

Mục tiêu:
Chỉ lưu kết quả backtest khi user bấm Save.
Không lưu signal arrays.
Không lưu toàn bộ quá trình test.
Chỉ lưu result table + metadata lần chạy + rating/check/note.

Quan trọng:
Không tạo bảng riêng mỗi lần backtest.
Dùng run_id để phân biệt.
SQLite chỉ có bảng cố định.

Cấu trúc thêm:

app/
  storage/
    __init__.py
    db.py
    schema.py
    repository.py

1. app/storage/db.py
- connect sqlite
- DB path ví dụ:

  data/backtest_results.sqlite3

- Bật WAL nếu hợp lý:

  PRAGMA journal_mode=WAL;

2. app/storage/schema.py
Tạo bảng:

backtest_runs:
- id TEXT PRIMARY KEY
- name TEXT
- created_at TEXT
- symbol TEXT
- mode TEXT
- timeframes_json TEXT
- strategies_json TEXT
- filters_json TEXT
- row_count INTEGER
- note TEXT

backtest_results:
- id INTEGER PRIMARY KEY AUTOINCREMENT
- run_id TEXT
- row_index INTEGER
- selected INTEGER
- rating INTEGER
- timeframe TEXT
- strategy TEXT
- params TEXT
- side_mode TEXT
- sl REAL
- tp REAL
- max_hold INTEGER
- trades INTEGER
- win_rate REAL
- total_return REAL
- profit_factor REAL
- expectancy REAL
- max_drawdown REAL
- avg_win REAL
- avg_loss REAL
- test_trades INTEGER
- test_win_rate REAL
- test_total_return REAL
- test_profit_factor REAL
- test_expectancy REAL
- score REAL
- extra_json TEXT
- FOREIGN KEY(run_id) REFERENCES backtest_runs(id)

Index:
- idx_backtest_results_run_id
- idx_backtest_runs_created_at

3. app/storage/repository.py
- save_run(...)
- list_runs(...)
- load_run(run_id)
- delete_run(run_id)

API thêm:

POST /api/backtest/save

Request:

{
  "name": "M15_M30_VOL_EXPANSION_test",
  "note": "filter winrate >= 65, pf >= 1.2",
  "symbol": "BTCUSD",
  "mode": "normal",
  "timeframes": ["M15", "M30"],
  "strategies": ["VOL_EXPANSION_CONT"],
  "filters": [
    {"field": "win_rate", "op": ">=", "value": 65}
  ],
  "rows": [
    {
      "selected": true,
      "rating": 4,
      "timeframe": "M15",
      "strategy": "VOL_EXPANSION_CONT",
      ...
    }
  ]
}

Response:

{
  "run_id": "uuid",
  "saved_rows": 123
}

GET /api/backtest/runs

Response:
[
  {
    "id": "uuid",
    "name": "...",
    "created_at": "...",
    "symbol": "BTCUSD",
    "mode": "normal",
    "row_count": 123,
    "note": "..."
  }
]

GET /api/backtest/runs/{run_id}

Response:
{
  "run": {...},
  "columns": [...],
  "rows": [...]
}

DELETE /api/backtest/runs/{run_id}

Response:
{
  "deleted": true
}

Frontend Phase 4:
- Enable Save button.
- Khi Save:
  - hỏi name/note
  - gửi current table rows + selected/rating
- Thêm panel "Saved Runs"
  - load list runs
  - click để load lại bảng
  - delete run

Done Phase 4 khi:
- Bấm Backtest không lưu DB.
- Bấm Save mới có record trong SQLite.
- Load lại saved run được.
- Rating/check được lưu.
- Không lưu signal arrays.


==================================================
PHASE 5 - POLISH / EXPORT / SAFETY
==================================================

Mục tiêu:
Làm hệ thống dùng thoải mái hơn.

Việc cần làm:
1. Export CSV từ bảng đang xem.
2. Copy selected rows.
3. Lưu column visibility vào localStorage.
4. Lưu font size table vào localStorage.
5. Thêm confirm khi delete saved run.
6. Thêm error message rõ khi backtest lỗi.
7. Thêm timeout hoặc warning nếu request quá nặng.
8. Thêm progress đơn giản nếu sau này chạy lâu.
9. Thêm benchmark thời gian chạy:
   - started_at
   - finished_at
   - duration_sec
10. Thêm endpoint:

GET /api/backtest/runs/{run_id}/export.csv

Không làm nếu chưa cần:
- user account
- cloud
- realtime websocket
- chart phức tạp
- multi-symbol
- live trading


==================================================
NGUYÊN TẮC IMPLEMENT
==================================================

1. Core backtest không biết FastAPI.
2. FastAPI không chứa logic indicator.
3. SQLite không lưu signal arrays.
4. Frontend không tự tính metric.
5. Mỗi phase phải chạy được độc lập.
6. Không rewrite lớn khi chỉ cần tách module.
7. Không đổi rule backtest nếu không có yêu cầu rõ.
8. Ưu tiên ít dependency.
9. Code càng boring càng tốt.
10. Sau mỗi phase phải có cách test rõ ràng.


==================================================
THỨ TỰ LÀM NGAY
==================================================

Bước 1:
Tạo app/backtest modules từ Phase 1.

Bước 2:
Tạo scripts/smoke_backtest_core.py.

Bước 3:
Chạy smoke test.

Bước 4:
Tạo FastAPI ở Phase 2.

Bước 5:
Test bằng Swagger.

Bước 6:
Chỉ khi Phase 1 + 2 ổn mới làm frontend Phase 3.

Bước 7:
Chỉ khi frontend hiện table ổn mới thêm SQLite Phase 4.


==================================================
TIÊU CHÍ DONE TỐI THIỂU CHO PROJECT MVP
==================================================

MVP được coi là xong khi:

- Mở web local được.
- Chọn timeframe.
- Chọn indicator/strategy.
- Nhập filter winrate/pnl/profit_factor.
- Bấm Run Backtest.
- Bảng kết quả hiện ra.
- Có checkbox từng dòng.
- Có rating 1-5 sao.
- Bấm Save mới lưu SQLite.
- Load lại saved run được.
- Không cần chart.
- Không cần login.
- Không cần deploy public.
