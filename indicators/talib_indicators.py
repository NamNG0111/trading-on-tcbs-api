"""
TA-Lib based technical indicators implementation
"""
import numpy as np
import pandas as pd
from typing import List, Union, Dict, Any
from .base import BaseIndicator, IndicatorResult, Signal, SignalType, register_indicator

try:
    import talib
    TALIB_AVAILABLE = True
except ImportError:
    TALIB_AVAILABLE = False
    print("Warning: TA-Lib not available. Install with: pip install TA-Lib")


class TALibIndicator(BaseIndicator):
    """Base class for TA-Lib indicators"""
    
    def __init__(self, name: str, talib_func_name: str, period: int = 14, **kwargs):
        super().__init__(name, period, **kwargs)
        self.talib_func_name = talib_func_name
        self.talib_func = getattr(talib, talib_func_name) if TALIB_AVAILABLE else None
        
    def calculate(self, data: Union[np.ndarray, pd.Series, List[float]], 
                  **kwargs) -> IndicatorResult:
        """Calculate indicator using TA-Lib"""
        if not TALIB_AVAILABLE:
            raise ImportError("TA-Lib is required for this indicator")
            
        if not self.validate_data(data):
            return IndicatorResult(values=np.array([]))
        
        # Convert to numpy array
        if isinstance(data, pd.Series):
            prices = data.values
        elif isinstance(data, list):
            prices = np.array(data, dtype=float)
        else:
            prices = data.astype(float)
        
        # Calculate indicator
        try:
            if self.period:
                values = self.talib_func(prices, timeperiod=self.period, **self.params)
            else:
                values = self.talib_func(prices, **self.params)
                
            # Generate signals
            current_price = prices[-1] if len(prices) > 0 else 0
            signals = self.generate_signals(values, current_price)
            
            self._last_values = values
            self._last_signals = signals
            
            return IndicatorResult(
                values=values,
                signals=signals,
                metadata={'talib_function': self.talib_func_name}
            )
            
        except Exception as e:
            return IndicatorResult(
                values=np.array([]),
                signals=[],
                metadata={'error': str(e)}
            )


@register_indicator("RSI")
class RSI(TALibIndicator):
    """Relative Strength Index"""
    
    def __init__(self, period: int = 14, oversold: float = 30, overbought: float = 70, **kwargs):
        super().__init__("RSI", "RSI", period, **kwargs)
        self.oversold = oversold
        self.overbought = overbought
    
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


@register_indicator("SMA")
class SMA(TALibIndicator):
    """Simple Moving Average"""
    
    def __init__(self, period: int = 20, **kwargs):
        super().__init__("SMA", "SMA", period, **kwargs)
    
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


@register_indicator("EMA")
class EMA(TALibIndicator):
    """Exponential Moving Average"""
    
    def __init__(self, period: int = 20, **kwargs):
        super().__init__("EMA", "EMA", period, **kwargs)
    
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


@register_indicator("MACD")
class MACD(TALibIndicator):
    """Moving Average Convergence Divergence"""
    
    def __init__(self, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9, **kwargs):
        super().__init__("MACD", "MACD", slow_period, **kwargs)
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
        self.params.update({
            'fastperiod': fast_period,
            'slowperiod': slow_period,
            'signalperiod': signal_period
        })
    
    def calculate(self, data: Union[np.ndarray, pd.Series, List[float]], 
                  **kwargs) -> IndicatorResult:
        """Calculate MACD"""
        if not TALIB_AVAILABLE:
            raise ImportError("TA-Lib is required for MACD")
            
        if not self.validate_data(data):
            return IndicatorResult(values={'macd': np.array([]), 'signal': np.array([]), 'histogram': np.array([])})
        
        # Convert to numpy array
        if isinstance(data, pd.Series):
            prices = data.values
        elif isinstance(data, list):
            prices = np.array(data, dtype=float)
        else:
            prices = data.astype(float)
        
        try:
            macd, signal, histogram = talib.MACD(
                prices, 
                fastperiod=self.fast_period,
                slowperiod=self.slow_period,
                signalperiod=self.signal_period
            )
            
            values = {
                'macd': macd,
                'signal': signal,
                'histogram': histogram
            }
            
            # Generate signals
            current_price = prices[-1] if len(prices) > 0 else 0
            signals = self.generate_signals(values, current_price)
            
            return IndicatorResult(
                values=values,
                signals=signals,
                metadata={'periods': {'fast': self.fast_period, 'slow': self.slow_period, 'signal': self.signal_period}}
            )
            
        except Exception as e:
            return IndicatorResult(
                values={'macd': np.array([]), 'signal': np.array([]), 'histogram': np.array([])},
                signals=[],
                metadata={'error': str(e)}
            )
    
    def generate_signals(self, values: Dict[str, np.ndarray], 
                        current_price: float, **kwargs) -> List[Signal]:
        """Generate MACD signals"""
        signals = []
        
        macd = values.get('macd', np.array([]))
        signal_line = values.get('signal', np.array([]))
        histogram = values.get('histogram', np.array([]))
        
        if len(macd) < 2 or len(signal_line) < 2:
            return signals
            
        current_macd = macd[-1]
        current_signal = signal_line[-1]
        current_histogram = histogram[-1]
        prev_histogram = histogram[-2]
        
        timestamp = pd.Timestamp.now()
        
        # MACD line crosses above signal line
        if current_histogram > 0 and prev_histogram <= 0:
            signals.append(Signal(
                signal_type=SignalType.BUY,
                strength=min(1.0, abs(current_histogram) / abs(current_macd) if current_macd != 0 else 0.5),
                price=current_price,
                timestamp=timestamp,
                indicator_name=self.name,
                metadata={
                    'macd': current_macd,
                    'signal': current_signal,
                    'histogram': current_histogram,
                    'crossover': 'bullish'
                }
            ))
        # MACD line crosses below signal line
        elif current_histogram < 0 and prev_histogram >= 0:
            signals.append(Signal(
                signal_type=SignalType.SELL,
                strength=min(1.0, abs(current_histogram) / abs(current_macd) if current_macd != 0 else 0.5),
                price=current_price,
                timestamp=timestamp,
                indicator_name=self.name,
                metadata={
                    'macd': current_macd,
                    'signal': current_signal,
                    'histogram': current_histogram,
                    'crossover': 'bearish'
                }
            ))
        
        return signals


@register_indicator("BBANDS")
class BollingerBands(TALibIndicator):
    """Bollinger Bands"""
    
    def __init__(self, period: int = 20, std_dev: float = 2.0, **kwargs):
        super().__init__("BBANDS", "BBANDS", period, **kwargs)
        self.std_dev = std_dev
        self.params.update({'nbdevup': std_dev, 'nbdevdn': std_dev})
    
    def calculate(self, data: Union[np.ndarray, pd.Series, List[float]], 
                  **kwargs) -> IndicatorResult:
        """Calculate Bollinger Bands"""
        if not TALIB_AVAILABLE:
            raise ImportError("TA-Lib is required for Bollinger Bands")
            
        if not self.validate_data(data):
            return IndicatorResult(values={'upper': np.array([]), 'middle': np.array([]), 'lower': np.array([])})
        
        # Convert to numpy array
        if isinstance(data, pd.Series):
            prices = data.values
        elif isinstance(data, list):
            prices = np.array(data, dtype=float)
        else:
            prices = data.astype(float)
        
        try:
            upper, middle, lower = talib.BBANDS(
                prices,
                timeperiod=self.period,
                nbdevup=self.std_dev,
                nbdevdn=self.std_dev
            )
            
            values = {
                'upper': upper,
                'middle': middle,
                'lower': lower
            }
            
            # Generate signals
            current_price = prices[-1] if len(prices) > 0 else 0
            signals = self.generate_signals(values, current_price)
            
            return IndicatorResult(
                values=values,
                signals=signals,
                metadata={'period': self.period, 'std_dev': self.std_dev}
            )
            
        except Exception as e:
            return IndicatorResult(
                values={'upper': np.array([]), 'middle': np.array([]), 'lower': np.array([])},
                signals=[],
                metadata={'error': str(e)}
            )
    
    def generate_signals(self, values: Dict[str, np.ndarray], 
                        current_price: float, **kwargs) -> List[Signal]:
        """Generate Bollinger Bands signals"""
        signals = []
        
        upper = values.get('upper', np.array([]))
        middle = values.get('middle', np.array([]))
        lower = values.get('lower', np.array([]))
        
        if len(upper) == 0 or np.isnan(upper[-1]):
            return signals
            
        current_upper = upper[-1]
        current_middle = middle[-1]
        current_lower = lower[-1]
        
        timestamp = pd.Timestamp.now()
        
        # Price touches or exceeds lower band (oversold)
        if current_price <= current_lower:
            signals.append(Signal(
                signal_type=SignalType.BUY,
                strength=min(1.0, (current_lower - current_price) / (current_middle - current_lower)),
                price=current_price,
                timestamp=timestamp,
                indicator_name=self.name,
                metadata={
                    'upper_band': current_upper,
                    'middle_band': current_middle,
                    'lower_band': current_lower,
                    'position': 'at_lower_band'
                }
            ))
        # Price touches or exceeds upper band (overbought)
        elif current_price >= current_upper:
            signals.append(Signal(
                signal_type=SignalType.SELL,
                strength=min(1.0, (current_price - current_upper) / (current_upper - current_middle)),
                price=current_price,
                timestamp=timestamp,
                indicator_name=self.name,
                metadata={
                    'upper_band': current_upper,
                    'middle_band': current_middle,
                    'lower_band': current_lower,
                    'position': 'at_upper_band'
                }
            ))
        
        return signals


@register_indicator("STOCH")
class Stochastic(TALibIndicator):
    """Stochastic Oscillator"""
    
    def __init__(self, k_period: int = 14, d_period: int = 3, oversold: float = 20, overbought: float = 80, **kwargs):
        super().__init__("STOCH", "STOCH", k_period, **kwargs)
        self.k_period = k_period
        self.d_period = d_period
        self.oversold = oversold
        self.overbought = overbought
    
    def calculate(self, data: Union[np.ndarray, pd.Series, List[float]], 
                  high_data: Union[np.ndarray, pd.Series, List[float]] = None,
                  low_data: Union[np.ndarray, pd.Series, List[float]] = None,
                  **kwargs) -> IndicatorResult:
        """Calculate Stochastic Oscillator"""
        if not TALIB_AVAILABLE:
            raise ImportError("TA-Lib is required for Stochastic")
            
        # If high/low not provided, use close price as approximation
        if high_data is None:
            high_data = data
        if low_data is None:
            low_data = data
            
        if not self.validate_data(data):
            return IndicatorResult(values={'k': np.array([]), 'd': np.array([])})
        
        # Convert to numpy arrays
        def to_array(d):
            if isinstance(d, pd.Series):
                return d.values
            elif isinstance(d, list):
                return np.array(d, dtype=float)
            else:
                return d.astype(float)
        
        high_prices = to_array(high_data)
        low_prices = to_array(low_data)
        close_prices = to_array(data)
        
        try:
            k_percent, d_percent = talib.STOCH(
                high_prices, low_prices, close_prices,
                fastk_period=self.k_period,
                slowk_period=self.d_period,
                slowd_period=self.d_period
            )
            
            values = {
                'k': k_percent,
                'd': d_percent
            }
            
            # Generate signals
            current_price = close_prices[-1] if len(close_prices) > 0 else 0
            signals = self.generate_signals(values, current_price)
            
            return IndicatorResult(
                values=values,
                signals=signals,
                metadata={'k_period': self.k_period, 'd_period': self.d_period}
            )
            
        except Exception as e:
            return IndicatorResult(
                values={'k': np.array([]), 'd': np.array([])},
                signals=[],
                metadata={'error': str(e)}
            )
    
    def generate_signals(self, values: Dict[str, np.ndarray], 
                        current_price: float, **kwargs) -> List[Signal]:
        """Generate Stochastic signals"""
        signals = []
        
        k_values = values.get('k', np.array([]))
        d_values = values.get('d', np.array([]))
        
        if len(k_values) == 0 or np.isnan(k_values[-1]):
            return signals
            
        current_k = k_values[-1]
        current_d = d_values[-1] if len(d_values) > 0 else current_k
        
        timestamp = pd.Timestamp.now()
        
        # Oversold condition
        if current_k <= self.oversold and current_d <= self.oversold:
            signals.append(Signal(
                signal_type=SignalType.BUY,
                strength=min(1.0, (self.oversold - current_k) / self.oversold),
                price=current_price,
                timestamp=timestamp,
                indicator_name=self.name,
                metadata={
                    'k_value': current_k,
                    'd_value': current_d,
                    'condition': 'oversold'
                }
            ))
        # Overbought condition
        elif current_k >= self.overbought and current_d >= self.overbought:
            signals.append(Signal(
                signal_type=SignalType.SELL,
                strength=min(1.0, (current_k - self.overbought) / (100 - self.overbought)),
                price=current_price,
                timestamp=timestamp,
                indicator_name=self.name,
                metadata={
                    'k_value': current_k,
                    'd_value': current_d,
                    'condition': 'overbought'
                }
            ))
        
        return signals
