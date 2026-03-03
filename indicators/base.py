"""
Base classes for technical indicators framework
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Union, Any
import numpy as np
import pandas as pd
from dataclasses import dataclass
from enum import Enum


class SignalType(Enum):
    """Signal types for trading decisions"""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    STRONG_BUY = "STRONG_BUY"
    STRONG_SELL = "STRONG_SELL"


@dataclass
class Signal:
    """Trading signal with metadata"""
    signal_type: SignalType
    strength: float  # 0.0 to 1.0
    price: float
    timestamp: pd.Timestamp
    indicator_name: str
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class IndicatorResult:
    """Result from indicator calculation"""
    values: Union[np.ndarray, pd.Series, float]
    signals: List[Signal] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.signals is None:
            self.signals = []
        if self.metadata is None:
            self.metadata = {}


class BaseIndicator(ABC):
    """Abstract base class for all technical indicators"""
    
    def __init__(self, name: str, period: int = 14, **kwargs):
        self.name = name
        self.period = period
        self.params = kwargs
        self._last_values = None
        self._last_signals = []
        
    @abstractmethod
    def calculate(self, data: Union[np.ndarray, pd.Series, List[float]], 
                  **kwargs) -> IndicatorResult:
        """
        Calculate indicator values
        
        Args:
            data: Price data (typically close prices)
            **kwargs: Additional parameters
            
        Returns:
            IndicatorResult with calculated values and signals
        """
        pass
    
    @abstractmethod
    def generate_signals(self, values: Union[np.ndarray, pd.Series], 
                        current_price: float, **kwargs) -> List[Signal]:
        """
        Generate trading signals based on indicator values
        
        Args:
            values: Calculated indicator values
            current_price: Current market price
            **kwargs: Additional parameters
            
        Returns:
            List of trading signals
        """
        pass
    
    def update(self, new_data_point: float, current_price: float = None) -> IndicatorResult:
        """
        Update indicator with new data point (for real-time updates)
        
        Args:
            new_data_point: New price data point
            current_price: Current market price for signal generation
            
        Returns:
            Updated IndicatorResult
        """
        # Default implementation - recalculate with new data
        # Subclasses can override for more efficient updates
        if self._last_values is None:
            return self.calculate([new_data_point])
        
        # Append new data and recalculate
        if isinstance(self._last_values, np.ndarray):
            data = np.append(self._last_values, new_data_point)
        else:
            data = list(self._last_values) + [new_data_point]
            
        return self.calculate(data)
    
    def get_required_periods(self) -> int:
        """Get minimum number of periods required for calculation"""
        return self.period
    
    def validate_data(self, data: Union[np.ndarray, pd.Series, List[float]]) -> bool:
        """Validate input data"""
        if data is None or len(data) == 0:
            return False
        
        if len(data) < self.get_required_periods():
            return False
            
        # Check for NaN or infinite values
        if isinstance(data, (np.ndarray, pd.Series)):
            if np.any(np.isnan(data)) or np.any(np.isinf(data)):
                return False
        
        return True
    
    def __str__(self) -> str:
        return f"{self.name}({self.period})"
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}', period={self.period}, params={self.params})"


class CompositeIndicator(BaseIndicator):
    """Base class for indicators that combine multiple indicators"""
    
    def __init__(self, name: str, indicators: List[BaseIndicator], **kwargs):
        super().__init__(name, **kwargs)
        self.indicators = indicators
        self.period = max(ind.get_required_periods() for ind in indicators)
    
    def calculate(self, data: Union[np.ndarray, pd.Series, List[float]], 
                  **kwargs) -> IndicatorResult:
        """Calculate all component indicators"""
        results = {}
        all_signals = []
        
        for indicator in self.indicators:
            if indicator.validate_data(data):
                result = indicator.calculate(data, **kwargs)
                results[indicator.name] = result
                all_signals.extend(result.signals)
        
        # Combine results - subclasses should override this
        combined_values = self._combine_results(results)
        combined_signals = self._combine_signals(all_signals, data[-1] if len(data) > 0 else 0)
        
        return IndicatorResult(
            values=combined_values,
            signals=combined_signals,
            metadata={'component_results': results}
        )
    
    @abstractmethod
    def _combine_results(self, results: Dict[str, IndicatorResult]) -> Union[np.ndarray, pd.Series, float]:
        """Combine results from component indicators"""
        pass
    
    @abstractmethod
    def _combine_signals(self, signals: List[Signal], current_price: float) -> List[Signal]:
        """Combine signals from component indicators"""
        pass


class IndicatorRegistry:
    """Registry for managing available indicators"""
    
    _indicators: Dict[str, type] = {}
    
    @classmethod
    def register(cls, name: str, indicator_class: type):
        """Register an indicator class"""
        cls._indicators[name] = indicator_class
    
    @classmethod
    def get_indicator(cls, name: str) -> Optional[type]:
        """Get indicator class by name"""
        return cls._indicators.get(name)
    
    @classmethod
    def list_indicators(cls) -> List[str]:
        """List all registered indicators"""
        return list(cls._indicators.keys())
    
    @classmethod
    def create_indicator(cls, name: str, **kwargs) -> Optional[BaseIndicator]:
        """Create indicator instance by name"""
        indicator_class = cls.get_indicator(name)
        if indicator_class:
            return indicator_class(**kwargs)
        return None


def register_indicator(name: str):
    """Decorator to register indicators"""
    def decorator(indicator_class):
        IndicatorRegistry.register(name, indicator_class)
        return indicator_class
    return decorator
