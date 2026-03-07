# Hướng Dẫn Sử Dụng TCBS OpenAPI Cho Người Mới Bắt Đầu

## Tổng Quan

TCBS OpenAPI là một hệ thống API mạnh mẽ cho phép bạn tích hợp giao dịch chứng khoán vào hệ thống của mình. API này hỗ trợ cả giao dịch cổ phiếu và phái sinh với các tính năng toàn diện như đặt lệnh, quản lý danh mục, và dữ liệu thị trường thời gian thực.

## Mục Lục
1. [Chuẩn Bị Trước Khi Bắt Đầu](#chuẩn-bị-trước-khi-bắt-đầu)
2. [Xác Thực và Token](#xác-thực-và-token)
3. [Các Endpoints Chính](#các-endpoints-chính)
4. [Ví Dụ Code Python](#ví-dụ-code-python)
5. [Tích Hợp Tín Hiệu Giao Dịch](#tích-hợp-tín-hiệu-giao-dịch)
6. [Sử Dụng Asyncio Cho Giao Dịch](#sử-dụng-asyncio-cho-giao-dịch)
7. [Xử Lý Lệnh Chưa Thực Hiện](#xử-lý-lệnh-chưa-thực-hiện)
8. [Xử Lý Lỗi](#xử-lý-lỗi)
9. [Best Practices](#best-practices)

## Chuẩn Bị Trước Khi Bắt Đầu

### 1. Tạo Tài Khoản TCBS
- Truy cập [TCBS](https://www.tcbs.com.vn) để mở tài khoản giao dịch
- Đăng ký dịch vụ API thông qua hệ thống TCInvest

### 2. Lấy API Key
- Đăng nhập vào TCInvest
- Điều hướng đến phần "API Management" hoặc "Quản lý API"
- Tạo API Key mới và lưu trữ an toàn

### 3. Cài Đặt Môi Trường Phát Triển
```bash
pip install requests
```

## Xác Thực và Token

### Bước 1: Nhận Token
Trước khi sử dụng bất kỳ API nào, bạn cần trao đổi API Key để lấy JWT Token.

**Endpoint:** `POST /gaia/v1/oauth2/openapi/token`

**Request Body:**
```json
{
  "otp": "111111",
  "apiKey": "310ebe1b-07a7-463a-860d-773dcaa31591"
}
```

**Response:**
```json
{
  "token": "eyJ4NXQiOiJaaWpkaFpqVmlNamMwWmdfUlMyNTYiLCJhbGciOiJSUzI1NiJ9"
}
```

### Bước 2: Sử Dụng Token
Thêm token vào header của tất cả các request:
```
Authorization: Bearer {token}
```

## Các Endpoints Chính

### 1. Thông Tin Tài Khoản

#### Lấy Thông Tin Tiểu Khoản
**Endpoint:** `GET /eros/v2/get-profile/by-username/{custodyCode}`

```python
import requests

def get_account_info(custody_code, token):
    url = f"https://openapi.tcbs.com.vn/eros/v2/get-profile/by-username/{custody_code}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    params = {
        "fields": "basicInfo,personalInfo,bankSubAccounts,bankAccounts"
    }

    response = requests.get(url, headers=headers, params=params)
    return response.json()
```

### 2. Đặt Lệnh Giao Dịch

#### Đặt Lệnh Thường (Cổ phiếu)
**Endpoint:** `POST /akhlys/v1/accounts/{accountNo}/orders`

```python
def place_stock_order(account_no, token, order_data):
    url = f"https://openapi.tcbs.com.vn/akhlys/v1/accounts/{account_no}/orders"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # order_data mẫu
    order_data = {
        "execType": "NS",  # NS: Bán, NB: Mua
        "price": 50000,    # Giá
        "priceType": "LO", # LO: Lệnh giới hạn
        "quantity": 100,   # Khối lượng
        "symbol": "VNM"    # Mã chứng khoán
    }

    response = requests.post(url, headers=headers, json=order_data)
    return response.json()
```

### 3. Tra Cứu Sổ Lệnh

#### Lấy Danh Sách Lệnh
**Endpoint:** `GET /aion/v1/accounts/{accountNo}/orders`

```python
def get_order_list(account_no, token):
    url = f"https://openapi.tcbs.com.vn/aion/v1/accounts/{account_no}/orders"
    headers = {
        "Authorization": f"Bearer {token}"
    }

    response = requests.get(url, headers=headers)
    return response.json()
```

### 4. Thông Tin Sức Mua

#### Lấy Sức Mua Chung
**Endpoint:** `GET /aion/v1/accounts/{accountNo}/ppse`

```python
def get_purchasing_power(account_no, token):
    url = f"https://openapi.tcbs.com.vn/aion/v1/accounts/{account_no}/ppse"
    headers = {
        "Authorization": f"Bearer {token}"
    }

    response = requests.get(url, headers=headers)
    return response.json()
```

### 5. Thông Tin Tài Sản

#### Lấy Thông Tin Cổ Phiếu
**Endpoint:** `GET /aion/v1/accounts/{accountNo}/se`

```python
def get_stock_assets(account_no, token):
    url = f"https://openapi.tcbs.com.vn/aion/v1/accounts/{account_no}/se"
    headers = {
        "Authorization": f"Bearer {token}"
    }

    response = requests.get(url, headers=headers)
    return response.json()
```

### 6. Thông Tin Tiền

#### Lấy Số Dư Tiền
**Endpoint:** `GET /aion/v1/accounts/{accountNo}/cashInvestments`

```python
def get_cash_balance(account_no, token):
    url = f"https://openapi.tcbs.com.vn/aion/v1/accounts/{account_no}/cashInvestments"
    headers = {
        "Authorization": f"Bearer {token}"
    }

    response = requests.get(url, headers=headers)
    return response.json()
```

## Ví Dụ Code Python Hoàn Chỉnh

### Class TCBS API Client

```python
import requests
import json
import time
from typing import Dict, Optional

class TCBSAPI:
    def __init__(self, api_key: str, base_url: str = "https://openapi.tcbs.com.vn"):
        self.api_key = api_key
        self.base_url = base_url
        self.token = None
        self.token_expiry = None

    def get_token(self, otp: str) -> bool:
        """Lấy JWT token từ API Key"""
        url = f"{self.base_url}/gaia/v1/oauth2/openapi/token"
        payload = {
            "otp": otp,
            "apiKey": self.api_key
        }

        try:
            response = requests.post(url, json=payload)
            response.raise_for_status()

            data = response.json()
            self.token = data.get("token")

            if self.token:
                print("✓ Token lấy thành công")
                return True
            else:
                print("✗ Không thể lấy token")
                return False

        except requests.exceptions.RequestException as e:
            print(f"✗ Lỗi khi lấy token: {e}")
            return False

    def _get_headers(self) -> Dict[str, str]:
        """Tạo headers cho request"""
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    def place_order(self, account_no: str, symbol: str, quantity: int,
                   price: float, side: str = "NB") -> Dict:
        """
        Đặt lệnh giao dịch

        Args:
            account_no: Số tiểu khoản
            symbol: Mã chứng khoán
            quantity: Khối lượng
            price: Giá
            side: "NB" (mua) hoặc "NS" (bán)
        """
        url = f"{self.base_url}/akhlys/v1/accounts/{account_no}/orders"

        order_data = {
            "execType": side,
            "price": int(price),
            "priceType": "LO",
            "quantity": quantity,
            "symbol": symbol
        }

        try:
            response = requests.post(url, headers=self._get_headers(), json=order_data)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            return {"error": str(e)}

    def get_account_info(self, custody_code: str) -> Dict:
        """Lấy thông tin tài khoản"""
        url = f"{self.base_url}/eros/v2/get-profile/by-username/{custody_code}"
        params = {"fields": "basicInfo,personalInfo,bankSubAccounts,bankAccounts"}

        try:
            response = requests.get(url, headers=self._get_headers(), params=params)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            return {"error": str(e)}

    def get_cash_balance(self, account_no: str) -> Dict:
        """Lấy thông tin số dư tiền"""
        url = f"{self.base_url}/aion/v1/accounts/{account_no}/cashInvestments"

        try:
            response = requests.get(url, headers=self._get_headers())
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            return {"error": str(e)}

    def get_purchasing_power(self, account_no: str) -> Dict:
        """Lấy thông tin sức mua"""
        url = f"{self.base_url}/aion/v1/accounts/{account_no}/ppse"

        try:
            response = requests.get(url, headers=self._get_headers())
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            return {"error": str(e)}
```

### Cách Sử Dụng

```python
# Khởi tạo client
api = TCBSAPI(api_key="your_api_key_here")

# Bước 1: Đăng nhập và lấy token
otp = input("Nhập mã OTP: ")
if api.get_token(otp):
    print("Đăng nhập thành công!")

    # Bước 2: Lấy thông tin tài khoản
    account_info = api.get_account_info("your_custody_code")
    print("Thông tin tài khoản:", account_info)

    # Bước 3: Kiểm tra số dư tiền
    cash_balance = api.get_cash_balance("your_account_no")
    print("Số dư tiền:", cash_balance)

    # Bước 4: Đặt lệnh mua
    order_result = api.place_order(
        account_no="your_account_no",
        symbol="VNM",
        quantity=100,
        price=50000,
        side="NB"  # Mua
    )
    print("Kết quả đặt lệnh:", order_result)
```

## Xử Lý Lỗi

### Các Mã Lỗi Phổ Biến

| Mã lỗi | Ý nghĩa | Cách xử lý |
|--------|---------|-----------|
| 401 | Unauthorized | Token hết hạn hoặc không hợp lệ |
| 403 | Forbidden | Không có quyền truy cập |
| 404 | Not Found | Endpoint không tồn tại |
| 400 | Bad Request | Dữ liệu gửi lên không đúng định dạng |

### Ví Dụ Xử Lý Lỗi

```python
def safe_api_call(api_func, *args, **kwargs):
    """Hàm wrapper để xử lý lỗi API"""
    try:
        response = api_func(*args, **kwargs)

        if "error" in response:
            print(f"Lỗi API: {response['error']}")
            return None

        return response

    except requests.exceptions.Timeout:
        print("Timeout: API không phản hồi")
        return None

    except requests.exceptions.ConnectionError:
        print("Lỗi kết nối mạng")
        return None

    except Exception as e:
        print(f"Lỗi không xác định: {e}")
        return None
```

## Best Practices

### 1. Bảo Mật
- **Không hardcode API Key** trong code
- Lưu trữ token an toàn và refresh khi cần thiết
- Sử dụng HTTPS cho tất cả requests

### 2. Xử Lý Token
- Token có thời hạn, cần refresh trước khi hết hạn
- Lưu token ở nơi an toàn (environment variables, key vault)

### 3. Rate Limiting
- TCBS có giới hạn số request per phút
- Implement retry logic với exponential backoff

### 4. Logging
```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)
```

### 5. Error Handling
- Luôn check response status
- Handle các exception khác nhau
- Log lỗi để debug

## Kết Luận

TCBS OpenAPI cung cấp một nền tảng mạnh mẽ để tích hợp giao dịch chứng khoán vào ứng dụng của bạn. Bắt đầu với việc lấy token, sau đó khám phá các endpoints từ đơn giản đến phức tạp. Luôn nhớ xử lý lỗi và bảo mật thông tin xác thực.

Để biết thêm chi tiết, hãy tham khảo tài liệu chính thức tại [TCBS Developer Portal](https://developers.tcbs.com.vn).

Chúc bạn thành công với việc tích hợp TCBS OpenAPI!

---

# HƯỚNG DẪN NÂNG CAO: TÍCH HỢP TÍN HIỆU, ASYNCIO, QUẢN LÝ LỆNH VÀ BEST PRACTICES

## 1. Tích Hợp Tín Hiệu Giao Dịch

Trong phần này, bạn sẽ học cách tích hợp tín hiệu giao dịch định nghĩa sẵn vào hệ thống để tự động đặt lệnh khi điều kiện thỏa mãn.

### Ví dụ thiết kế tín hiệu:
```python
class SignalType(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"

@dataclass
class TradingSignal:
    symbol: str
    signal_type: SignalType
    price: float
    quantity: int
    confidence: float
    timestamp: str
    reason: str
```

### Tích hợp vào hệ thống giao dịch:
```python
class SignalGenerator:
    ...
    def generate_signals(self) -> List[TradingSignal]:
        # Sinh tín hiệu từ chỉ báo kỹ thuật
        ...

class TradingExecutor:
    ...
    async def execute_signal(self, signal: TradingSignal):
        # Đặt lệnh mua/bán khi có tín hiệu
        ...
```

## 2. Sử Dụng Asyncio Cho Giao Dịch

Asyncio giúp theo dõi nhiều mã, đặt lệnh, kiểm tra trạng thái đồng thời, giảm độ trễ.

### Ví dụ:
```python
import asyncio
import aiohttp
...
async def main():
    async with AsyncTCBSClient(api_key) as client:
        await asyncio.gather(
            monitor.start_monitoring(),
            order_manager.place_and_monitor_order(...)
        )
asyncio.run(main())
```

## 3. Quản Lý Lệnh Chưa Thực Hiện, Đảo Ngược Lệnh

Hệ thống cần tự động hủy lệnh nếu không khớp, và có thể đặt lệnh đảo ngược nếu cần.

### Ví dụ:
```python
class SmartOrderManager:
    ...
    async def place_smart_order(..., reverse_on_failure=True):
        ...
    async def start_monitoring(self):
        # Theo dõi trạng thái, tự động hủy/đảo khi hết timeout
        ...
```

## 4. Ví Dụ Thực Tế & Best Practices

- Kết hợp nhiều chỉ báo (RSI, MACD, EMA...)
- Sử dụng trailing stop-loss
- Lọc tín hiệu theo confidence
- Backtest tín hiệu trước khi trade thật
- Retry logic, connection pooling, logging, risk management

### Ví dụ backtest:
```python
class SignalBacktester:
    ...
    def backtest_signal(self, ...):
        ...
```

### Ví dụ logging chi tiết:
```python
import logging
...
logger = logging.getLogger("OrderManager")
logger.info(f"Đặt lệnh: {symbol} {side} {quantity}@{price}")
```

---

## Kết Luận Nâng Cao

Bạn đã có nền tảng xây dựng hệ thống giao dịch tự động mạnh mẽ, mở rộng được với:
- Machine learning
- WebSocket real-time
- Multi-asset trading
- Portfolio optimization

Tham khảo thêm tại [TCBS Developer Portal](https://developers.tcbs.com.vn) và các tài liệu chuyên sâu về trading system design patterns.

---

## Khi nào nên dùng async? (Dành cho hệ thống trading real-time, auto-trading)

### Nên dùng async cho các tác vụ sau:

- **Đặt lệnh (place_order, cancel_order, modify_order):**
  - Đặt/cancel nhiều lệnh cùng lúc cho nhiều mã.
  - Đảm bảo không bị block khi chờ phản hồi từ API broker.
- **Kiểm tra trạng thái lệnh (get_order_status):**
  - Theo dõi nhiều lệnh đang chờ khớp, liên tục polling trạng thái.
- **Lấy dữ liệu giá/market data:**
  - Lấy giá real-time cho nhiều mã (qua REST hoặc websocket).
- **Xử lý tín hiệu giao dịch:**
  - Xử lý đồng thời nhiều tín hiệu buy/sell từ nhiều chiến lược hoặc nhiều mã.
- **Quản lý danh sách lệnh đang hoạt động:**
  - Theo dõi, timeout, tự động hủy/đảo lệnh khi không khớp.
- **Kết nối WebSocket:**
  - Nhận dữ liệu real-time (giá, khớp lệnh, trạng thái thị trường) không delay.

### Lý do:
- Tối ưu hiệu suất hệ thống, tận dụng IO-bound, không bị block bởi network.
- Đáp ứng tức thời với tín hiệu và biến động thị trường.
- Dễ mở rộng quy mô (multi-symbol, multi-strategy, multi-account).
- Giảm độ trễ, tăng khả năng kiểm soát rủi ro.

### Ví dụ các hàm nên dùng async:
```python
async def place_order(...): ...
async def cancel_order(...): ...
async def get_order_status(...): ...
async def get_market_data(...): ...
async def handle_signals(...): ...
async def monitor_orders(...): ...
async def run_websocket_listener(...): ...
```

### Gợi ý triển khai:
- Toàn bộ pipeline từ nhận tín hiệu → đặt lệnh → kiểm tra trạng thái → xử lý kết quả nên là async.
- Sử dụng aiohttp, websockets, hoặc các framework async-native (FastAPI, Starlette, ...).
- Kết hợp asyncio.gather để chạy đồng thời nhiều task.
- Nếu dùng thread/blocking, chỉ nên dùng cho các thao tác đơn lẻ, không realtime.

**Tóm lại:**
- Nếu mục tiêu là trading real-time, auto, multi-symbol: Ưu tiên async cho mọi thao tác liên quan đến network, IO, và xử lý tín hiệu/lệnh.
