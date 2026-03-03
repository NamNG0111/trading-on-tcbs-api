# Hướng dẫn vận hành & mở rộng hệ thống giao dịch tự động (simple_wow)

## 1. Kiến trúc tổng quan
- **main.py**: Pipeline chính, khởi tạo client, đọc tín hiệu, đặt lệnh, giám sát trạng thái.
- **signal_generator.py**: Sinh tín hiệu giao dịch từ các chiến lược được cấu hình.
- **strategies/**: Thư mục chứa các chiến lược giao dịch riêng biệt (RSI, MACD, v.v.).
  - **base_strategy.py**: Lớp cơ sở cho tất cả các chiến lược.
  - **rsi_strategy.py**: Chiến lược dựa trên chỉ báo RSI.
- **strategy_config.yaml**: File cấu hình tập trung cho các chiến lược và tham số.
- **trading_asyncio_module.py**: Quản lý kết nối API, lấy giá, đặt lệnh, kiểm tra trạng thái.
- **smart_order_manager.py**: Quản lý lệnh nâng cao (timeout, đảo lệnh, hủy lệnh).
- **config_manager.py**: Đọc config, credentials an toàn.
- **credentials.yaml**: Thông tin đăng nhập API (bảo mật, không commit git).
- **raw_files/**: Lưu bản nháp, ý tưởng, code chưa hoàn thiện.

## 2. Quy trình vận hành pipeline
1. Điền thông tin thật vào `credentials.yaml`.
2. Cấu hình các chiến lược trong `strategy_config.yaml`.
3. Chạy `python3 main.py` trong thư mục simple_wow.
4. Pipeline sẽ:
   - Lấy token, kết nối API.
   - Khởi tạo SignalGenerator với các chiến lược được cấu hình.
   - Sinh tín hiệu từ tất cả chiến lược được bật.
   - Đặt lệnh tự động với các tín hiệu đủ điều kiện.
   - Theo dõi trạng thái lệnh, quản lý timeout, đảo lệnh nếu cần.

## 3. Quy trình cấu hình và sử dụng chiến lược mới

### A. Cấu hình chiến lược trong strategy_config.yaml

File `strategy_config.yaml` là nơi tập trung quản lý tất cả các chiến lược giao dịch:

```yaml
# strategy_config.yaml
# Danh sách mã chứng khoán theo dõi
symbols:
  - VNM
  - VCB
  - TCB
  - HPG

# Cấu hình các chiến lược giao dịch
strategies:
  rsi:
    enabled: true
    params:
      rsi_period: 14
      overbought: 70
      oversold: 30
      confidence: 0.8
      default_quantity: 100

  macd:
    enabled: false
    params:
      fast_period: 12
      slow_period: 26
      signal_period: 9
      confidence: 0.7

# Tín hiệu thủ công (nếu có)
manual_signals:
  - symbol: HPG
    signal_type: BUY
    price: 55500
    quantity: 200
    confidence: 1.0
    reason: "manual_entry"

# Cấu hình giao dịch chung
trading:
  max_position_size: 1000
  risk_per_trade: 0.02
```

### B. Cách thêm chiến lược mới

#### 1. Tạo chiến lược mới trong thư mục strategies/

```python
# strategies/macd_strategy.py
from .base_strategy import BaseStrategy, TradingSignal, SignalType
from typing import Optional

class MACDStrategy(BaseStrategy):
    async def generate_signal(self, symbol: str) -> Optional[TradingSignal]:
        try:
            current_price = await self._get_current_price(symbol)
            macd_data = await self._calculate_macd(symbol)

            # Logic MACD
            if macd_data['histogram'] > 0 and macd_data['macd'] > macd_data['signal']:
                return TradingSignal(
                    symbol=symbol,
                    signal_type=SignalType.BUY,
                    price=current_price,
                    quantity=self.config.get('default_quantity', 100),
                    confidence=self.config.get('confidence', 0.7),
                    timestamp=self._get_current_time(),
                    reason=f"MACD bullish: {macd_data['macd']:.4f}"
                )
            elif macd_data['histogram'] < 0 and macd_data['macd'] < macd_data['signal']:
                return TradingSignal(
                    symbol=symbol,
                    signal_type=SignalType.SELL,
                    price=current_price,
                    quantity=self.config.get('default_quantity', 100),
                    confidence=self.config.get('confidence', 0.7),
                    timestamp=self._get_current_time(),
                    reason=f"MACD bearish: {macd_data['macd']:.4f}"
                )
        except Exception as e:
            print(f"Error in MACD strategy for {symbol}: {e}")
        return None

    async def _get_current_price(self, symbol: str) -> float:
        # Implementation to get current price
        return 0.0

    async def _calculate_macd(self, symbol: str) -> dict:
        # Implementation to calculate MACD
        return {'macd': 0, 'signal': 0, 'histogram': 0}  # Placeholder
```

#### 2. Đăng ký chiến lược trong SignalGenerator

```python
# signal_generator.py (cập nhật _setup_strategies)
def _setup_strategies(self):
    """Initialize strategies based on config"""
    from .strategies.rsi_strategy import RSIStrategy
    from .strategies.macd_strategy import MACDStrategy
    # Add more strategy imports as needed

    self.symbols = self.config.get('symbols', [])
    self.manual_signals = self.config.get('manual_signals', [])

    # Initialize RSI Strategy if enabled
    if self.config.get('strategies', {}).get('rsi', {}).get('enabled', False):
        rsi_config = self.config['strategies']['rsi']
        self.strategies.append(RSIStrategy(self.api_client, rsi_config))

    # Initialize MACD Strategy if enabled
    if self.config.get('strategies', {}).get('macd', {}).get('enabled', False):
        macd_config = self.config['strategies']['macd']
        self.strategies.append(MACDStrategy(self.api_client, macd_config))

    # Add more strategies here as needed
```

#### 3. Cấu hình chiến lược trong strategy_config.yaml

```yaml
strategies:
  macd:
    enabled: true
    params:
      fast_period: 12
      slow_period: 26
      signal_period: 9
      confidence: 0.7
      default_quantity: 100
```

### C. Cách sử dụng SignalGenerator mới

Với cấu trúc mới, việc sử dụng SignalGenerator trở nên đơn giản hơn:

```python
# main.py
from signal_generator import SignalGenerator

async def main():
    # Khởi tạo với config mặc định
    signal_generator = SignalGenerator(api_client=api_client)

    # Hoặc chỉ định file config tùy chỉnh
    # signal_generator = SignalGenerator(api_client=api_client, config_path='custom_config.yaml')

    # Sinh tín hiệu - tự động sử dụng tất cả chiến lược được bật
    signals = await signal_generator.generate_signals()

    # Xử lý tín hiệu...
```

**Ví dụ sử dụng nâng cao:**

```python
# Chỉ sinh tín hiệu cho một số mã cụ thể
signals = await signal_generator.generate_signals(symbols=['VNM', 'HPG'])

# Sinh tín hiệu với tham số tùy chỉnh (ghi đè config)
# (Chức năng này có thể được mở rộng trong tương lai)
```

## 4. Cấu trúc thư mục chiến lược mới

```
simple_wow/
├── strategies/
│   ├── __init__.py
│   ├── base_strategy.py          # Lớp cơ sở cho mọi chiến lược
│   ├── rsi_strategy.py           # Chiến lược RSI
│   ├── macd_strategy.py          # Chiến lược MACD (ví dụ)
│   └── bollinger_strategy.py     # Chiến lược Bollinger Bands (ví dụ)
├── strategy_config.yaml          # File cấu hình tập trung
├── signal_generator.py           # Tích hợp các chiến lược
└── main.py                       # Pipeline chính
```

## 5. Lớp cơ sở BaseStrategy

Tất cả chiến lược phải kế thừa từ `BaseStrategy`:

```python
# strategies/base_strategy.py
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum

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

class BaseStrategy(ABC):
    def __init__(self, api_client=None, config: Dict[str, Any] = None):
        self.api_client = api_client
        self.config = config or {}
        self.signals_history = []

    @abstractmethod
    async def generate_signal(self, symbol: str) -> Optional[TradingSignal]:
        """Generate trading signal for the given symbol"""
        pass

    def _get_current_time(self) -> str:
        from datetime import datetime
        return datetime.now().isoformat()
```

## 6. Ví dụ chiến lược hoàn chỉnh

### Chiến lược RSI

```python
# strategies/rsi_strategy.py
from .base_strategy import BaseStrategy, TradingSignal, SignalType
from typing import Optional

class RSIStrategy(BaseStrategy):
    async def generate_signal(self, symbol: str) -> Optional[TradingSignal]:
        try:
            current_price = await self._get_current_price(symbol)
            rsi_value = await self._calculate_rsi(symbol)

            if rsi_value > self.config.get('overbought', 70):
                return TradingSignal(
                    symbol=symbol,
                    signal_type=SignalType.SELL,
                    price=current_price,
                    quantity=self.config.get('default_quantity', 100),
                    confidence=self.config.get('confidence', 0.8),
                    timestamp=self._get_current_time(),
                    reason=f"RSI quá mua: {rsi_value:.2f}"
                )
            elif rsi_value < self.config.get('oversold', 30):
                return TradingSignal(
                    symbol=symbol,
                    signal_type=SignalType.BUY,
                    price=current_price,
                    quantity=self.config.get('default_quantity', 100),
                    confidence=self.config.get('confidence', 0.8),
                    timestamp=self._get_current_time(),
                    reason=f"RSI quá bán: {rsi_value:.2f}"
                )
        except Exception as e:
            print(f"Error in RSI strategy for {symbol}: {e}")
        return None

    async def _get_current_price(self, symbol: str) -> float:
        # Implementation to get current price
        return 0.0

    async def _calculate_rsi(self, symbol: str) -> float:
        # Implementation to calculate RSI
        return 50.0  # Placeholder
```

### Chiến lược kết hợp đa chỉ báo

```python
# strategies/combined_strategy.py
from .base_strategy import BaseStrategy, TradingSignal, SignalType
from typing import Optional, List

class CombinedStrategy(BaseStrategy):
    def __init__(self, api_client=None, config=None):
        super().__init__(api_client, config)
        self.strategies = []  # Danh sách các chiến lược con

    async def generate_signal(self, symbol: str) -> Optional[TradingSignal]:
        signals = []

        # Thu thập tín hiệu từ các chiến lược con
        for strategy in self.strategies:
            signal = await strategy.generate_signal(symbol)
            if signal:
                signals.append(signal)

        if not signals:
            return None

        # Logic kết hợp: Majority Vote
        buy_count = sum(1 for s in signals if s.signal_type == SignalType.BUY)
        sell_count = sum(1 for s in signals if s.signal_type == SignalType.SELL)

        if buy_count > sell_count:
            # Tính confidence trung bình
            avg_confidence = sum(s.confidence for s in signals if s.signal_type == SignalType.BUY) / buy_count
            return TradingSignal(
                symbol=symbol,
                signal_type=SignalType.BUY,
                price=signals[0].price,  # Lấy giá từ tín hiệu đầu tiên
                quantity=self.config.get('default_quantity', 100),
                confidence=min(avg_confidence, 1.0),
                timestamp=self._get_current_time(),
                reason=f"Majority vote BUY ({buy_count}/{len(signals)})"
            )
        elif sell_count > 0:
            avg_confidence = sum(s.confidence for s in signals if s.signal_type == SignalType.SELL) / sell_count
            return TradingSignal(
                symbol=symbol,
                signal_type=SignalType.SELL,
                price=signals[0].price,
                quantity=self.config.get('default_quantity', 100),
                confidence=min(avg_confidence, 1.0),
                timestamp=self._get_current_time(),
                reason=f"Majority vote SELL ({sell_count}/{len(signals)})"
            )

        return None
```

## 7. Quy trình phát triển chiến lược mới

1. **Tạo file chiến lược mới** trong thư mục `strategies/`
2. **Kế thừa từ BaseStrategy** và implement `generate_signal()`
3. **Cấu hình tham số** trong `strategy_config.yaml`
4. **Đăng ký chiến lược** trong `SignalGenerator._setup_strategies()`
5. **Test chiến lược** độc lập trước khi tích hợp
6. **Cập nhật tài liệu** này với ví dụ sử dụng

## 8. Best practices khi mở rộng chiến lược

- **Tách biệt trách nhiệm**: Mỗi chiến lược chỉ làm một việc cụ thể
- **Cấu hình hóa tham số**: Đưa tất cả tham số vào file YAML
- **Xử lý lỗi tốt**: Luôn catch exception và return None nếu có lỗi
- **Async programming**: Tất cả hàm lấy dữ liệu phải là async
- **Testing**: Viết test cho từng chiến lược trước khi chạy thật
- **Documentation**: Comment rõ ràng logic và tham số
- **Version control**: Commit code thường xuyên, không commit credentials

## 9. Ví dụ main.py với cấu trúc mới

```python
import asyncio
import sys
import os
from pathlib import Path

# Add the current directory to Python path
sys.path.append(str(Path(__file__).parent))

from config_manager import ConfigManager
from trading_asyncio_module import AsyncTCBSClient, AsyncOrderManager
from signal_generator import SignalGenerator

async def main():
    # Load configuration
    config = ConfigManager()
    creds = config.load_credentials()

    # Initialize API client
    async with AsyncTCBSClient(api_key=creds.api_key) as client:
        # Get authentication token
        await client._get_token()
        if not client.token:
            print('❌ Không lấy được token, kiểm tra lại API Key hoặc OTP.')
            return

        client.account_no = creds.account_id
        client.api_key = creds.api_key

        # Initialize order manager and signal generator
        order_manager = AsyncOrderManager(client)
        signal_generator = SignalGenerator(api_client=client)

        print("🚀 Khởi động hệ thống giao dịch tự động...")
        print("📊 Đang theo dõi các mã: " + ", ".join(signal_generator.symbols))

        try:
            while True:
                print("\n" + "="*50)
                print("🔄 Đang tạo tín hiệu giao dịch...")

                # Generate signals using all configured strategies
                try:
                    signals = await signal_generator.generate_signals()

                    if not signals:
                        print("ℹ️ Không có tín hiệu giao dịch nào được tạo ra")
                    else:
                        for signal in signals:
                            print("📈 Tín hiệu: {signal.symbol} | "
                                 "Loại: {signal.signal_type.name} | "
                                 "Giá: {signal.price:,.0f} | "
                                 "KL: {signal.quantity} | "
                                 "Độ tin cậy: {signal.confidence*100:.0f}%")

                            # Execute trade if confidence is high enough
                            if signal.confidence >= 0.7:
                                order_type = "NB" if signal.signal_type.name == "BUY" else "NS"
                                print("⚡ Đang đặt lệnh {order_type} {signal.quantity} {signal.symbol} @ {signal.price:,.0f}...")

                                # Place and monitor the order
                                await order_manager.place_and_monitor_order(
                                    client.account_no,
                                    signal.symbol,
                                    signal.quantity,
                                    signal.price,
                                    order_type
                                )

                except Exception as e:
                    print("❌ Lỗi khi tạo tín hiệu: {str(e)}")

                # Wait before next signal generation
                print("⏳ Đợi 30 giây trước khi kiểm tra lại...")
                await asyncio.sleep(30)

        except KeyboardInterrupt:
            print("👋 Dừng hệ thống giao dịch...")

        finally:
            # Cleanup
            if 'order_manager' in locals():
                await order_manager.stop_monitoring()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("👋 Đã dừng chương trình")
    except Exception as e:
        print("❌ Lỗi nghiêm trọng: {str(e)}")
```

## 10. Hỏi đáp nhanh

- **Muốn thêm chiến lược mới?** → Tạo class mới trong `strategies/`, kế thừa `BaseStrategy`, cấu hình trong `strategy_config.yaml`
- **Muốn thay đổi tham số?** → Chỉnh sửa `strategy_config.yaml`, không cần sửa code
- **Muốn bật/tắt chiến lược?** → Đặt `enabled: true/false` trong config
- **Muốn kết hợp nhiều chiến lược?** → Tạo `CombinedStrategy` hoặc logic trong `SignalGenerator`
- **Muốn test chiến lược?** → Chạy độc lập từng chiến lược trước khi tích hợp
- **Muốn rollback code cũ?** → Xem trong `raw_files/`

---

## 11. Liên hệ & tài liệu tham khảo
- Xem thêm `tcbs_openapi_guide.md` trong simple_wow/ để tra cứu API.
- Tham khảo tài liệu TCBS chính thức: https://developers.tcbs.com.vn
- Có thể hỏi AI assistant để được hướng dẫn chi tiết từng bước.

---

## 12. Lịch sử cập nhật
- **Phiên bản hiện tại**: Cấu trúc module hóa với `strategy_config.yaml` và thư mục `strategies/`
- **Lợi ích**: Dễ mở rộng, dễ cấu hình, dễ bảo trì
- **Tương thích ngược**: Hỗ trợ cả cách cũ (truyền `signal_sources` trực tiếp) và cách mới (qua config)

