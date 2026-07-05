# Phase 4 - Save / History / Review Checklist

## Mục tiêu Phase 4

- [ ] Lưu được kết quả backtest/candidate từ frontend
- [ ] Lưu được rating/note/check trạng thái từng row
- [ ] Xem lại lịch sử các lần Run đã lưu
- [ ] Load lại saved run để tiếp tục review
- [ ] Export/Copy vẫn hoạt động đúng với dữ liệu đã load lại
- [ ] Không làm thay đổi core backtest/search engine hiện tại

---

## 1. Backend - Files cần thêm / sửa

- [ ] `app/api/routes_saved.py` — API lưu/load/delete saved runs
- [ ] `app/services/saved_store.py` — logic đọc/ghi saved data
- [ ] `app/api/main.py` hoặc file include router — đăng ký saved router
- [ ] `data/saved_runs/` — folder chứa saved runs
- [ ] `.gitignore` — ignore `data/saved_runs/` nếu không muốn commit dữ liệu save

---

## 2. Data format

### Saved run metadata

- [ ] Mỗi lần save tạo 1 `run_id`
- [ ] Lưu `created_at`
- [ ] Lưu `symbol`
- [ ] Lưu `timeframes`
- [ ] Lưu `mode`
- [ ] Lưu `strategies`
- [ ] Lưu `filters`
- [ ] Lưu `row_count`
- [ ] Lưu `note` tổng nếu có

Ví dụ data cần lưu:

    {
      "run_id": "20260705_091500_btcusd_m15_h1",
      "created_at": "2026-07-05T09:15:00",
      "symbol": "BTCUSD",
      "timeframes": ["M15", "H1"],
      "mode": "normal",
      "strategies": ["ema_rsi"],
      "filters": [
        { "field": "win_rate", "op": ">=", "value": 65 }
      ],
      "row_count": 120,
      "note": ""
    }

### Saved rows

- [ ] Lưu toàn bộ `columns`
- [ ] Lưu toàn bộ `rows`
- [ ] Lưu `ratings`
- [ ] Lưu `selected rows`
- [ ] Lưu `row notes`
- [ ] Không phụ thuộc vào sort/search hiện tại
- [ ] Không để mất rating/note khi load lại

---

## 3. Backend endpoints

### POST /api/saved-runs

- [ ] Dùng để save run hiện tại
- [ ] Nhận payload gồm:
  - [ ] metadata
  - [ ] columns
  - [ ] rows
  - [ ] ratings
  - [ ] selected rows
  - [ ] row notes
- [ ] Trả về:
  - [ ] `run_id`
  - [ ] `message`
  - [ ] `saved_path`

---

### GET /api/saved-runs

- [ ] Dùng để list saved runs
- [ ] Sort mới nhất lên trên
- [ ] Mỗi item gồm:
  - [ ] `run_id`
  - [ ] `created_at`
  - [ ] `symbol`
  - [ ] `timeframes`
  - [ ] `mode`
  - [ ] `strategies`
  - [ ] `row_count`
  - [ ] `note`

---

### GET /api/saved-runs/{run_id}

- [ ] Dùng để load saved run
- [ ] Trả về:
  - [ ] metadata
  - [ ] columns
  - [ ] rows
  - [ ] ratings
  - [ ] selected rows
  - [ ] row notes

---

### DELETE /api/saved-runs/{run_id}

- [ ] Dùng để xóa saved run
- [ ] Nếu `run_id` không tồn tại thì trả lỗi rõ ràng
- [ ] Không cho xóa nhầm file ngoài folder saved runs

---

## 4. Backend validation

- [ ] Không cho save nếu `rows` rỗng
- [ ] Không cho save nếu thiếu `columns`
- [ ] Không cho load file không tồn tại
- [ ] Không cho path traversal kiểu `../../`
- [ ] Giới hạn số row lưu nếu cần
- [ ] Error response rõ ràng, dễ hiểu
- [ ] Không crash server nếu file save bị lỗi JSON

---

## 5. Frontend - API layer

### Sửa `frontend/src/api.js`

- [ ] Thêm `saveRun(payload)`
- [ ] Thêm `fetchSavedRuns()`
- [ ] Thêm `loadSavedRun(runId)`
- [ ] Thêm `deleteSavedRun(runId)`
- [ ] Dùng chung `API_BASE`
- [ ] Error handling giống `runBacktestAPI()`

---

## 6. Frontend - State

### Sửa `frontend/src/state.js`

Thêm state:

- [ ] `currentRunId`
- [ ] `currentRunMeta`
- [ ] `savedRuns`
- [ ] `rowNotes`
- [ ] `dirty`
- [ ] `loadedFromSave`

Ví dụ:

    currentRunId: null,
    currentRunMeta: null,
    savedRuns: [],
    rowNotes: {},
    dirty: false,
    loadedFromSave: false

---

## 7. Frontend - Save button

- [ ] Nếu chưa có result rows → báo `No results to save`
- [ ] Nếu có rows → gọi `saveRun()`
- [ ] Save kèm:
  - [ ] run payload hiện tại
  - [ ] columns
  - [ ] rows
  - [ ] ratings
  - [ ] selected rows
  - [ ] row notes
- [ ] Sau khi save thành công:
  - [ ] Hiện status `Saved`
  - [ ] Cập nhật `currentRunId`
  - [ ] Refresh saved runs list
- [ ] Nếu save lỗi → hiện error rõ ràng

---

## 8. Frontend - History panel

### UI cần thêm

- [ ] Thêm khu vực `Saved Runs`
- [ ] Hiển thị danh sách run đã lưu
- [ ] Mỗi run hiển thị:
  - [ ] created_at
  - [ ] timeframes
  - [ ] mode
  - [ ] strategies
  - [ ] row_count
  - [ ] nút Load
  - [ ] nút Delete
- [ ] List saved runs tự load khi mở app
- [ ] List saved runs refresh sau khi Save/Delete

---

## 9. Frontend - Load saved run

- [ ] Click Load → gọi `loadSavedRun(runId)`
- [ ] Restore:
  - [ ] columns
  - [ ] rows
  - [ ] ratings
  - [ ] selected rows
  - [ ] row notes
  - [ ] metadata
- [ ] Render lại table
- [ ] Render lại status
- [ ] Hiện `Loaded saved run`
- [ ] Nếu load lỗi → hiện error rõ ràng
- [ ] Sau khi load, Copy Selected vẫn dùng đúng selected rows

---

## 10. Frontend - Delete saved run

- [ ] Click Delete → confirm trước khi xóa
- [ ] Gọi `deleteSavedRun(runId)`
- [ ] Refresh saved runs list
- [ ] Nếu đang mở run bị xóa:
  - [ ] Clear `currentRunId`
  - [ ] Giữ table hiện tại hoặc clear theo quyết định
- [ ] Nếu delete lỗi → hiện error rõ ràng

---

## 11. Row notes

### Table UI

- [ ] Thêm cột `note` hoặc nút note riêng
- [ ] Cho phép nhập note cho từng row
- [ ] Note phải đi theo row khi sort/search
- [ ] Note phải được save/load lại đúng
- [ ] Note không làm hỏng export/copy
- [ ] Note dài thì vẫn hiển thị gọn, không phá layout

---

## 12. Rating / checkbox persistence

- [ ] Rating hiện tại không mất khi search
- [ ] Rating hiện tại không mất khi sort
- [ ] Checkbox hiện tại không mất khi search
- [ ] Checkbox hiện tại không mất khi sort
- [ ] Khi Save → lưu rating/checkbox
- [ ] Khi Load → restore rating/checkbox
- [ ] Copy Selected dùng đúng selected rows sau khi load
- [ ] Export CSV có thể bao gồm rating/note nếu đang visible

---

## 13. Export sau khi load saved run

- [ ] Export CSV hoạt động với saved run
- [ ] Export chỉ lấy visible columns
- [ ] Export theo search hiện tại
- [ ] Export theo sort hiện tại
- [ ] Export không làm mất tiếng Nhật/Vietnamese nếu có note
- [ ] CSV mở bằng Excel không lỗi encoding

---

## 14. Manual test - Save cơ bản

- [ ] Mở frontend
- [ ] Chọn timeframe
- [ ] Run backtest
- [ ] Rating vài row
- [ ] Tick checkbox vài row
- [ ] Thêm note vài row
- [ ] Save
- [ ] Reload browser
- [ ] Load saved run
- [ ] Kiểm tra rows còn đúng
- [ ] Kiểm tra rating còn đúng
- [ ] Kiểm tra checkbox còn đúng
- [ ] Kiểm tra note còn đúng

---

## 15. Manual test - Filter rỗng

- [ ] Add filter nhưng để value rỗng
- [ ] Run
- [ ] Không lỗi
- [ ] Save vẫn được
- [ ] Load lại vẫn được

---

## 16. Manual test - Search / sort / export

- [ ] Search keyword
- [ ] Sort theo `win_rate`
- [ ] Ẩn vài column
- [ ] Export CSV
- [ ] CSV đúng visible columns
- [ ] CSV đúng filtered rows
- [ ] CSV đúng sorted rows

---

## 17. Manual test - Delete

- [ ] Save 2 runs
- [ ] Delete 1 run
- [ ] List cập nhật đúng
- [ ] Load run còn lại vẫn OK
- [ ] Delete run không tồn tại thì không crash

---

## 18. Không làm trong Phase 4

- [ ] Không cần login/user account
- [ ] Không cần database phức tạp
- [ ] Không cần chart đẹp
- [ ] Không cần realtime dashboard
- [ ] Không cần sửa core strategy engine
- [ ] Không cần tối ưu performance lớn
- [ ] Không cần multi-user

---

## 19. Done criteria

- [ ] Save button hoạt động thật
- [ ] Saved runs hiện trong UI
- [ ] Load lại saved run được
- [ ] Delete saved run được
- [ ] Rating không mất sau save/load
- [ ] Checkbox không mất sau save/load
- [ ] Note không mất sau save/load
- [ ] Export/copy vẫn đúng
- [ ] Backend có validate lỗi cơ bản
- [ ] Không phá Phase 3 UI hiện tại
