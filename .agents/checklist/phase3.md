# Phase 3 - Frontend UI Checklist

## Files

- [ ] `frontend/index.html` — Main layout, 4 cột trên + table dưới
- [ ] `frontend/src/main.js` — Init, load options, bind events, orchestrate
- [ ] `frontend/src/api.js` — `fetchOptions()`, `runBacktest(payload)`, base URL `http://127.0.0.1:8000`
- [ ] `frontend/src/state.js` — Global state object + `setState()`
- [ ] `frontend/src/table.js` — Render table, sort, search, column toggle, copy TSV, checkbox, rating, font size
- [ ] `frontend/src/style.css` — All styles

## 1. Setup panel (phần trên)

### Timeframes column
- [ ] `GET /api/options` → render timeframes list
- [ ] Click item → add to selected timeframes
- [ ] Click selected item → remove

### Strategies column
- [ ] `GET /api/options` → render strategies list
- [ ] Click item → add to selected strategies
- [ ] Click selected item → remove

### Selected column
- [ ] Display selected timeframes (có nút remove từng cái)
- [ ] Display selected strategies (có nút remove từng cái)
- [ ] Clear All button → reset cả timeframe & strategy
- [ ] Nếu rỗng → show placeholder text

### Filters column
- [ ] Default 2 filters: `win_rate >= 65`, `profit_factor >= 1.2`
- [ ] Field select populated from `/api/options` filter_fields
- [ ] Operator select populated from `/api/options` operators
- [ ] Value input (text)
- [ ] Add filter button
- [ ] Remove filter button (mỗi dòng)
- [ ] Filter rows hiển thị rõ

### Mode selector
- [ ] Radio: Normal / Dense High WR
- [ ] Default: Normal

### Run button
- [ ] Disabled khi chưa chọn timeframe nào
- [ ] Disabled trong lúc loading
- [ ] Loading text: "Running backtest..."
- [ ] Validate: ít nhất 1 timeframe
- [ ] Payload gửi lên: `{ symbol, timeframes, mode, strategies[], filters[], limit: 500 }`
- [ ] Strategies rỗng = chạy all (gửi null)
- [ ] Lỗi → hiển thị message đỏ rõ ràng

## 2. Result table (phần dưới)

### Toolbar
- [ ] Save button: disabled + click alert "Save will be implemented in Phase 4"
- [ ] Copy Selected: copy checked rows as TSV → clipboard
- [ ] Export CSV: download file
- [ ] Font size A- / A+
- [ ] Search input: filter rows real-time
- [ ] Result count: "X rows"

### Table
- [ ] Sort column: click header → toggle ascending/descending
- [ ] Hide/show columns: toggle (checkbox list or dropdown)
- [ ] Checkbox mỗi dòng (selected state)
- [ ] Rating 1-5★ mỗi dòng (clickable stars)
- [ ] Headers chính xác theo list

## 3. Behavior & state

- [ ] `state.js` chứa: timeframes, strategies, selectedTfs, selectedStrats, filters, mode, columns, rows, columnVisibility, fontSize, searchText, loading
- [ ] Result chỉ lưu tạm trong frontend state → reload mất
- [ ] NaN/inf/null handle từ API (backend đã xử lý)
- [ ] Không tự tính metric ở frontend

## 4. Test thủ công

- [ ] `uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`
- [ ] Load options được
- [ ] Chọn timeframe/strategy được
- [ ] Add/remove filter được
- [ ] Run backtest được, table hiện data
- [ ] Sort/search/hide column/copy selected hoạt động
- [ ] Checkbox/rating hoạt động
- [ ] Font size +/- text thay đổi
- [ ] Save chưa lưu thật, chỉ báo Phase 4
- [ ] Reload trang mất hết (chấp nhận)
