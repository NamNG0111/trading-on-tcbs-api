# signal_generator.py
from typing import List, Optional, Dict, Any
import yaml
import os
from strategies.base_strategy import BaseStrategy, TradingSignal, SignalType

class SignalGenerator:
    def __init__(self, api_client=None, config_path: str = 'strategy_config.yaml'):
        self.api_client = api_client
        self.strategies: List[BaseStrategy] = []
        self.manual_signals: List[Dict] = []
        self.symbols: List[str] = []
        self.config = self._load_config(config_path)
        self._setup_strategies()
        
    def _load_config(self, config_path: str) -> Dict:
        """Load configuration from YAML file"""
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            raise ValueError(f"Failed to load config: {e}")

    def _setup_strategies(self):
        """Initialize strategies based on config"""
        from strategies.rsi_strategy import RSIStrategy
        # Add more strategy imports as needed
        
        self.symbols = self.config.get('symbols', [])
        self.manual_signals = self.config.get('manual_signals', [])
        
        # Initialize RSI Strategy if enabled
        if self.config.get('strategies', {}).get('rsi', {}).get('enabled', False):
            rsi_config = self.config['strategies']['rsi']
            self.strategies.append(RSIStrategy(self.api_client, rsi_config))
        
        # Add more strategies here as needed

    async def generate_signals(self, symbols: List[str] = None) -> List[TradingSignal]:
        """Generate signals using all enabled strategies"""
        signals = []
        symbols = symbols or self.symbols
        
        if not symbols:
            raise ValueError("No symbols provided for signal generation")
            
        if not self.strategies and not self.manual_signals:
            raise ValueError("No strategies or manual signals configured")
        
        # Generate signals from strategies
        for symbol in symbols:
            for strategy in self.strategies:
                try:
                    signal = await strategy.generate_signal(symbol)
                    if signal:
                        signals.append(signal)
                except Exception as e:
                    print(f"Error generating signal for {symbol}: {e}")
        
        # Add manual signals
        for manual_signal in self.manual_signals:
            if manual_signal.get('symbol') in symbols:
                signals.append(TradingSignal(
                    symbol=manual_signal['symbol'],
                    signal_type=SignalType[manual_signal['signal_type']],
                    price=float(manual_signal['price']),
                    quantity=int(manual_signal['quantity']),
                    confidence=float(manual_signal.get('confidence', 1.0)),
                    timestamp=self._get_current_time(),
                    reason=manual_signal.get('reason', 'manual')
                ))
        
        return signals

    def _get_current_time(self) -> str:
        from datetime import datetime
        return datetime.now().isoformat()