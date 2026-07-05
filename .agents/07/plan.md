# Plan 2 phase — Backtest realism + UI clarity

## PHASE 1 — Core metrics + execution realism, ít rủi ro

Mục tiêu:
Thêm các cột và option quan trọng nhất, default phải giữ behavior cũ nếu user không bật.

Backend:
- Thêm cột:
  - rr = tp / sl
  - realized_rr = avg_win / abs(avg_loss)
  - ambiguous_trades
  - ambiguous_rate
- Thêm entry mode:
  - same_open = mặc định như hiện tại
  - next_open = signal candle đóng xong, vào lệnh ở open cây kế tiếp
- Thêm cost option:
  - use_spread_slippage: false mặc định
  - spread_pct
  - slippage_pct
  - Nếu tắt: chỉ dùng FEE_PER_SIDE như hiện tại
  - Nếu bật: return trừ thêm spread_pct + slippage_pct

UI:
- Search Grid / Execution section thêm:
  - checkbox: Entry next open
  - checkbox: Use spread/slippage
  - input: spread_pct
  - input: slippage_pct
  - checkbox/show: ambiguous metrics
- Filter fields thêm:
  - rr
  - realized_rr
  - ambiguous_trades
  - ambiguous_rate

Files:
- app/backtest/config.py
- app/backtest/batch_engine.py
- app/backtest/result_builder.py
- app/backtest/runner.py
- app/api/routes_options.py
- frontend/src/state.js
- frontend/src/main.js
- frontend/src/style.css

Acceptance:
- Tắt toàn bộ option mới thì kết quả gần như y hệt hiện tại.
- API trả thêm rr, realized_rr, ambiguous_trades, ambiguous_rate.
- Bật Entry next open thì entry dùng open[i + 1], không dùng open[i].
- Bật spread/slippage thì total_return/PF giảm hợp lý.
- Có thể filter rr >= x, realized_rr >= x, ambiguous_rate <= x.


## PHASE 2 — Position sizing/leverage + UI dễ hiểu hơn

Mục tiêu:
Thêm phần giống trade thật hơn và sửa UX để tránh hiểu nhầm filter chưa được apply.

Backend:
- Thêm risk/equity mode:
  - use_position_sizing: false mặc định
  - risk_model: current_return_pct | fixed_fractional
  - risk_per_trade_pct
  - equity_total_return
  - equity_max_drawdown
- Thêm leverage/liquidation:
  - use_liquidation: false mặc định
  - leverage
  - maintenance_margin_pct
  - liquidated_trades
  - liquidation_rate
  - Nếu tắt: không check liquidation, giữ logic cũ
- Chưa cần full equity curve cho mọi config trong batch.
  - Chỉ thêm summary trước.
  - Equity curve chi tiết nên làm endpoint riêng sau khi user chọn 1 row.

UI:
- Execution / Risk section thêm:
  - checkbox: Use position sizing
  - input: risk_per_trade_pct
  - checkbox: Use leverage/liquidation
  - input: leverage
  - input: maintenance_margin_pct
- Result Filters:
  - Dropdown chọn field có nút ☆/★ để lưu favorite.
  - Favorite lưu localStorage.
  - Favorite field đưa lên đầu dropdown.
- Làm rõ filter/search grid đã apply:
  - Sau Run thành công, Result Filters và Search Grid hiện badge: Applied to current results
  - Nếu user sửa filter/grid sau Run, hiện: Changed after run — click Run Backtest to apply
  - Giữ màu dirty hiện tại nhưng thêm text rõ ràng hơn.

Files:
- app/backtest/batch_engine.py
- app/backtest/result_builder.py
- app/backtest/runner.py
- app/backtest/config.py
- app/api/routes_options.py
- frontend/index.html
- frontend/src/state.js
- frontend/src/main.js
- frontend/src/style.css
- frontend/src/table.js nếu cần format/hide columns

Acceptance:
- Tắt risk/leverage thì output không đổi so với phase 1.
- Bật risk_per_trade thì có equity_total_return/equity_max_drawdown.
- Bật liquidation thì có liquidated_trades/liquidation_rate.
- Favorite filter field reload page vẫn còn.
- Sau Run nhìn vào UI biết filter/grid đã được apply hay đã bị sửa sau run.
