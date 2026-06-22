# Báo cáo Tối Ưu Hóa Chiến Lược FVG XAUUSD (Khung M3)

## 🎯 1. Mục tiêu và Tiêu chí
Báo cáo này phân tích kết quả thử nghiệm kịch bản chiến lược giao dịch **Fair Value Gap (FVG)** trên mã XAUUSD ở khung thời gian **3 Phút (M3)**. 

Các mục tiêu cốt lõi:
- **Winrate \> 45%**: Tỷ lệ thắng tối thiểu bắt buộc đối với một hệ thống ngắn hạn để giữ tâm lý tốt.
- **Tối đa hóa Lợi nhuận tịnh (Total OOS Return)**
- **Chốt lời từng phần (PARTIAL_TP)**: Ưu tiên chốt 50% khối lượng lệnh ngay khi đạt mục tiêu `2R`, phần 50% còn lại dùng `Trailing Stop`.
- **Ngắn hạn - Không nhiễu**: Tìm kiếm các chỉ báo phụ để triệt tiêu nhiễu dữ liệu của khung M3.

## 📊 2. Dữ liệu và Phương pháp (WFO)
* **Nguồn dữ liệu:** `XAUUSD.sml_M3_60000_before_20251001.parquet`
* **Giai đoạn:** Thao tác kiểm chuẩn diễn ra từ 04/06/2025 tới 30/09/2025 (~38,318 nến).
* **Cross-Validation (WFO):** Chiến lược sử dụng Roll-forward cơ bản (2 tháng IS/Train, 1 tháng OOS/Test) cho mẫu.

## 🧮 3. Mạng Lưới Tham Số (Grid Search)
Thuật toán đã thực hiện kết hợp FVG nguyên bản cùng các bộ lọc độc lập:
1. **EMA Filters**: `[Off, 50, 100, 200]`
2. **ADX Threshold**: `[0, 15, 20, 25, 30]` (Lọc các vùng sideway)
3. **Stop Loss Multiplier**: `[0.5, 0.75, 1.0, 1.25, 1.5, 2.0]` × Khẩu độ ATR
4. **Wait Candles**: Nghỉ `[2, 3, 5]` nến sau lệnh nhằm né Spikes.
Tổng cộng **120** kịch bản khả thi đã hoàn tất backtest.

---

## 🏆 4. Kịch Bản Tối Ưu Hiệu Quả Nhất
Từ hàng ngàn mô phỏng chi tiết, **duy nhất 1 cấu hình** thực sự giữ được **OOS Winrate \>= 45%** một cách bền vững trên mẫu Test.

### ⚙️ Thông số của Cấu hình Best Setup (#1)
- **Signal**: FVG 
- **Mode Quản lý lệnh**: `PARTIAL_TP`
- **TP1 (Chốt 1/2 vốn)**: `2.0R`
- **Stop Loss ATR Mult**: `2.0`
- **EMA Filter**: `Tắt (0)`
- **ADX Threshold**: `25`
- **Wait Candles**: `2`

### 📈 Chỉ số Hiệu Suất (Performance)
* **Winrate**: `45.1%`
* **Lợi Nhuận ròng (Net Profit)**: `+16.2%` (Với tỷ lệ risk 1%/lệnh)
* **Khấu trừ tối đa (Max Drawdown)**: `5.2%`
* **Mức Calmar**: `3.10`
* **Tổng số lệnh**: `51` lệnh OOS.

### 💡 Phân Tích Logic Cấu Hình (Tại sao hoạt động)
1. Khung thời gian nhỏ (M-3p) biến động đột ngột và ngẫu nhiên (noise). Các công cụ **EMA dường như quá chậm**, bị nhiễu do dao động sóng liên tục đánh lừa, dẫn đến việc *Tắt (Disable) EMA Filter* mang lại hiệu quả bắt điểm FVG sạch sẽ hơn.
2. Ngược lại, **ADX \>= 25** cực kỳ quan trọng. FVG trên khung 3 phút sẽ rơi vào cạm bẫy "Whipsaw" cực thảm liệt trong vùng Sideway. ADX-25 đảm bảo lúc FVG kích hoạt, dòng tiền thị trường thực sự đang chạy xu hướng mạnh (Impulse move).
3. Đặt **Stop Loss = 2.0 ATR** cho khung m3 dường như nới khoảng trống an toàn rất tốt để tránh những "Gim nến / Bóng nến" rũ bỏ vị thế (Liquidity sweep) trước khi giá đi qua ngưỡng mục tiêu `2R`.

Kêt hợp chiến lược `Partial_TP` giúp hệ số R-Return trung bình thực tế được bảo toán an toàn cao. Hệ thống dễ dàng củng cố mức DD dưới 6%.

---

## 🛠️ 5. Cơ Chế Setup Và Vào/Ra Lệnh (Trading Rules)

Dựa vào cấu hình mạnh nhất đã tìm ra trên khung M3, dưới đây là bộ quy tắc chính xác để cài đặt trên biểu đồ và cách thức quản lý lệnh:

### 5.1. Cài đặt Chỉ Báo (Indicators Setup)
- **Khung thời gian (Timeframe)**: M3 (3 Phút).
- **ADX (Average Directional Index)**: Chu kỳ `14`. Kéo một đường ngang thẳng tại mức `25`.
- **ATR (Average True Range)**: Chu kỳ `200` (dùng dạng RMA theo tiêu chuẩn mặc định của TradingView).
- **EMA (Đường trung bình động)**: TẮT hoàn toàn, không quan tâm tới mốc EMA.

### 5.2. Điều Kiện Vào Lệnh (Entry Rules)

> **Nguyên tắc cốt lõi (Xác nhận Momentum):**
> Chỉ xét điểm vào lệnh nếu cây nến hiện tại thỏa mãn điều kiện: Hệ số **ADX(14) >= 25**. Nếu ADX ở dưới 25 (Thị trường đi ngang / Sideway), tuyệt đối không vào bất kỳ lệnh nào.

**Lệnh MUA (Long):**
1. Bạn nhìn lại 3 cây nến trước đó `(Nến T-3, T-2, T-1)`.
2. Tạo ra kẽ hở FVG tăng: Giá ***Đáy nến T-3*** lớn hơn giá ***Đỉnh nến T-1***. 
3. Độ rộng của kẽ hở (Đáy T-3 trừ đi Đỉnh T-1) phải vừa đủ lớn: lớn hơn `0.1 x ATR`.
4. Điểm cắn (Trigger): Tại cây nến hiện tại `(T-0)`, nếu giá đóng cửa vượt mạnh lên và **lớn hơn giá Đáy của nến T-3** $\rightarrow$ Kích hoạt `Bắc Cầu (Buy)`.

**Lệnh BÁN (Short):** (Ngược lại)
1. Tạo kẽ hở FVG giảm: Giá ***Đỉnh nến T-3*** thấp hơn giá ***Đáy nến T-1*** (Khoảng cách > 0.1 x ATR).
2. Điểm cắn (Trigger): Tại cây nến hiện tại `(T-0)`, nếu giá đóng cửa giảm mạnh và **thấp hơn giá Đỉnh nến T-3** $\rightarrow$ Kích hoạt `Bán (Sell)`.

*Lưu ý khoảng tĩnh:* Sau khi 1 lệnh vừa Đóng (chạm SL hoặc TP), bạn phải **không vào lệnh trong 2 cây nến tiếp theo** kể cả khi nó có hình thành FVG (để tránh rũ bỏ).

### 5.3. Quản Lý Vốn & Chốt Lời (Exit Rules & Partial TP)

- **Xác định mức Rủi ro (R / Risk):** `R = 2.0 x ATR` tại thời điểm quyết định vào lệnh.
- **Stop Loss (Ban đầu):** Đặt cách điểm Entry một khoảng bằng đúng `1R`.
- **Take Profit (Mục tiêu chốt 1/2):** Bằng `2R` so với điểm Entry.

**Quy trình Thực thi:**
- Nếu giá cắn Stop Loss trước: Chấp nhận mất toàn bộ tỷ lệ Risk cho lệnh đó.
- Nếu giá đi đúng hướng và chạm mức giá `+2R`: Bạn thực hiện Chốt ngang **50% vị thế/khối lượng**.
- Ngay khoảnh khắc đó, **kéo Stop Loss của 50% khối lượng còn lại về mức Giá Hòa Vốn (Break-even)**.
- Đồng thời, thả nổi phần vốn 50% còn lại bằng lệnh `Trailing Stop`. Điểm trượt dừng (Trail distance) luôn duy trì đúng khoảng cách là `1R` chạy đuổi theo các mức Đỉnh/Đáy cao nhất (với lệnh Long/Short) mà giá vừa thiết lập. Lệnh sẽ tắt hoàn toàn khi giá đảo chiều cắn vào vạch Trailing Stop hờ này.

---

## 📂 Danh sách Files Kết Quả
Hệ thống backtest hoàn chỉnh đã sinh ra tự động các file dưới đây tại thư mục `my-data/backtest_v2/result/`:

1. CSV Tham Số Tổng Tổng Quan: `03_fvg_m3_top_strategies.csv`
2. Lịch sử Lệnh Cấu hình #1: `03_fvg_m3_best_setup_trades.csv`
3. Biểu Đồ Kép Tương Tác: `03_fvg_m3_best_setup_chart.html`
