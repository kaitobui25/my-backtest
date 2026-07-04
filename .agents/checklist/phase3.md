# Phase 3 - Frontend UI Checklist

## Files

- [ ] `frontend/index.html` — Main layout: setup panel trên + result table dưới
- [ ] `frontend/src/main.js` — Init, load options, bind events, orchestrate
- [ ] `frontend/src/api.js` — `fetchOptions()`, `runBacktest(payload)`, base URL `http://127.0.0.1:8000`
- [ ] `frontend/src/state.js` — Global state object + `setState()`
- [ ] `frontend/src/table.js` — Render table, sort, search, column toggle, copy TSV, checkbox, rating, font size
- [ ] `frontend/src/style.css` — All styles

==================================================
1. SETUP PANEL
==================================================

## Timeframes column

- [ ] `GET /api/options` → render timeframes list
- [ ] Click timeframe item → add to selected timeframes
- [ ] Duplicate timeframe không được add lại
- [ ] Click/remove selected timeframe → remove khỏi selected list

## Strategies column

- [ ] `GET /api/options` → render strategies list
- [ ] Click strategy item → add to selected strategies
- [ ] Duplicate strategy không được add lại
- [ ] Click/remove selected strategy → remove khỏi selected list
- [ ] Nếu không chọn strategy nào → payload gửi `strategies: null`

## Selected column

- [ ] Display selected timeframes
- [ ] Display selected strategies
- [ ] Có nút remove từng item
- [ ] Có nút `Clear All` → reset cả timeframe và strategy
- [ ] Nếu rỗng → show placeholder text

## Filters column

- [ ] Default filters:
  - `win_rate >= 65`
  - `profit_factor >= 1.2`
- [ ] Field select populated from `/api/options.filter_fields`
- [ ] Operator select populated from `/api/options.operators`
- [ ] Value input dạng text
- [ ] Add filter button
- [ ] Remove filter button mỗi dòng
- [ ] Filter value rỗng → không gửi filter đó
- [ ] Numeric string như `"65"` → convert thành number nếu được
- [ ] Filter rows hiển thị rõ, dễ sửa

## Mode selector

- [ ] Radio: `Normal`
- [ ] Radio: `Dense High WR`
- [ ] Default: `Normal`
- [ ] Payload mode phải gửi đúng:
  - `normal`
  - `dense_high_winrate`

## Run button

- [ ] Disabled khi chưa chọn timeframe nào
- [ ] Disabled trong lúc loading
- [ ] Loading text: `Running backtest...`
- [ ] Validate: phải có ít nhất 1 timeframe
- [ ] Payload gửi lên:

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

- [ ] Nếu không chọn strategy nào thì gửi:

"strategies": null

- [ ] Lỗi API → hiển thị message đỏ rõ ràng
- [ ] Success → render bảng kết quả xuống dưới

==================================================
2. RESULT TABLE
==================================================

## Toolbar

- [ ] Save button để sẵn
- [ ] Save button click → alert: `Save will be implemented in Phase 4`
- [ ] Copy Selected → copy checked rows dạng TSV để paste vào Excel
- [ ] Export CSV → download file CSV từ table hiện tại
- [ ] Font size A- / A+
- [ ] Search input → filter rows real-time
- [ ] Result count: `X rows`

## Table

- [ ] Render rows từ response `/api/backtest`
- [ ] Sort column: click header → toggle ascending/descending
- [ ] Sort numeric đúng kiểu số
- [ ] Hide/show columns bằng checkbox list hoặc dropdown
- [ ] Checkbox mỗi dòng
- [ ] Rating 1-5★ mỗi dòng
- [ ] Rating clickable, lưu vào frontend state
- [ ] Checkbox state lưu vào frontend state
- [ ] Table scroll ngang được nếu nhiều cột
- [ ] Header dễ nhìn, compact

## Default visible columns

- [ ] selected
- [ ] rating
- [ ] timeframe
- [ ] strategy
- [ ] params
- [ ] side_mode
- [ ] sl
- [ ] tp
- [ ] max_hold
- [ ] trades
- [ ] win_rate
- [ ] total_return
- [ ] profit_factor
- [ ] expectancy
- [ ] max_drawdown
- [ ] test_trades
- [ ] test_win_rate
- [ ] test_total_return
- [ ] test_profit_factor
- [ ] score

## Dynamic columns

- [ ] Nếu API trả thêm columns ngoài default list thì vẫn giữ trong data
- [ ] Extra columns có thể ẩn mặc định
- [ ] Hide/show column không làm mất data

==================================================
3. BEHAVIOR & STATE
==================================================

## `state.js` cần chứa

- [ ] `timeframes`
- [ ] `strategies`
- [ ] `selectedTfs`
- [ ] `selectedStrats`
- [ ] `filters`
- [ ] `mode`
- [ ] `columns`
- [ ] `rows`
- [ ] `columnVisibility`
- [ ] `fontSize`
- [ ] `searchText`
- [ ] `sortState`
- [ ] `loading`
- [ ] `error`

## Rules

- [ ] Result chỉ lưu tạm trong frontend state
- [ ] Reload page thì mất result, chấp nhận Phase 3
- [ ] Không tự tính metric ở frontend
- [ ] Không sửa backtest core nếu không có bug rõ
- [ ] Không thêm dependency nặng
- [ ] Không làm SQLite trong Phase 3
- [ ] Không làm chart
- [ ] Không làm login/auth

==================================================
4. API HELPERS
==================================================

## `api.js`

- [ ] `API_BASE_URL = "http://127.0.0.1:8000"`
- [ ] `fetchOptions()`
- [ ] `runBacktest(payload)`
- [ ] Handle HTTP error rõ ràng
- [ ] Return JSON sạch cho main.js dùng

==================================================
5. TEST THỦ CÔNG
==================================================

## Backend

- [ ] Chạy backend:

uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

- [ ] Check Swagger:

http://127.0.0.1:8000/docs

## Frontend

- [ ] Có lệnh chạy frontend rõ ràng

Nếu dùng static server:

cd frontend
python -m http.server 5173

Nếu dùng Vite:

cd frontend
npm run dev

## Manual test

- [ ] Load options được
- [ ] Chọn timeframe được
- [ ] Chọn strategy được
- [ ] Không chọn strategy nào vẫn chạy all được
- [ ] Add/remove filter được
- [ ] Mode normal gửi đúng `normal`
- [ ] Mode Dense High WR gửi đúng `dense_high_winrate`
- [ ] Run backtest được
- [ ] Loading state hoạt động
- [ ] API error hiển thị rõ
- [ ] Table hiện data
- [ ] Sort hoạt động
- [ ] Search hoạt động
- [ ] Hide/show column hoạt động
- [ ] Copy selected rows hoạt động
- [ ] Export CSV hoạt động
- [ ] Checkbox hoạt động
- [ ] Rating 1-5 sao hoạt động
- [ ] Font size +/- thay đổi được
- [ ] Save chưa lưu thật, chỉ báo Phase 4
- [ ] Reload trang mất result, chấp nhận

==================================================
6. DONE PHASE 3 KHI
==================================================

- [ ] Frontend mở được trên browser
- [ ] Options load từ backend
- [ ] User chọn timeframe/strategy/filter được
- [ ] User bấm Run Backtest và nhận result
- [ ] Result table dùng được: sort/search/hide/copy/check/rating/font size
- [ ] Save chưa lưu thật, không có SQLite
- [ ] Agent báo cáo file đã tạo/sửa
- [ ] Agent báo cáo cách chạy frontend
- [ ] Agent báo cáo những gì cố tình để Phase 4
