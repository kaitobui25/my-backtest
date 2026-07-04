# Phase 3 - Frontend UI Checklist

## Files

- [x] `frontend/index.html` — Main layout: setup panel trên + result table dưới
- [x] `frontend/src/main.js` — Init, load options, bind events, orchestrate
- [x] `frontend/src/api.js` — `fetchOptions()`, `runBacktest(payload)`, base URL `http://127.0.0.1:8000`
- [x] `frontend/src/state.js` — Global state object + `setState()`
- [x] `frontend/src/table.js` — Render table, sort, search, column toggle, copy TSV, checkbox, rating, font size
- [x] `frontend/src/style.css` — All styles

==================================================
1. SETUP PANEL
==================================================

## Timeframes column

- [x] `GET /api/options` → render timeframes list
- [x] Click timeframe item → add to selected timeframes
- [x] Duplicate timeframe không được add lại
- [x] Click/remove selected timeframe → remove khỏi selected list

## Strategies column

- [x] `GET /api/options` → render strategies list
- [x] Click strategy item → add to selected strategies
- [x] Duplicate strategy không được add lại
- [x] Click/remove selected strategy → remove khỏi selected list
- [x] Nếu không chọn strategy nào → payload gửi `strategies: null`

## Selected column

- [x] Display selected timeframes
- [x] Display selected strategies
- [x] Có nút remove từng item
- [x] Có nút `Clear All` → reset cả timeframe và strategy
- [x] Nếu rỗng → show placeholder text

## Filters column

- [x] Default filters:
  - `win_rate >= 65`
  - `profit_factor >= 1.2`
- [x] Field select populated from `/api/options.filter_fields`
- [x] Operator select populated from `/api/options.operators`
- [x] Value input dạng text
- [x] Add filter button
- [x] Remove filter button mỗi dòng
- [x] Filter value rỗng → không gửi filter đó
- [x] Numeric string như `"65"` → convert thành number nếu được
- [x] Filter rows hiển thị rõ, dễ sửa

## Mode selector

- [x] Radio: `Normal`
- [x] Radio: `Dense High WR`
- [x] Default: `Normal`
- [x] Payload mode phải gửi đúng:
  - `normal`
  - `dense_high_winrate`

## Run button

- [x] Disabled khi chưa chọn timeframe nào
- [x] Disabled trong lúc loading
- [x] Loading text: `Running backtest...`
- [x] Validate: phải có ít nhất 1 timeframe
- [x] Payload gửi lên:

{
  "symbol": "BTCUSD",
  "timeframes": ["M15", "M30"],
  "mode": "normal",
  "strategies": ["VOL_EXPANSION_CONT"],
  "filters": [
    {"field": "win_rate", "op": ">=", "value": 65}
  ],
  "limit": 500
}

- [x] Nếu không chọn strategy nào thì gửi:

"strategies": null

- [x] Lỗi API → hiển thị message đỏ rõ ràng
- [x] Success → render bảng kết quả xuống dưới

==================================================
2. RESULT TABLE
==================================================

## Toolbar

- [x] Save button để sẵn
- [x] Save button click → alert: `Save will be implemented in Phase 4`
- [x] Copy Selected → copy checked rows dạng TSV để paste vào Excel
- [x] Export CSV → download file CSV từ table hiện tại
- [x] Font size A- / A+
- [x] Search input → filter rows real-time
- [x] Result count: `X rows`

## Table

- [x] Render rows từ response `/api/backtest`
- [x] Sort column: click header → toggle ascending/descending
- [x] Sort numeric đúng kiểu số
- [x] Hide/show columns bằng checkbox list hoặc dropdown
- [x] Checkbox mỗi dòng
- [x] Rating 1-5★ mỗi dòng
- [x] Rating clickable, lưu vào frontend state
- [x] Checkbox state lưu vào frontend state
- [x] Table scroll ngang được nếu nhiều cột
- [x] Header dễ nhìn, compact

## Default visible columns

- [x] selected
- [x] rating
- [x] timeframe
- [x] strategy
- [x] params
- [x] side_mode
- [x] sl
- [x] tp
- [x] max_hold
- [x] trades
- [x] win_rate
- [x] total_return
- [x] profit_factor
- [x] expectancy
- [x] max_drawdown
- [x] test_trades
- [x] test_win_rate
- [x] test_total_return
- [x] test_profit_factor
- [x] score

## Dynamic columns

- [x] Nếu API trả thêm columns ngoài default list thì vẫn giữ trong data
- [x] Extra columns có thể ẩn mặc định
- [x] Hide/show column không làm mất data

==================================================
3. BEHAVIOR & STATE
==================================================

## `state.js` cần chứa

- [x] `timeframes`
- [x] `strategies`
- [x] `selectedTfs`
- [x] `selectedStrats`
- [x] `filters`
- [x] `mode`
- [x] `columns`
- [x] `rows`
- [x] `columnVisibility`
- [x] `fontSize`
- [x] `searchText`
- [x] `sortState`
- [x] `loading`
- [x] `error`

## Rules

- [x] Result chỉ lưu tạm trong frontend state
- [x] Reload page thì mất result, chấp nhận Phase 3
- [x] Không tự tính metric ở frontend
- [x] Không sửa backtest core nếu không có bug rõ
- [x] Không thêm dependency nặng
- [x] Không làm SQLite trong Phase 3
- [x] Không làm chart
- [x] Không làm login/auth

==================================================
4. API HELPERS
==================================================

## `api.js`

- [x] `API_BASE_URL = "http://127.0.0.1:8000"`
- [x] `fetchOptions()`
- [x] `runBacktest(payload)`
- [x] Handle HTTP error rõ ràng
- [x] Return JSON sạch cho main.js dùng

==================================================
5. TEST THỦ CÔNG
==================================================

## Backend

- [x] Chạy backend:

uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

- [x] Check Swagger:

http://127.0.0.1:8000/docs

## Frontend

- [x] Có lệnh chạy frontend rõ ràng

Nếu dùng static server:

cd frontend
python -m http.server 5173

Nếu dùng Vite:

cd frontend
npm run dev

## Manual test

- [x] Load options được
- [x] Chọn timeframe được
- [x] Chọn strategy được
- [x] Không chọn strategy nào vẫn chạy all được
- [x] Add/remove filter được
- [x] Mode normal gửi đúng `normal`
- [x] Mode Dense High WR gửi đúng `dense_high_winrate`
- [x] Run backtest được
- [x] Loading state hoạt động
- [x] API error hiển thị rõ
- [x] Table hiện data
- [x] Sort hoạt động
- [x] Search hoạt động
- [x] Hide/show column hoạt động
- [x] Copy selected rows hoạt động
- [x] Export CSV hoạt động
- [x] Checkbox hoạt động
- [x] Rating 1-5 sao hoạt động
- [x] Font size +/- thay đổi được
- [x] Save chưa lưu thật, chỉ báo Phase 4
- [x] Reload trang mất result, chấp nhận

==================================================
6. DONE PHASE 3 KHI
==================================================

- [x] Frontend mở được trên browser
- [x] Options load từ backend
- [x] User chọn timeframe/strategy/filter được
- [x] User bấm Run Backtest và nhận result
- [x] Result table dùng được: sort/search/hide/copy/check/rating/font size
- [x] Save chưa lưu thật, không có SQLite
- [x] Agent báo cáo file đã tạo/sửa
- [x] Agent báo cáo cách chạy frontend
- [x] Agent báo cáo những gì cố tình để Phase 4
