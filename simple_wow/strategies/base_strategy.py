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