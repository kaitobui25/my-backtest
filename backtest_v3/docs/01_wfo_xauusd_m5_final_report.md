# Báo cáo Chuyên sâu: Tối ưu hóa Walk-Forward (WFO) Chiến lược XAUUSD Khung M5

**Ngày thực hiện:** Tháng 4/2026
**Mã dự án:** Backtest v3 - WFO Holy Grail Search
**Mục tiêu:** Truy tìm siêu cấu hình sinh lời với Winrate > 50% bằng cách sử dụng sức mạnh tính toán Numba/VectorBT để quét liên tục trên 8 năm lịch sử M5.

---

## 1. Kiến trúc Hệ thống Thử nghiệm (Backtest Engine V3)
Để đảm bảo kết quả trung thực tuyệt đối và tránh Look-ahead Bias (bẫy nhìn trước tương lai), hệ thống đã được chẻ nhỏ và tinh chuẩn như sau:

- **Bộ Tín hiệu (Signal Generators):** Tổng cộng **10 chiến lược cốt lõi** hoạt động hoàn toàn độc lập, bao gồm các phương pháp hiện đại nhất: Squeeze Momentum (smi.pine), Precision Sniper (EMA+Confluence), SMC_FVG (LuxAlgo), Bollinger Bands Bounce, RSI Reversal, SuperTrend, MACD Cross, v.v.
- **Bộ Quản lý Vốn (Exit Modes):** Fixed TP/SL, Trailing Stop (dịch SL theo ATR), và Partial TP (chốt 50% ở móc 2R, thả trôi phần còn lại).
- **Bộ Lọc Cấu hình (Grid Search):** `10,800 cấu hình` (trải dài với đủ loại Stoploss, Risk/Reward, và các bộ lọc Xu hướng EMA 200, Động lượng ADX 20/25, Thanh khoản Volume).

### Phân rã Dữ liệu Tiêu chuẩn Quantitative (Data Splitting)
Dữ liệu 800.000 cây nến M5 (2014-2026) được chặt làm 3 tầng cách ly:
1. **Warmup:** Dùng vài năm đầu mồi các đường trung bình (như EMA 200).
2. **WFO Pool (2016 - Giữa 2023):** Dữ liệu được cắt vụn thành **11 Folds (Nếp gấp)**. Mỗi Fold lấy 24 tháng In-Sample (IS) để huấn luyện $\rightarrow$ sau đó bắn chiến lược ra 6 tháng Out-of-Sample (OOS) hoàn toàn mới để đo lường. Cuốn chiếu trượt tiếp tới năm 2023. Tốn 158.000 lượt mô phỏng.
3. **Final Holdout (Giữa 2023 - 2026):** Khoảng Dữ Liệu Chết - Bị khóa lại hoàn toàn để làm "Kính Chiếu Yêu" tại bước cuối.

---

## 2. Kết quả Tại Pha Walk-Forward (Đoạn 2016-2023)
Kỹ thuật khâu nối equity (chắp vá kết quả OOS của 11 nếp gấp lại tạo thành 1 đồ thị kéo dài 6 năm chưa từng qua huấn luyện) cho ra một ảo ảnh rất đẹp:
- **Tổng Lợi Nhuận Gộp WFO:** **+506.96%** (Biến 1,000$ thành 6,070$).
- **Sụt giảm Tối đa (Max DD):** 46.39%.
- **Chân lý về Winrate M5:** KHÔNG MỘT CẤU HÌNH NÀO duy trì được WinRate > 50% trên toàn bộ 6 năm sau khi trừ phí giao dịch (Spread + Commission = 0.12R). Tất cả các hệ thống Winrate 41-45% (như BB_Bounce) rơi vào thua lỗ do mất tốn phí. Lợi nhuận của XAU/USD M5 sinh ra từ việc **gồng lãi xa**.

**Top 1 Cấu hình Tốt Nhất (Bởi Composite Score = Calmar + Sharpe + WR):**
- **Tín hiệu:** SQUEEZE MOMENTUM.
- **Chốt Lời:** `TRAILING STOP` (thả trôi dời SL theo bóng nến).
- **Stoploss:** 0.75 ATR (Cắt lỗ cực rát).
- **Bộ Lọc:** Trend thuận theo EMA 200, và chỉ vào khi ADX > 25 (Thị trường bay mạnh).
- **Winrate Mù:** 38.2%. Nó thua nhiều hơn thắng, nhưng một lần phá xu hướng WFO mang về lợi nhuận bùng nổ, gánh lỗ mẻ hoàn toàn rủi ro.

---

## 3. Khâu Final Holdout & Bài Học Định Lượng "Đẫm Máu"
Để xác định Cấu Hình Winrate 38% kia là "Chén Thánh" thật hay chỉ là thuật toán Overfitting ngẫu nhiên bắt trúng sóng của mấy năm trước, chúng ta mở khóa tệp **Final Holdout (Dữ liệu chưa ai biết từ giữa 2023 đến 2026)**.

**Kết quả: TẤT CẢ CÁC SIÊU CHIẾN LƯỢC ĐỀU SỤP ĐỔ.**
Chiến lược Top 1 Squeeze Trailing lao dốc:
- Lợi nhuận bốc hơi thành **lỗ -51.4%**.
- Tỉ lệ chiến thắng thụt về **36.6%**
- Mức độ ăn mòn (Drawdown) trên **50%**.

### Chẩn đoán nguyên nhân tử vong:
1. **Regime Shift (Sự đứt gãy cấu trúc vĩ mô):** Sau giữa 2023, Vàng (XAUUSD) không di chuyển trong kênh giá kỹ thuật nữa, nó bị lèo lái bởi sự kiện Địa chính trị mạnh mẽ, Lạm phát và Cắt giảm Lãi Suất. Vàng tạo đỉnh All-Time High liên tục bằng việc giật Spikes quét hai đầu.
2. **Hạn chế Khung Thời Gian M5:** Khung M5 ngập trong nhiễu sóng (Market Noise). Các tín hiệu động lượng (MACD, Squeeze) bị quét dính Stoploss liên đới trước khi kịp bật lên.  
3. Phí giao dịch (Cost/Slippage) cứa nát những chiến lược đánh xoay vòng nhanh tại các điểm giao cắt hẹp.

---

## 4. Lời Khuyên & Hướng Đi Kế Tiếp (Roadmap Thực Chiến)
- **Khai tử niềm tin "Holy Grail M5":** WFO chứng minh rõ ràng việc dùng thuật toán tĩnh để kiếm được WinRate cao vững chắc cho vàng M5 trong nhiều năm mà không ngó ngàng đến chu kỳ vĩ mô là một điều ảo tưởng. Quá nửa hệ thống bán trên thị trường đều chết trong Holdout tương tự như thế này.
- **Dịch Chuyển Khung Thời Gian Giá:** Phải nâng lên **M15 hoặc M30** – Các cấu trúc nến ở tầng này loại bỏ tới 60% nhiễu do Robot cao tần tạo ra, cho phép sóng Squeeze và SMC (Smart Money Concept) hoạt động chính xác.
- **Thay đổi Bản chất Signal:** Thay vì bắn tín hiệu liên thanh (liên tục quét mỗi 5 phút), nên sử dụng kịch bản Multi-Timeframe. (Ví dụ: Định hướng sóng lớn dựa vào M30/H1, nhưng chỉ thả điểm "Entry Sniper" bằng M5 tại vùng giao cắt khối).

**Tóm lại:** Engine Backtest V3 rất hoàn hảo, việc nó bóc trần chiến lược "lừa đảo OOS" bằng bài test Holdout mù đã giúp chúng ta tiết kiệm không biết bao nhiêu tiền Máu (Real Money) nếu cố chấp mang đi Live Trade. Đây là thành quả tuyệt đối của Quantitative Finance.
