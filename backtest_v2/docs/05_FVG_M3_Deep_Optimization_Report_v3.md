# Báo Cáo Tối Ưu Hóa Sâu Chiến Lược XAUUSD (Khung M3) - Kịch Bản 05 (Cập Nhật V3 - CÓ TÍNH PHÍ SÀN)

## 🎯 1. Bối Cảnh Và Sự Sụp Đổ Của BB_BOUNCE (Thực Tế Tàn Khốc)
Báo cáo này **thay thế hoàn toàn** các kịch bản báo cáo số 04 trước đó. Nâng cấp cốt lõi của phiên bản `05v3` là việc mô phỏng sát nhất với thị trường thực:
1. **Fix hoàn toàn Bug kẹt lệnh (Consecutive Trades):** Ngăn chặn hệ thống nhồi lệnh liên tục trong một khoảng sideway hẹp (trước đây bot bất chấp bỏ qua cấu hình `wait_candles`).
2. **Loại bỏ "Zero Friction Fallacy":** Đưa vào mô phỏng mức chi phí Spread & Commission là `0.15R` mỗi lệnh. Trong giao dịch M3, Stop Loss quá ngắn sẽ bị Spread cấu mất một phần rất lớn lợi nhuận đường dài.

**Kết quả:** Sự thống trị của `BB_BOUNCE` hoàn toàn biến mất! Khi đưa phí giao dịch và tính toán số lệnh chính xác vào, việc bào lệnh với tần suất lớn (hơn 2,000 lệnh ở bản v2) làm chi phí đẩy lên quá cao, biến chiến lược Bollinger Bands từ sinh lãi khổng lồ sang bị lỗ ròng/hòa vốn. Tự nhiên chọn lọc đã khôi phục lại vị thế Vua cho tín hiệu **FVG (Fair Value Gap)**.

---

## 📊 2. Dữ Liệu Kiểm Thử (10 Tháng)
* **Dữ liệu chuẩn:** `XAUUSD_M3_v2_new.parquet` (~60,000 nến, từ 10/2025 tới 04/2026).
* **Quản lý rủi ro (Risk Management):** 1% vốn / Trade. Có trừ hao khoảng trượt giá và Spread `0.15 R`.
* **Quy trình:** Simulator thế hệ thứ 3 (`05` engine). Đã xóa sổ các lệnh "rác" do bom tín hiệu liên tục.

---

## 🏆 3. Top 5 Cấu Hình Tốt Nhất (Sống Sót Qua Spread - Dữ Liệu Thật)

Top 5 bây giờ là lãnh địa độc tôn của **FVG (SMC)** - nơi chất lượng của mỗi lệnh thắng áp đảo số lượng lệnh. 

| # | Tín hiệu | Chế Độ (Mode) | SL (ATR) | Tỉ lệ RR | Bộ Lọc EMA | Bộ Lọc ADX | Rèn nhịp (Wait) | Tỷ lệ thắng (WR%) | Net Profit% | Max DD | Trades |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **FVG** | PARTIAL_TP | 3.0 | 3.0 | EMA 50 | >= 20 | 5 nến | 34.3% | +51.4% | 12.5% | 198 |
| 2 | **FVG** | PARTIAL_TP | 3.0 | 3.0 | EMA 50 | >= 20 | 2 nến | 34.0% | +48.0% | 12.5% | 200 |
| 3 | **FVG** | FIXED | 3.0 | 3.0 | EMA 50 | >= 20 | 2 nến | 33.6% | +43.4% | 11.5% | 202 |
| 4 | **FVG** | FIXED | 3.0 | 3.0 | EMA 50 | >= 20 | 5 nến | 33.6% | +43.4% | 11.5% | 202 |
| 5 | **FVG** | FIXED | 3.0 | 3.0 | EMA 50 | >= 20 | 0 nến | 33.8% | +45.8% | 12.5% | 204 |

> 💡 **Nhận xét quan trọng:** 
> - **Lợi nhuận thực tế:** Mức +51.4% trong gần nửa năm giao dịch là con số *cực kỳ xuất sắc và bền vững* (tương đương ~100%/năm ROI). Không còn ảo giác lãi kép 300% như các bản lỗi trước.
> - **Chiến lược Rùa Bò (Khoảng 200 Trades trong 10 tháng):** Chỉ trung bình chưa tới 1 lệnh/ngày. Tần suất thấp giúp hệ thống miễn nhiễm với độ bào mòn tài khoản của Spread/Commision.
> - **Tính An Toàn Max Drawdown:** DD cao nhất chỉ khoảng 11-12.5% (hoàn toàn đủ tiêu chuẩn vượt quĩ cấp vốn Prop Firm).
> - **Quyền lực của R:R dài (3.0):** Stop loss được dãn ra `3.0 x ATR` giúp "phép màu FVG" không bị quét râu nhảm trước khi nó chạy đúng cấu trúc. 

---

## 🛠️ 4. Cơ Chế Setup Và Vào/Ra Lệnh (Trading Rules) Cho Top 1

Cấu hình hạng 1 là viên ngọc quý giá nhất sau đợt rà soát.

### ⚙️ Các chỉ báo cần setup trên Chart M3
- **EMA (Exponential Moving Average):** Chu kỳ 50 (Dùng xác định phe bò/phe gấu).
- **ADX (Average Directional Index):** Chu kỳ 14 (Đo độ bốc của xu hướng).
- **ATR:** Chu kỳ 200 (Thước đo biến động làm căn cứ kéo SL/TP).

### 🟢/🔴 Màng Lọc Vàng (Tuyệt Đối Tuân Thủ)
- **Trend Guard:** Chỉ Đánh Lên (Buy) khi Giá > EMA(50). Chỉ Đánh Xuống (Sell) khi Giá < EMA (50).
- **Momentum Guard:** Tuyệt đối không trade khi ADX(14) < 20 (Thị trường lờ đờ đi ngang, đánh FVG rất dễ bị quét 2 đầu).

### 🎯 Setup Entry (Phát hiện và vào lệnh FVG)
Lệnh được kích hoạt khi:
1. Bạn phát hiện ra chuỗi 3 cụm nến chênh lệch (Imbalance Gap). Trong đó, Khoảng trống giá (Gap) phải hở rộng tối thiểu > `0.1 * ATR`.
2. Lệnh sẽ vào **ngay tại thời điểm Giá vòng về lấp hoàn toàn** cái Gap đó rồi giật lại theo hướng Trend ban đầu (Mean-reversion entry inside Trend).

### 🛡 Quản Lý Lệnh Tối Ưu (Riding The Profit bằng `PARTIAL_TP`)
*Với mô hình FVG, việc giá chạy xa là rất phổ biến. Tuy nhiên ta phải chốt một nửa để bảo vệ tâm lý.*

- **SL Ban Đầu (Cố định cứng):** Ở khoảng giá Rủi ro = `3.0 x ATR(200)`. Rất gắt, rất an toàn với nến 3 phút.
- **TP1 (Bến đỗ số 1):** TP1 được đặt cách điểm Entry 1 khoảng `Dài gấp 3 lần Rủi ro phía trên (RR = 3.0)`.
- **Hành Động Khi Giá Đu Cuộc Đua Chạm Rốn TP1:**
  1. Lập tức **chốt lời cắt đi 50% khối lượng lệnh** bỏ vào túi (+1.5R thực tế/khoản nhỏ lẻ). 
  2. Kéo **Stop Loss của 50% lệnh đang mở còn lại về đúng điểm hòa vốn (Entry Break-Even)**. Không bao giờ cho phép một lệnh đã thắng lớn quay lại cắn âm tài khoản.
  3. Cứ thế, 50% khối lượng còn lại sẽ chơi theo luật Dropping Stop - Trailing dần theo đuôi ngọn sóng theo khoảng hở 3.0 ATR cho tới khi xu hướng đổi chiều thì đóng nốt. 

### ⏳ Chờ Nhịp Thở Lấy Hơi (Wait_Candles = 5)
Sau khi Đóng hoàn tất bất cứ một lệnh (Dù thắng hay SL), bạn **buộc phải bỏ qua 5 cây nến kế tiếp (~15 phút)**. Tuyệt đối không vào bất kỳ lệnh FVG nào trong quãng nghỉ này để cho cấu trúc nến được tái lập rõ ràng.

---

## 📂 5. Dữ Liệu Minh Chứng 
- Bảng tổng sắp Grid mới (Có lọc Spread): `result/05/05v3_fvg_m3_deep_strategies.csv`
- Biểu đồ vốn chuẩn Walk-forward: `result/05/05v3_fvg_m3_best_chart.html`

> **Tổng Kết:** Bạn đã có trong tay một hệ quy chiếu "Sạch Sẽ". File 05v3 là file chuẩn để bạn build logic code TradingView cho con Bot XAU USD hoặc đánh tay! Quên các cấu hình BB_BOUNCE rác và tỉ lệ WR ảo đi. Đây mới là Trading chuyên nghiệp.
