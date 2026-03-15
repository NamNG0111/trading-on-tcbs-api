# 🚨 Crisis Delta Hedging Playbook — Short Gamma trên Thị Trường Việt Nam

> **Mục đích**: Quy trình step-by-step để delta hedge khi thị trường extreme volatility. Follow một cách máy móc, không second-guess.

---

## Mục lục
1. [Tổng quan tình huống](#1-tổng-quan-tình-huống)
2. [Hệ thống cảnh báo & Trigger sớm](#2-hệ-thống-cảnh-báo--trigger-sớm)
3. [Quy trình Hedging trong phiên (Intraday)](#3-quy-trình-hedging-trong-phiên-intraday)
4. [Chuyển sang Futures khi hết thanh khoản cổ phiếu](#4-chuyển-sang-futures-khi-hết-thanh-khoản-cổ-phiếu)
5. [Cách tính số hợp đồng futures cần để hedge](#5-cách-tính-số-hợp-đồng-futures-cần-để-hedge)
6. [Quy trình Unwind Futures → Cổ phiếu (ngày hôm sau)](#6-quy-trình-unwind-futures--cổ-phiếu-ngày-hôm-sau)
7. [Checklist nhanh — In ra dán trên bàn](#7-checklist-nhanh)

---

## 1. Tổng quan tình huống

**Bạn đang:**
- Short nhiều call options → **Short Gamma** → phải mua cổ phiếu khi giá tăng, bán cổ phiếu khi giá giảm
- Danh mục 30-40 cổ phiếu underlying trên HOSE (biên độ ±7%)
- Thường delta hedge vào **ATC (14:30-14:45)**

**Rủi ro trong extreme market:**
- Cổ phiếu hit sàn/trần → **mất thanh khoản** → không thể bán/mua để hedge
- **Asymmetry**: chiều giảm hệ thống thường đồng loạt giảm sàn; chiều tăng phân hóa hơn
- Nếu không hedge được: **lỗ gamma + lỗ unhedged delta** → double hit

---

## 2. Hệ thống cảnh báo & Trigger sớm

### 2.1 Định nghĩa chế độ thị trường (Market Regime)

| Regime | Trigger | Hành động |
|--------|---------|-----------|
| 🟢 **NORMAL** | VN30 dao động < 2% trong phiên | Hedge ATC như bình thường |
| 🟡 **ELEVATED** | VN30 dao động 2-4% HOẶC VIX/tin geopolitical bất thường | Hedge **2 lần/phiên** (11:15 + ATC) |
| 🔴 **EXTREME** | VN30 dao động > 4% HOẶC > 5 mã VN30 hit trần/sàn | Hedge **liên tục** + sẵn sàng dùng futures |

> [!IMPORTANT]
> Chuyển regime lên là quyết định **không thể đảo ngược** trong phiên. Không bao giờ hạ regime xuống trong cùng phiên. Hôm sau mới reassess.

### 2.2 Trigger hành động intraday theo mức biến động cổ phiếu

**Khi regime là 🟡 hoặc 🔴**, áp dụng trigger PER STOCK. Có 2 kịch bản:

#### Kịch bản A — Thị trường giảm dần (trigger 3% kích hoạt trước)

```
Cổ phiếu XYZ giảm qua -3% (hoặc tăng qua +3%)
  │
  ├─ BƯỚC 1: Tính lượng hedge theo K-Factor, CÓ GIỚI HẠN 50% delta_limit
  │    Hedge = min(50% × Delta_Limit, Delta_At_Trigger + K × (Delta_Limit − Delta_At_Trigger))
  │    → Đặt lệnh LO tại best bid/ask
  │    → Làm tròn 100 CP (half round up: 150 → 200)
  │
  ├─ XYZ tiếp tục giảm qua -5% (hoặc tăng qua +5%)
  │    BƯỚC 2: Tính lượng hedge theo K-Factor, BỎ GIỚI HẠN 50%
  │    Hedge = Delta_At_Trigger + K × (Delta_Limit − Delta_At_Trigger)
  │    → Bổ sung thêm phần chưa hedge ở bước 1
  │    → Nếu K-factor hedge > hedge đã đặt tại 3% → đặt thêm phần chêch
  │    → Nếu K-factor hedge ≤ hedge đã đặt → KHÔNG CẦN LÀM GÌ THÊM
  │
  └─ XYZ tiếp tục giảm qua -6.5% (hoặc tăng qua +6.5%)
       BƯỚC 3: CHUẨN BỊ PHƯƠNG ÁN FUTURES
       → Đặt sẵn lệnh ATC
       → Tính số HĐ futures cần (xem Mục 5)
       → Nếu dư bán sàn / dư mua trần → NGAY LẬP TỨC vào futures
```

#### Kịch bản B — Thị trường gap thẳng qua 3% (ví dụ mở cửa giảm -5%)

```
Cổ phiếu XYZ mở cửa đã giảm > -5% (hoặc tăng > +5%)
  │
  ├─ SKIP bước 3%: Trigger 3% là điểm hành động sớm — nếu đã qua thì bỏ qua
  │
  ├─ NGAY LẬP TỨC: Tính hedge theo K-Factor, BỎ GIỚI HẠN 50%
  │    Hedge = Delta_At_Trigger + K × (Delta_Limit − Delta_At_Trigger)
  │    → Đặt lệnh LO/MP ngay
  │
  └─ Nếu giảm tiếp qua -6.5%:
       → Chuẩn bị futures (giống Bước 3 Kịch bản A)
```

> [!IMPORTANT]
> **Nguyên tắc chung**: Khi giá gap qua nhiều ngưỡng, hành động theo ngưỡng **CAO NHẤT** đã chạm. Không cần chạy lại các bước của ngưỡng thấp hơn.

> [!NOTE]
> **K-Factor** (mặc định K=0.3): Là hệ số "sợ sàn". K=0 nghĩa là chỉ hedge đúng delta neutral. K=0.3 nghĩa là bán thêm 30% khoảng cách giữa delta hiện tại và delta sàn. Mục tiêu: **mua bảo hiểm thanh khoản** trước khi mất cơ hội giao dịch.

> [!CAUTION]
> **Tại sao giới hạn 50% ở trigger 3%?** Vì ở mức -3%, thị trường vẫn có khả năng hồi phục cao. Nếu bán quá nhiều (>50% delta sàn) mà thị trường quay đầu, chi phí mua lại rất lớn. Giới hạn 50% là trade-off giữa bảo hiểm thanh khoản và rủi ro giá quay đầu. Tại -5% trở đi, rủi ro sàn đã quá cao nên bỏ giới hạn.

### 2.3 Cách monitor — Cụ thể

1. **Sáng trước 9:00**: Check tin geopolitical, futures Mỹ/Châu Á đêm qua → set regime ban đầu
2. **9:00-9:15 (ATO)**: Quan sát giá mở cửa. Nếu gap down/up > 2% so với close hôm trước → nâng regime
3. **9:15 trở đi**: Monitor VN30 và các mã underlying theo trigger ở trên

---

## 3. Quy trình Hedging trong phiên (Intraday)

### 3.1 Khi regime ELEVATED hoặc EXTREME — Decision tree

```
Cổ phiếu XYZ biến động trong phiên
    │
    ├─── Biến động ≥ 3% nhưng < 5%? (Kịch bản A, Bước 1)
    │     │
    │     ├─ CÓ thanh khoản? (bid/ask spread < 1%, KL đặt > 10% ADV)
    │     │   └─ CÓ → Hedge K-Factor (max 50% Delta_Limit), lệnh LO
    │     │       └─ Monitor tiếp → nếu qua 5% → xem nhánh tiếp
    │     └─ KHÔNG → Đặt ATC + chuẩn bị futures (xem Mục 4)
    │
    ├─── Biến động ≥ 5% nhưng < 6.5%? (Kịch bản A Bước 2 hoặc Kịch bản B)
    │     └─ Hedge K-Factor (KHÔNG giới hạn 50%), lệnh LO/MP
    │         └─ Monitor tiếp → nếu qua 6.5% → xem nhánh tiếp
    │
    ├─── Biến động ≥ 6.5%? (Chuẩn bị Futures)
    │     └─ Đặt sẵn ATC + tính số HĐ futures + sẵn sàng vào lệnh
    │
    └─── Hit sàn/trần (-7%/+7%)?
          ├─ Vẫn có thanh khoản ATC? → Đặt lệnh ATC
          └─ Dư bán sàn / dư mua trần → CHUYỂN SANG FUTURES NGAY (xem Mục 4)
```

### 3.2 Cách xác định "mất thanh khoản"

Cổ phiếu coi là **mất thanh khoản** khi thỏa BẤT KỲ điều kiện nào:
- Dư bán sàn / dư mua trần > 3x ADV (average daily volume 20 ngày)
- Best bid/ask spread > 2%
- Khối lượng khớp liên tục trong 15 phút < 1% ADV

---

## 4. Chuyển sang Futures khi hết thanh khoản cổ phiếu

### 4.1 Khi nào dùng futures

> **QUY TẮC VÀNG**: Futures là biện pháp **khẩn cấp cuối cùng**, không phải công cụ hedge mặc định. Dùng KHI VÀ CHỈ KHI không thể giao dịch cổ phiếu.

### 4.2 Chọn hợp đồng

| Ưu tiên | Hợp đồng | Khi nào |
|----------|-----------|---------|
| 1 | VN30F1M | Mặc định. Thanh khoản cao nhất |
| 2 | VN30F2M | Chỉ khi F1M cũng mất thanh khoản (rất hiếm) |

> [!WARNING]
> **KHÔNG DÙNG F2M** trừ khi F1M thực sự mất thanh khoản. Bid/ask spread F2M thường 2-5 điểm, trade-in/trade-out chi phí cực lớn.

### 4.3 Quy trình vào lệnh futures

```
BƯỚC 1: Xác định tổng delta exposure CẦN HEDGE (xem Mục 5 cho công thức)
BƯỚC 2: Tính số hợp đồng futures (xem Mục 5)
BƯỚC 3: Đặt lệnh futures tại market price (không cố chờ giá tốt hơn — MỤC TIÊU LÀ HEDGE, KHÔNG PHẢI KIẾM LỜI)
BƯỚC 4: Ghi chép ngay:
         - Thời điểm vào lệnh
         - Số hợp đồng
         - Giá vào
         - Lý do (danh sách cổ phiếu nào không hedge được)
         - Delta exposure tương ứng từng cổ phiếu
```

---

## 5. Cách tính số hợp đồng futures cần để hedge

### 5.1 Công thức chính

```
Số hợp đồng = (Unhedged Delta Exposure bằng VND) × β_portfolio / (VN30 Futures Price × 100,000 VND)
```

Trong đó:
- **Unhedged Delta Exposure (VND)** = Tổng giá trị delta chưa hedge được bằng cổ phiếu
- **β_portfolio** = Beta trung bình (có trọng số delta) của các cổ phiếu cần hedge so với VN30
- **VN30 Futures Price** = Giá hợp đồng tương lai VN30 hiện tại
- **100,000 VND** = multiplier của hợp đồng VN30 futures

### 5.2 Ví dụ cụ thể

Giả sử:
- Bạn cần **bán** 5 tỷ VND delta nhưng cổ phiếu mất thanh khoản (thị trường giảm sàn, bạn cần bán nhưng dư bán sàn)
- β trung bình của các mã cần hedge = 1.2
- VN30 Futures đang ở 1,200 điểm

```
Số HĐ cần short = 5,000,000,000 × 1.2 / (1,200 × 100,000)
                 = 6,000,000,000 / 120,000,000
                 = 50 hợp đồng short
```

### 5.3 Cách ước lượng Beta nhanh

Trong tình huống khẩn cấp, không có thời gian tính beta chính xác:

| Nhóm cổ phiếu | Beta ước lượng |
|----------------|---------------|
| VN30 components (VNM, VCB, VHM, HPG, FPT...) | 1.0 - 1.3 |
| Mid-cap trong VN100 nhưng ngoài VN30 | 0.8 - 1.1 |
| Small-cap, cổ phiếu ngành | 0.6 - 0.9 |
| Ngân hàng, chứng khoán | 1.1 - 1.5 |
| BĐS, xây dựng | 1.2 - 1.6 |

> [!TIP]
> **Trong khủng hoảng hệ thống**, beta thực tế thường > beta bình thường (correlation tăng lên). Nên **multiply thêm 1.1-1.2x** vào beta ước lượng khi regime EXTREME.

### 5.4 Bảng tra nhanh (Quick Reference)

Với VN30F ≈ 1,200 điểm, 1 hợp đồng ≈ 120 triệu VND notional:

| Unhedged Delta (tỷ VND) | β=0.8 | β=1.0 | β=1.2 | β=1.5 |
|--------------------------|-------|-------|-------|-------|
| 1 | 7 HĐ | 8 HĐ | 10 HĐ | 13 HĐ |
| 2 | 13 HĐ | 17 HĐ | 20 HĐ | 25 HĐ |
| 5 | 33 HĐ | 42 HĐ | 50 HĐ | 63 HĐ |
| 10 | 67 HĐ | 83 HĐ | 100 HĐ | 125 HĐ |

> [!IMPORTANT]
> **Luôn làm tròn LÊN**, không xuống. Over-hedge tốt hơn under-hedge trong crisis.

---

## 6. Quy trình Unwind Futures → Cổ phiếu (ngày hôm sau)

> [!CAUTION]
> **Đây là phần phức tạp nhất**. Bạn đang hold 2 vị thế cần close đồng thời: futures position + lượng cổ phiếu tương ứng cần giao dịch. Sai lầm ở đây gây ra rủi ro mới thay vì giảm rủi ro.

### 6.1 Nguyên tắc chung

1. **Luôn close song song**: Mua/bán cổ phiếu ĐI ĐÔI VỚI đóng futures. Không bao giờ đóng hết một bên trước.
2. **Chia batch**: Không close tất cả cùng lúc. Chia thành batches.
3. **Ưu tiên mã có thanh khoản cao**: Close mã dễ trước, mã khó sau.
4. **Có deadline**: Phải close xong trước **14:00** để còn buffer cho ATC.

### 6.2 Chuẩn bị trước phiên (trước 9:00)

```
BƯỚC A: Tính toán trước phiên (tối hôm trước hoặc sáng sớm)
─────────────────────────────────────────────────────────────
1. Liệt kê TẤT CẢ cổ phiếu cần giao dịch (để thay thế futures hedge)
2. Tính CHÍNH XÁC delta cần cho TỪNG cổ phiếu
3. Sắp xếp theo THỨ TỰ ƯU TIÊN (xem Mục 6.3)
4. Tính tổng delta tương đương futures cần đóng
5. Chuẩn bị bảng theo template (xem Mục 6.5)
```

### 6.3 Thứ tự ưu tiên close cổ phiếu

Sắp xếp theo tiêu chí sau (ưu tiên giảm dần):

| Ưu tiên | Tiêu chí | Lý do |
|----------|----------|-------|
| 1 | **Thanh khoản cao nhất** (ADV lớn) | Dễ vào/ra, impact thấp. Ghi chú: Đơn vị ADV trong file Excel nên dùng **tỷ VND** cho dễ đọc. |
| 2 | **Delta lớn nhất** (delta exposure lớn) | Giảm rủi ro delta hở nhanh nhất. |
| 3 | **Thuộc VN30** | Correlation với futures cao nhất → offset tốt nhất. |
| 4 | **Còn lại** | Theo thứ tự thanh khoản giảm dần. |

### 6.4 Quy trình close trong phiên — STEP BY STEP

```
═══════════════════════════════════════════════════════════════
PHASE 1: KHỞI ĐỘNG (9:00 - 9:30)
═══════════════════════════════════════════════════════════════

Bước 1: Đánh giá tình hình mở cửa
   - Thị trường mở cửa hướng nào? Gap up/down bao nhiêu?
   - Cổ phiếu có thanh khoản không?
   
Bước 2: Nếu thị trường vẫn extreme → CHƯA ĐÓNG. Giữ futures hedge.
        Nếu thị trường ổn định hoặc hồi phục → BẮT ĐẦU ĐÓNG.

═══════════════════════════════════════════════════════════════
PHASE 2: ĐÓNG DẦN (9:30 - 13:30) — Chia làm 4 batches
═══════════════════════════════════════════════════════════════

   ┌─────────────────────────────────────────────────────┐
   │ Batch 1 (9:30-10:30): 25% vị thế                   │
   │  → Chọn 25% cổ phiếu có thanh khoản CAO NHẤT       │
   │  → Đặt lệnh LO gần bid/ask                         │
   │  → Khi khớp xong: NGAY LẬP TỨC đóng 25% futures   │
   │    tương ứng bằng market order                      │
   ├─────────────────────────────────────────────────────┤
   │ Batch 2 (10:30-11:30): 25% vị thế                  │
   │  → Tiếp tục với nhóm cổ phiếu tiếp theo            │
   │  → Đóng 25% futures tương ứng khi khớp             │
   ├─────────────────────────────────────────────────────┤
   │ Batch 3 (13:00-13:30): 25% vị thế                  │
   │  → Nhóm cổ phiếu tiếp theo                         │
   │  → Đóng 25% futures tương ứng                      │
   ├─────────────────────────────────────────────────────┤
   │ Batch 4 (13:30-14:15): 25% còn lại                 │
   │  → Mã khó nhất, thanh khoản kém nhất               │
   │  → Nếu không khớp được → ĐẶT ATC                   │
   │  → Đóng nốt futures tương ứng                      │
   └─────────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════
PHASE 3: KIỂM TRA CUỐI (14:15 - 14:30)
═══════════════════════════════════════════════════════════════

Bước 1: Đối chiếu bảng tracking:
   - Tất cả cổ phiếu đã khớp? → Close futures tương ứng chưa?
   - Nếu còn cổ phiếu chưa khớp → Đặt ATC
   
Bước 2: Kiểm tra vị thế futures còn lại:
   - Vị thế futures còn lại phải = delta chưa hedge được bằng cổ phiếu
   - Nếu lệch → điều chỉnh futures

Bước 3: DONE. Về regime NORMAL nếu thị trường đã bình thường.
```

### 6.5 Template bảng tracking — Chuẩn bị trước phiên

| # | Cổ phiếu | Delta cần (triệu VND) | Beta | Delta quy VN30 (triệu) | Futures tương đương (HĐ) | Ưu tiên | Batch | Giá target | Trạng thái | Giá khớp | Thời gian khớp | Futures đã đóng? |
|---|----------|----------------------|------|------------------------|--------------------------|---------|-------|------------|------------|----------|----------------|------------------|
| 1 | HPG | -800 | 1.3 | -1,040 | 8.7 | 1 | 1 | | | | | |
| 2 | VNM | -600 | 0.9 | -540 | 4.5 | 1 | 1 | | | | | |
| 3 | FPT | -500 | 1.1 | -550 | 4.6 | 2 | 2 | | | | | |
| ... | ... | ... | ... | ... | ... | ... | ... | | | | | |
| **TỔNG** | | **-X,XXX** | | **-X,XXX** | **XX** | | | | | | | |

> [!TIP]
> **Pre-compute bảng này tối hôm trước** bằng Excel/Python. Trong phiên chỉ điền cột "Giá khớp", "Thời gian khớp", và "Futures đã đóng". Không tính toán gì trong phiên dưới áp lực.

### 6.6 Xử lý tình huống bất thường khi unwind

| Tình huống | Hành động |
|------------|-----------|
| Thị trường tiếp tục giảm sâu ngày 2 | **GIỮ futures hedge**. Không đóng. Reassess ngày 3. |
| Một số mã khớp, một số không | Close futures TƯƠNG ỨNG với mã đã khớp. Giữ phần futures cho mã chưa khớp. |
| Futures basis thay đổi lớn (contango/backwardation mở rộng) | Chấp nhận loss trên basis. **Mục tiêu là hedge, không phải kiếm lời trên basis.** |
| Cần phải roll futures (hợp đồng sắp đáo hạn) | Roll sang kỳ hạn tiếp theo. Chi phí roll là chi phí bảo hiểm. |

---

## 7. Checklist nhanh

### 🔴 Khi thị trường EXTREME — Trong phiên

- [ ] **Check regime**: VN30 biến động > 4%? → EXTREME
- [ ] **Monitor trigger**: Cổ phiếu nào đã > 3%?
- [ ] **Hedge sớm**: Đã gửi lệnh cho mã > 3%? (50% delta)
- [ ] **Hedge full**: Đã gửi lệnh cho mã > 5%? (100% delta)
- [ ] **Kiểm tra thanh khoản**: Mã nào dư bán sàn / dư mua trần?
- [ ] **Tính futures**: Bao nhiêu HĐ cần? (dùng bảng tra nhanh Mục 5.4)
- [ ] **Vào futures**: Đã short/long đủ số HĐ?
- [ ] **Ghi chép**: Đã ghi lý do, số HĐ, giá, thời điểm?

### 🔄 Ngày hôm sau — Unwind

- [ ] **Bảng tracking**: Đã chuẩn bị sẵn (tối hôm trước)?
- [ ] **Đánh giá mở cửa**: Thị trường có hồi phục? Có thanh khoản?
- [ ] **Nếu vẫn extreme**: GIỮ futures. Không đóng.
- [ ] **Nếu ổn**: Bắt đầu close theo batch (25% mỗi batch)
- [ ] **Batch 1**: Cổ phiếu khớp → Đóng futures tương ứng ✓
- [ ] **Batch 2**: Cổ phiếu khớp → Đóng futures tương ứng ✓
- [ ] **Batch 3**: Cổ phiếu khớp → Đóng futures tương ứng ✓
- [ ] **Batch 4**: Cổ phiếu/ATC → Đóng futures tương ứng ✓
- [ ] **Kiểm tra cuối**: Vị thế net = 0? Không còn futures dư?

---

## Phụ lục: Những sai lầm phổ biến cần tránh

| ❌ Sai lầm | ✅ Nên làm |
|------------|-----------|
| Chờ xem thị trường có hồi không trước khi hedge | Hedge ngay khi trigger chạm. **Bạn không phải fortune teller.** |
| Cố mua/bán cổ phiếu tại giá tốt trong crisis | Market order hoặc chấp nhận giá đang có. Chi phí slippage < chi phí unhedged. |
| Đóng hết futures sáng sớm rồi mới bán cổ phiếu | **LUÔN CLOSE SONG SONG**. Đóng 1 bên trước = tạo rủi ro mới. |
| Tính toán trong phiên dưới áp lực | Pre-compute TẤT CẢ tối hôm trước. Trong phiên chỉ EXECUTE. |
| Nghĩ "lần này khác" và bỏ qua playbook | **Playbook tồn tại vì lần nào bạn cũng nghĩ "lần này khác"**. Follow the process. |
| Dùng F2M vì F1M "đắt" | F1M thanh khoản > F2M. Chi phí bid/ask F2M >>> premium F1M. |

---

> **Lời cuối**: Playbook này được thiết kế để bạn follow một cách *máy móc*. Trong crisis, **quy trình tốt beat trực giác tốt**. Bạn không cần nghĩ — chỉ cần làm theo. Every single time.
