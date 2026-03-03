"""
Custom technical indicators implementation
"""
import numpy as np
import pandas as pd
from typing import List, Union, Dict, Any
from .base import BaseIndicator, IndicatorResult, Signal, SignalType, register_indicator


@register_indicator("CUSTOM_RSI")
class CustomRSI(BaseIndicator):
    """Custom RSI implementation without TA-Lib dependency"""
    
    def __init__(self, period: int = 14, oversold: float = 30, overbought: float = 70, **kwargs):
        super().__init__("CUSTOM_RSI", period, **kwargs)
        self.oversold = oversold
        self.overbought = overbought
    
    def calculate(self, data: Union[np.ndarray, pd.Series, List[float]], 
                  **kwargs) -> IndicatorResult:
        """Calculate RSI using custom implementation"""
        if not self.validate_data(data):
            return IndicatorResult(values=np.array([]))
        
        # Convert to numpy array
        if isinstance(data, pd.Series):
            prices = data.values
        elif isinstance(data, list):
            prices = np.array(data, dtype=float)
        else:
            prices = data.astype(float)
        
        # Calculate price changes
        deltas = np.diff(prices)
        
        # Separate gains and losses
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        # Calculate average gains and losses
        avg_gains = np.zeros_like(prices)
        avg_losses = np.zeros_like(prices)
        
        if len(gains) >= self.period:
            # Initial averages
            avg_gains[self.period] = np.mean(gains[:self.period])
            avg_losses[self.period] = np.mean(losses[:self.period])
            
            # Smoothed averages (Wilder's smoothing)
            for i in range(self.period + 1, len(prices)):
                avg_gains[i] = (avg_gains[i-1] * (self.period - 1) + gains[i-1]) / self.period
                avg_losses[i] = (avg_losses[i-1] * (self.period - 1) + losses[i-1]) / self.period
        
        # Calculate RSI
        rsi = np.full_like(prices, np.nan)
        valid_mask = (avg_losses != 0) & (avg_gains + avg_losses != 0)
        
        rs = np.divide(avg_gains, avg_losses, out=np.zeros_like(avg_gains), where=avg_losses!=0)
        rsi[valid_mask] = 100 - (100 / (1 + rs[valid_mask]))
        
        # Generate signals
        current_price = prices[-1] if len(prices) > 0 else 0
        signals = self.generate_signals(rsi, current_price)
        
        return IndicatorResult(
            values=rsi,
            signals=signals,
            metadata={'period': self.period, 'implementation': 'custom'}
        )
    
    def generate_signals(self, values: Union[np.ndarray, pd.Series], 
                        current_price: float, **kwargs) -> List[Signal]:
        """Generate RSI-based signals"""
        signals = []
        
        if len(values) == 0 or np.isnan(values[-1]):
            return signals
            
        current_rsi = values[-1]
        timestamp = pd.Timestamp.now()
        
        if current_rsi <= self.oversold:
            signals.append(Signal(
                signal_type=SignalType.BUY,
                strength=min(1.0, (self.oversold - current_rsi) / self.oversold),
                price=current_price,
                timestamp=timestamp,
                indicator_name=self.name,
                metadata={'rsi_value': current_rsi, 'threshold': self.oversold}
            ))
        elif current_rsi >= self.overbought:
            signals.append(Signal(
                signal_type=SignalType.SELL,
                strength=min(1.0, (current_rsi - self.overbought) / (100 - self.overbought)),
                price=current_price,
                timestamp=timestamp,
                indicator_name=self.name,
                metadata={'rsi_value': current_rsi, 'threshold': self.overbought}
            ))
        
        return signals


@register_indicator("CUSTOM_SMA")
class CustomSMA(BaseIndicator):
    """Custom Simple Moving Average implementation"""
    
    def __init__(self, period: int = 20, **kwargs):
        super().__init__("CUSTOM_SMA", period, **kwargs)
    
    def calculate(self, data: Union[np.ndarray, pd.Series, List[float]], 
                  **kwargs) -> IndicatorResult:
        """Calculate SMA using custom implementation"""
        if not self.validate_data(data):
            return IndicatorResult(values=np.array([]))
        
        # Convert to numpy array
        if isinstance(data, pd.Series):
            prices = data.values
        elif isinstance(data, list):
            prices = np.array(data, dtype=float)
        else:
            prices = data.astype(float)
        
        # Calculate SMA
        sma = np.full_like(prices, np.nan)
        
        for i in range(self.period - 1, len(prices)):
            sma[i] = np.mean(prices[i - self.period + 1:i + 1])
        
        # Generate signals
        current_price = prices[-1] if len(prices) > 0 else 0
        signals = self.generate_signals(sma, current_price)
        
        return IndicatorResult(
            values=sma,
            signals=signals,
            metadata={'period': self.period, 'implementation': 'custom'}
        )
    
    def generate_signals(self, values: Union[np.ndarray, pd.Series], 
                        current_price: float, **kwargs) -> List[Signal]:
        """Generate SMA crossover signals"""
        signals = []
        
        if len(values) < 2 or np.isnan(values[-1]):
            return signals
            
        current_sma = values[-1]
        timestamp = pd.Timestamp.now()
        
        # Price vs SMA crossover
        if current_price > current_sma:
            signals.append(Signal(
                signal_type=SignalType.BUY,
                strength=min(1.0, (current_price - current_sma) / current_sma),
                price=current_price,
                timestamp=timestamp,
                indicator_name=self.name,
                metadata={'sma_value': current_sma, 'crossover': 'above'}
            ))
        elif current_price < current_sma:
            signals.append(Signal(
                signal_type=SignalType.SELL,
                strength=min(1.0, (current_sma - current_price) / current_sma),
                price=current_price,
                timestamp=timestamp,
                indicator_name=self.name,
                metadata={'sma_value': current_sma, 'crossover': 'below'}
            ))
        
        return signals


@register_indicator("CUSTOM_EMA")
class CustomEMA(BaseIndicator):
    """Custom Exponential Moving Average implementation"""
    
    def __init__(self, period: int = 20, **kwargs):
        super().__init__("CUSTOM_EMA", period, **kwargs)
        self.alpha = 2.0 / (period + 1)  # Smoothing factor
    
    def calculate(self, data: Union[np.ndarray, pd.Series, List[float]], 
                  **kwargs) -> IndicatorResult:
        """Calculate EMA using custom implementation"""
        if not self.validate_data(data):
            return IndicatorResult(values=np.array([]))
        
        # Convert to numpy array
        if isinstance(data, pd.Series):
            prices = data.values
        elif isinstance(data, list):
            prices = np.array(data, dtype=float)
        else:
            prices = data.astype(float)
        
        # Calculate EMA
        ema = np.full_like(prices, np.nan)
        
        if len(prices) >= self.period:
            # Initialize with SMA
            ema[self.period - 1] = np.mean(prices[:self.period])
            
            # Calculate EMA for remaining values
            for i in range(self.period, len(prices)):
                ema[i] = self.alpha * prices[i] + (1 - self.alpha) * ema[i - 1]
        
        # Generate signals
        current_price = prices[-1] if len(prices) > 0 else 0
        signals = self.generate_signals(ema, current_price)
        
        return IndicatorResult(
            values=ema,
            signals=signals,
            metadata={'period': self.period, 'alpha': self.alpha, 'implementation': 'custom'}
        )
    
    def generate_signals(self, values: Union[np.ndarray, pd.Series], 
                        current_price: float, **kwargs) -> List[Signal]:
        """Generate EMA crossover signals"""
        signals = []
        
        if len(values) < 2 or np.isnan(values[-1]):
            return signals
            
        current_ema = values[-1]
        timestamp = pd.Timestamp.now()
        
        # Price vs EMA crossover
        if current_price > current_ema:
            signals.append(Signal(
                signal_type=SignalType.BUY,
                strength=min(1.0, (current_price - current_ema) / current_ema),
                price=current_price,
                timestamp=timestamp,
                indicator_name=self.name,
                metadata={'ema_value': current_ema, 'crossover': 'above'}
            ))
        elif current_price < current_ema:
            signals.append(Signal(
                signal_type=SignalType.SELL,
                strength=min(1.0, (current_ema - current_price) / current_ema),
                price=current_price,
                timestamp=timestamp,
                indicator_name=self.name,
                metadata={'ema_value': current_ema, 'crossover': 'below'}
            ))
        
        return signals


@register_indicator("PRICE_MOMENTUM")
class PriceMomentum(BaseIndicator):
    """Price Momentum indicator"""
    
    def __init__(self, period: int = 10, threshold: float = 0.02, **kwargs):
        super().__init__("PRICE_MOMENTUM", period, **kwargs)
        self.threshold = threshold  # 2% threshold by default
    
    def calculate(self, data: Union[np.ndarray, pd.Series, List[float]], 
                  **kwargs) -> IndicatorResult:
        """Calculate price momentum"""
        if not self.validate_data(data):
            return IndicatorResult(values=np.array([]))
        
        # Convert to numpy array
        if isinstance(data, pd.Series):
            prices = data.values
        elif isinstance(data, list):
            prices = np.array(data, dtype=float)
        else:
            prices = data.astype(float)
        
        # Calculate momentum (current price / price n periods ago - 1)
        momentum = np.full_like(prices, np.nan)
        
        for i in range(self.period, len(prices)):
            momentum[i] = (prices[i] / prices[i - self.period]) - 1
        
        # Generate signals
        current_price = prices[-1] if len(prices) > 0 else 0
        signals = self.generate_signals(momentum, current_price)
        
        return IndicatorResult(
            values=momentum,
            signals=signals,
            metadata={'period': self.period, 'threshold': self.threshold}
        )
    
    def generate_signals(self, values: Union[np.ndarray, pd.Series], 
                        current_price: float, **kwargs) -> List[Signal]:
        """Generate momentum-based signals"""
        signals = []
        
        if len(values) == 0 or np.isnan(values[-1]):
            return signals
            
        current_momentum = values[-1]
        timestamp = pd.Timestamp.now()
        
        if current_momentum > self.threshold:
            signals.append(Signal(
                signal_type=SignalType.BUY,
                strength=min(1.0, current_momentum / (self.threshold * 2)),
                price=current_price,
                timestamp=timestamp,
                indicator_name=self.name,
                metadata={'momentum': current_momentum, 'threshold': self.threshold}
            ))
        elif current_momentum < -self.threshold:
            signals.append(Signal(
                signal_type=SignalType.SELL,
                strength=min(1.0, abs(current_momentum) / (self.threshold * 2)),
                price=current_price,
                timestamp=timestamp,
                indicator_name=self.name,
                metadata={'momentum': current_momentum, 'threshold': -self.threshold}
            ))
        
        return signals


@register_indicator("VOLATILITY")
class Volatility(BaseIndicator):
    """Price Volatility indicator"""
    
    def __init__(self, period: int = 20, high_vol_threshold: float = 0.02, **kwargs):
        super().__init__("VOLATILITY", period, **kwargs)
        self.high_vol_threshold = high_vol_threshold
    
    def calculate(self, data: Union[np.ndarray, pd.Series, List[float]], 
                  **kwargs) -> IndicatorResult:
        """Calculate price volatility (rolling standard deviation of returns)"""
        if not self.validate_data(data):
            return IndicatorResult(values=np.array([]))
        
        # Convert to numpy array
        if isinstance(data, pd.Series):
            prices = data.values
        elif isinstance(data, list):
            prices = np.array(data, dtype=float)
        else:
            prices = data.astype(float)
        
        # Calculate returns
        returns = np.diff(prices) / prices[:-1]
        
        # Calculate rolling volatility
        volatility = np.full_like(prices, np.nan)
        
        for i in range(self.period, len(prices)):
            volatility[i] = np.std(returns[i - self.period:i])
        
        # Generate signals
        current_price = prices[-1] if len(prices) > 0 else 0
        signals = self.generate_signals(volatility, current_price)
        
        return IndicatorResult(
            values=volatility,
            signals=signals,
            metadata={'period': self.period, 'high_vol_threshold': self.high_vol_threshold}
        )
    
    def generate_signals(self, values: Union[np.ndarray, pd.Series], 
                        current_price: float, **kwargs) -> List[Signal]:
        """Generate volatility-based signals"""
        signals = []
        
        if len(values) == 0 or np.isnan(values[-1]):
            return signals
            
        current_volatility = values[-1]
        timestamp = pd.Timestamp.now()
        
        # High volatility might indicate trend change or breakout
        if current_volatility > self.high_vol_threshold:
            signals.append(Signal(
                signal_type=SignalType.HOLD,  # High volatility = wait for direction
                strength=min(1.0, current_volatility / self.high_vol_threshold),
                price=current_price,
                timestamp=timestamp,
                indicator_name=self.name,
                metadata={
                    'volatility': current_volatility,
                    'threshold': self.high_vol_threshold,
                    'condition': 'high_volatility'
                }
            ))
        
        return signals
