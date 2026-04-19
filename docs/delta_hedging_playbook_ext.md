# BÁO CÁO PHÂN TÍCH VÀ QUY TRÌNH HÀNH ĐỘNG HEDGING CHỨNG QUYỀN (SOP)

## 1. Mô tả tình trạng hiện tại
* **Vị thế:** Đang bán (Short) lượng lớn Chứng quyền mua (Call CW).
* **Trạng thái rủi ro:** **Short Gamma Squeeze**. Cổ phiếu cơ sở (Underlying) tăng trần liên tục, dư mua lớn, mất thanh khoản chiều bán.
* **Vấn đề:** Không thể thực hiện Delta Hedging bằng cổ phiếu cơ sở. Việc phải mua lại CW từ đối thủ đang gây lỗ do chênh lệch Implied Volatility (IV).

---

## 2. Giải pháp đề xuất ngay lập tức (Immediate Action)
Khi cổ phiếu cơ sở mất thanh khoản, mục tiêu cao nhất là **Sống sót (Survival)** thay vì tối ưu chi phí:

1.  **Quét thanh khoản CW đối thủ (Proxy Hedging):** 
    * Xác định các mã CW cùng underlying có `Ask Size` đủ lớn.
    * Chấp nhận mua với IV cao hơn để đóng trạng thái Short Gamma/Delta nhanh nhất.

    1.1. **Lượng hóa chi phí Vol chênh lệch (Vol Spread Cost)**
    Khi phải mua lại chứng quyền (CW) của đối thủ để hedge (Gamma hedging) do cổ phiếu cơ sở mất thanh khoản, chấp nhận một khoản lỗ tức thì về mặt giá trị lý thuyết.

    1.2. **Công thức tính toán:**
    Cost ≈ ΔVega × (IV_market - IV_sold)

    - **IV_market**: Implied Volatility của CW mua trên thị trường (giá Ask).
    - **IV_sold**: Implied Volatility trung bình của lượng CW ông đã bán.
    - **ΔVega**: Tổng lượng Vega cần hedge.

2.  **Ưu tiên mã At-the-money (ATM):** Mua các mã có giá thực hiện (Strike) gần với giá hiện tại nhất để đạt được lượng Gamma bù đắp lớn nhất trên mỗi đơn vị vốn.
3.  **Hành động theo lớp:** Nếu không mua đủ lượng Delta bằng CW, chuyển sang sử dụng mã cổ phiếu có tương quan cao trong cùng ngành (Peer hedging) nếu mã đó chưa bị trần cứng.

---

## 3. Các kịch bản rủi ro và Quy trình ứng phó (SOP)

### Kịch bản A: Mất thanh khoản Delta (Cổ phiếu trần nhiều phiên)
* **Mô tả:** Cổ phiếu tiếp tục trần cứng phiên thứ 2, 3... khiến Delta âm của vị thế Short Call tăng vọt (do Gamma).
* **Phòng ngừa:** Thiết lập "Threshold" thanh khoản. Nếu dư mua trần > 5% tổng lượng lưu hành của mã đó -> Bắt đầu mua hedge ngay, không đợi đến cuối phiên:
    1. Quét Ask Size CW đối thủ (ưu tiên mã ATM, kỳ hạn 1-2 tháng).
    2. Chấp nhận "Pay Vol" (mua IV cao hơn IV mình bán).
    3. Ưu tiên mã có thanh khoản cao nhất thay vì mặc cả giá.
* **Quy trình:**
    1. Chạy Script Python (Mục 4) với giả định giá tăng +7% và +14%.
    2. Xác định số lượng cổ phiếu cơ sở thiếu hụt (`Delta_Hedge_Qty`).
    3. Thực hiện mua CW đối thủ hoặc Proxy mã tương đương.

### Kịch bản B: Volatility Explosion (IV tăng vọt)
* **Mô tả:** IV thị trường tăng mạnh làm giá CW tăng, gây lỗ Vega cho vị thế Short.
* **Phòng ngừa:** Đặt giới hạn Vega tối đa cho toàn bộ danh mục (Vega Limit).
* **Quy trình:**
    1. Tăng Spread Bid/Ask của bản thân để giảm rủi ro bị "hit" thêm lệnh mới.
    2. Nếu IV thị trường vượt ngưỡng Stress-test -> Thực hiện mua lại các mã Deep-out-of-the-money (OTM) để giảm Vega Exposure.

### Kịch bản C: Kịch bản ác mộng (Price Gap Up + Vol Spike + Illiquidity)
* **Mô tả:** Sáng sớm cổ phiếu mở cửa (Gap) tăng trần, đồng thời IV toàn thị trường tăng vọt, không thể đặt lệnh hedge kịp.
* **Phòng ngừa:** Luôn duy trì một lượng cổ phiếu cơ sở hoặc CW mua (Long) có Delta dương nhất định làm "vùng đệm".
* **Quy trình:** 1. Ngay lập tức giảm quy mô bán (Position Limit) cho các phiên tiếp theo.
    2. Sử dụng VN30F để hedge Delta tổng nếu mã nằm trong rổ VN30 (chấp nhận rủi ro Basis).

---

## 4. Python Script: Ma trận Stress-Test (PnL & Delta)

```python
import numpy as np
import pandas as pd
from scipy.stats import norm

def bs_metrics(S, K, T, r, sigma, type='call'):
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if type == 'call':
        price = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
        delta = norm.cdf(d1)
    else:
        price = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
        delta = norm.cdf(d1) - 1
    return price, delta

# --- THÔNG SỐ ĐẦU VÀO (Ông thay số vào đây) ---
S_now = 100         # Giá cổ phiếu hiện tại
K = 105             # Giá thực hiện (Strike)
T = 30/365          # 30 ngày tới đáo hạn
r = 0.05            # Lãi suất
vol_sold = 0.40     # Vol ông đã bán
n_cw_short = 1000000 # Số lượng CW đang short
conversion_ratio = 1 # Tỷ lệ chuyển đổi (ví dụ 1:1)

# --- MA TRẬN BIẾN THIÊN ---
prices = [S_now * (1 + x) for x in [-0.07, 0, 0.07, 0.14]] # Sàn, Đứng yên, Trần 1, Trần 2
vols = [vol_sold + x for x in [-0.05, 0, 0.10, 0.20]]      # Vol thay đổi

stress_data = []
for s in prices:
    for v in vols:
        p_new, d_new = bs_metrics(s, K, T, r, v)
        pnl = (bs_metrics(S_now, K, T, r, vol_sold)[0] - p_new) * n_cw_short
        delta_exposure = d_new * n_cw_short / conversion_ratio
        stress_data.append({
            'Price_Pct': f"{(s/S_now - 1)*100:.0f}%",
            'Vol_Abs': f"{v*100:.0f}%",
            'PnL_Triệu': round(pnl / 1_000_000, 2),
            'Delta_Qty': int(delta_exposure)
        })

df = pd.DataFrame(stress_data)
pnl_matrix = df.pivot(index='Price_Pct', columns='Vol_Abs', values='PnL_Triệu')
delta_matrix = df.pivot(index='Price_Pct', columns='Vol_Abs', values='Delta_Qty')

print("--- MA TRẬN PNL (TRIỆU VNĐ) ---")
print(pnl_matrix)
print("\n--- SỐ LƯỢNG CỔ PHIẾU CẦN MUA ĐỂ HEDGE ---")
print(delta_matrix)

- **IV_market**: Implied Volatility của CW mua trên thị trường (giá Ask).
- **IV_sold**: Implied Volatility trung bình của lượng CW ông đã bán.
- **ΔVega**: Tổng lượng Vega cần hedge.
