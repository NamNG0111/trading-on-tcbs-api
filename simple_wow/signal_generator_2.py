import asyncio
from dataclasses import dataclass
from typing import Dict, List, Optional
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
    confidence: float  # Độ tin cậy (0-1)
    timestamp: str
    reason: str  # Lý do tạo tín hiệu

class SignalGenerator:
    def __init__(self, api_client):
        self.api_client = api_client
        self.signals_history: List[TradingSignal] = []

    async def generate_signals(self, signal_sources=None, symbols=None) -> List[TradingSignal]:
        signals = []
        if not signal_sources:
            raise ValueError("Bạn phải truyền vào ít nhất một chiến lược hoặc tín hiệu (signal_sources) cho SignalGenerator. Không có tín hiệu mặc định. Vui lòng chỉ định rõ chiến lược hoặc tín hiệu muốn sử dụng.")
        if symbols is None:
            symbols = ["VNM", "VCB", "TCB", "HPG"]
        for symbol in symbols:
            for src in signal_sources:
                if callable(src):
                    sig = await src(symbol)
                elif isinstance(src, TradingSignal):
                    sig = src
                elif isinstance(src, dict):
                    # Cho phép truyền dict cấu hình cứng
                    sig = TradingSignal(symbol=src.get('symbol', symbol),
                                        signal_type=src.get('signal_type', SignalType.BUY),
                                        price=src.get('price', 50000),
                                        quantity=src.get('quantity', 100),
                                        confidence=src.get('confidence', 1.0),
                                        timestamp=src.get('timestamp', self._get_current_time()),
                                        reason=src.get('reason', 'manual'))
                else:
                    sig = None
                if sig:
                    signals.append(sig)
        return signals
    async def _check_rsi_signal(self, symbol: str) -> Optional[TradingSignal]:
        try:
            current_price = await self._get_current_price(symbol)
            rsi_value = await self._calculate_rsi(symbol)
            if rsi_value > 70:
                return TradingSignal(
                    symbol=symbol,
                    signal_type=SignalType.SELL,
                    price=current_price,
                    quantity=100,
                    confidence=0.8,
                    timestamp=self._get_current_time(),
                    reason=f"RSI quá mua: {rsi_value}"
                )
            elif rsi_value < 30:
                return TradingSignal(
                    symbol=symbol,
                    signal_type=SignalType.BUY,
                    price=current_price,
                    quantity=100,
                    confidence=0.8,
                    timestamp=self._get_current_time(),
                    reason=f"RSI quá bán: {rsi_value}"
                )
        except Exception as e:
            print(f"Lỗi khi kiểm tra tín hiệu cho {symbol}: {e}")
        return None
    async def _calculate_rsi(self, symbol: str) -> float:
        # TODO: Lấy dữ liệu giá lịch sử, tính RSI thật sự
        return 50  # Placeholder
    async def _get_current_price(self, symbol: str) -> float:
        url = f"https://openapi.tcbs.com.vn/market/v1/stock/real-time/{symbol}"
        headers = {
            "Authorization": f"Bearer {self.api_client.token}",
            "apiKey": self.api_client.api_key,
            "Content-Type": "application/json"
        }
        try:
            async with self.api_client.session.get(url, headers=headers) as resp:
                data = await resp.json()
                return float(data.get("lastPrice", 0))
        except Exception as e:
            print(f"Lỗi lấy giá {symbol}: {e}")
            return 0.0
    def _get_current_time(self) -> str:
        from datetime import datetime
        return datetime.now().isoformat()
