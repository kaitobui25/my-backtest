PLAN: UI Backtest Config Protection

Mục tiêu:
- Sửa layout top panel thành 5 cột.
- Dời Execution và Risk / Leverage từ cột 4 sang cột 3.
- Khi đang backtest thì khóa không cho sửa Search Grid, Execution, Risk / Leverage.
- Thêm cột 5 chỉ xem: hiển thị đúng config thật sự đang được dùng để chạy backtest.

1. Layout

File: frontend/index.html

- Giữ:
  Cột 1: Timeframes
  Cột 2: Strategies
  Cột 3: Selected Setup

- Dời vào cột 3:
  - Execution
  - Risk / Leverage

- Cột 4 chỉ còn:
  - Result Filters
  - Search Grid

- Thêm cột 5:
  - Panel title: Active Backtest Config
  - Body id: running-config-view
  - Chỉ xem, không có input chỉnh sửa.

File: frontend/src/style.css

- Đổi #top-bar từ 4 cột sang 5 cột.
- Ví dụ:
  grid-template-columns: 120px 2fr 1.6fr 1.8fr 1.8fr;

- Thêm style cho cột 5:
  - font nhỏ
  - pre xuống dòng được
  - có scroll nếu nội dung dài
  - nhìn giống panel read-only.

2. Khóa setting khi đang backtest

File: frontend/src/main.js

Thêm helper:

function isConfigLocked() {
  return state.loading;
}

Áp vào render:

- renderSearchGrid()
  - Nếu state.loading = true thì disable toàn bộ input/select.

- renderExecutionSettings()
  - Nếu state.loading = true thì disable checkbox/input.

- renderRiskSettings()
  - Nếu state.loading = true thì disable checkbox/input.

Chặn thêm ở event handler để chắc chắn:

- search-grid change/input:
  if (state.loading) return;

- execution-settings change/input:
  if (state.loading) return;

- risk-settings change/input:
  if (state.loading) return;

3. Tạo snapshot config thật sự dùng để chạy

File: frontend/src/state.js

Thêm field mới:

runningConfigSnapshot: null,

Ý nghĩa:
- Đây là bản copy cố định của payload tại thời điểm bấm Run.
- Cột 5 chỉ đọc từ runningConfigSnapshot.
- Không đọc trực tiếp từ selectedTimeframes, selectedStrategies, filters, gridSettings...
- Vì vậy sau khi bấm Run, user sửa selection bên trái thì cột 5 không bị đổi theo.

4. Cập nhật handleRun()

File: frontend/src/main.js

Trong handleRun():

- Build filters.
- Build payload.
- Copy payload vào runningConfigSnapshot trước khi gọi API.

Ví dụ logic:

const payload = {
  symbol: "BTCUSD",
  timeframes: [...state.selectedTimeframes],
  mode: state.mode,
  strategies: state.selectedStrategies.length > 0 ? [...state.selectedStrategies] : null,
  filters,
  limit: 500,
  search_params: buildSearchParams(),
};

state.runningConfigSnapshot = structuredClone(payload);
renderRunningConfig();

Sau đó mới gọi:

const result = await runBacktestAPI(payload, controller.signal);

5. Render cột 5

File: frontend/src/main.js

Thêm function:

renderRunningConfig()

Nội dung hiển thị gọn:

- Symbol
- Mode
- Timeframes
- Strategies
- Result Filters
- Search Grid:
  - grid_profile
  - sl_values
  - tp_values
  - max_holds
  - min_trades_per_day
  - min_test_trades_per_day
- Execution:
  - entry_mode
  - use_spread_slippage
  - spread_pct
  - slippage_pct
- Risk / Leverage:
  - use_position_sizing
  - risk_per_trade_pct
  - use_leverage
  - leverage
  - use_liquidation
  - maintenance_margin_pct

Nếu chưa từng bấm Run:
- Hiển thị: No active backtest config yet

Gọi renderRunningConfig() trong:
- renderAll()
- handleRun() sau khi set runningConfigSnapshot
- handleLoadSavedRun() nếu muốn load saved run cũng hiện config đã lưu

6. Test cần pass

- Mở UI thấy 5 cột.
- Execution và Risk / Leverage nằm ở cột 3.
- Cột 4 chỉ còn Result Filters + Search Grid.
- Bấm Run thì cột 5 hiện config đang chạy.
- Trong lúc Running:
  - Không sửa được Search Grid.
  - Không sửa được Execution.
  - Không sửa được Risk / Leverage.
- Sau khi Run xong:
  - Có thể sửa 4 cột bên trái.
  - Nhưng cột 5 không đổi theo.
- Bấm Run lần mới:
  - Cột 5 update sang config mới.
- Payload gửi API vẫn không đổi format cũ.
- Save run vẫn lưu đúng lastRunPayload/search_params như trước.
