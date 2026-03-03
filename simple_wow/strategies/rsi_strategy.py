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
                    reason=f"RSI {rsi_value:.2f} > {self.config.get('overbought', 70)}"
                )
            elif rsi_value < self.config.get('oversold', 30):
                return TradingSignal(
                    symbol=symbol,
                    signal_type=SignalType.BUY,
                    price=current_price,
                    quantity=self.config.get('default_quantity', 100),
                    confidence=self.config.get('confidence', 0.8),
                    timestamp=self._get_current_time(),
                    reason=f"RSI {rsi_value:.2f} < {self.config.get('oversold', 30)}"
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