"""
Test script for technical indicators
"""
import asyncio
import numpy as np
import os

from indicators.base import IndicatorRegistry
from indicators.talib_indicators import RSI, SMA, EMA, MACD, BollingerBands, Stochastic
from indicators.custom_indicators import CustomRSI, CustomSMA, CustomEMA, PriceMomentum, Volatility
from indicators.signal_generator import SignalGenerator, SignalRule, CombinationLogic, CommonSignalRules


def generate_sample_data(length: int = 100, base_price: float = 100.0, volatility: float = 0.02):
    """Generate sample price data for testing"""
    np.random.seed(42)  # For reproducible results
    
    prices = [base_price]
    for i in range(1, length):
        change = np.random.normal(0, volatility)
        new_price = prices[-1] * (1 + change)
        prices.append(max(new_price, 1.0))  # Ensure price stays positive
    
    return np.array(prices)


async def test_individual_indicators():
    """Test individual indicators"""
    print("=== Testing Individual Indicators ===")
    
    # Generate sample data
    prices = generate_sample_data(50, 100.0, 0.02)
    current_price = prices[-1]
    
    print(f"Sample data: {len(prices)} prices, current: {current_price:.2f}")
    
    # Test indicators
    indicators_to_test = [
        ("Custom RSI", CustomRSI(period=14)),
        ("Custom SMA", CustomSMA(period=20)),
        ("Custom EMA", CustomEMA(period=20)),
        ("Price Momentum", PriceMomentum(period=10)),
        ("Volatility", Volatility(period=20))
    ]
    
    # Add TA-Lib indicators if available
    try:
        indicators_to_test.extend([
            ("TA-Lib RSI", RSI(period=14)),
            ("TA-Lib SMA", SMA(period=20)),
            ("TA-Lib EMA", EMA(period=20)),
            ("TA-Lib MACD", MACD()),
            ("TA-Lib Bollinger Bands", BollingerBands(period=20))
        ])
        print("TA-Lib indicators available")
    except ImportError:
        print("TA-Lib not available, using custom indicators only")
    
    for name, indicator in indicators_to_test:
        try:
            result = indicator.calculate(prices)
            
            if isinstance(result.values, dict):
                # Multi-value indicators like MACD, Bollinger Bands
                print(f"\n{name}:")
                for key, values in result.values.items():
                    if len(values) > 0 and not np.isnan(values[-1]):
                        print(f"  {key}: {values[-1]:.4f}")
            else:
                # Single-value indicators
                if len(result.values) > 0 and not np.isnan(result.values[-1]):
                    print(f"\n{name}: {result.values[-1]:.4f}")
            
            # Show signals
            if result.signals:
                print(f"  Signals: {[f'{s.signal_type.value}({s.strength:.2f})' for s in result.signals]}")
            else:
                print(f"  No signals generated")
                
        except Exception as e:
            print(f"\n{name}: Error - {e}")


async def test_signal_generation():
    """Test signal generation with multiple indicators"""
    print("\n=== Testing Signal Generation ===")
    
    # Generate sample data
    prices = generate_sample_data(100, 100.0, 0.02)
    current_price = prices[-1]
    
    # Create signal generator
    signal_gen = SignalGenerator()
    
    # Add indicators
    signal_gen.add_indicator("RSI", CustomRSI(period=14, oversold=30, overbought=70))
    signal_gen.add_indicator("SMA", CustomSMA(period=20))
    signal_gen.add_indicator("MOMENTUM", PriceMomentum(period=10, threshold=0.02))
    
    # Add signal rules
    
    # Rule 1: RSI oversold/overbought
    rsi_rule = SignalRule(
        name="RSI_SIGNALS",
        indicators=["RSI"],
        conditions={
            "RSI": {
                "signal_type": [SignalType.BUY, SignalType.SELL],
                "min_strength": 0.3
            }
        },
        logic=CombinationLogic.OR,
        min_strength=0.3
    )
    signal_gen.add_rule(rsi_rule)
    
    # Rule 2: Combined RSI + SMA
    combo_rule = SignalRule(
        name="RSI_SMA_COMBO",
        indicators=["RSI", "SMA"],
        conditions={
            "RSI": {
                "signal_type": [SignalType.BUY, SignalType.SELL],
                "min_strength": 0.2
            },
            "SMA": {
                "signal_type": [SignalType.BUY, SignalType.SELL],
                "min_strength": 0.2
            }
        },
        logic=CombinationLogic.AND,
        min_strength=0.4
    )
    signal_gen.add_rule(combo_rule)
    
    # Rule 3: Weighted combination
    weighted_rule = SignalRule(
        name="WEIGHTED_COMBO",
        indicators=["RSI", "SMA", "MOMENTUM"],
        conditions={
            "RSI": {"signal_type": [SignalType.BUY, SignalType.SELL], "min_strength": 0.1},
            "SMA": {"signal_type": [SignalType.BUY, SignalType.SELL], "min_strength": 0.1},
            "MOMENTUM": {"signal_type": [SignalType.BUY, SignalType.SELL], "min_strength": 0.1}
        },
        logic=CombinationLogic.WEIGHTED,
        weights={"RSI": 0.5, "SMA": 0.3, "MOMENTUM": 0.2},
        min_strength=0.3
    )
    signal_gen.add_rule(weighted_rule)
    
    # Generate signals
    indicator_data = {
        "RSI": prices,
        "SMA": prices,
        "MOMENTUM": prices
    }
    
    signals = signal_gen.generate_signals(indicator_data, current_price)
    
    print(f"Current price: {current_price:.2f}")
    print(f"Generated {len(signals)} signals:")
    
    for signal in signals:
        print(f"  - {signal.indicator_name}: {signal.signal_type.value} (strength: {signal.strength:.2f})")
        if signal.metadata:
            print(f"    Metadata: {signal.metadata}")


async def test_indicator_registry():
    """Test indicator registry functionality"""
    print("\n=== Testing Indicator Registry ===")
    
    # List registered indicators
    registered = IndicatorRegistry.list_indicators()
    print(f"Registered indicators: {registered}")
    
    # Create indicators from registry
    for name in registered[:3]:  # Test first 3
        try:
            indicator = IndicatorRegistry.create_indicator(name, period=14)
            if indicator:
                print(f"Created {name}: {indicator}")
            else:
                print(f"Failed to create {name}")
        except Exception as e:
            print(f"Error creating {name}: {e}")


async def test_performance():
    """Test performance of indicators with larger datasets"""
    print("\n=== Testing Performance ===")
    
    # Generate larger dataset
    large_prices = generate_sample_data(1000, 100.0, 0.02)
    
    import time
    
    indicators_to_test = [
        ("Custom RSI", CustomRSI(period=14)),
        ("Custom SMA", CustomSMA(period=50)),
        ("Custom EMA", CustomEMA(period=50))
    ]
    
    print(f"Testing with {len(large_prices)} data points:")
    
    for name, indicator in indicators_to_test:
        start_time = time.time()
        
        try:
            result = indicator.calculate(large_prices)
            end_time = time.time()
            
            calculation_time = (end_time - start_time) * 1000  # Convert to milliseconds
            valid_values = np.sum(~np.isnan(result.values)) if hasattr(result.values, '__len__') else 1
            
            print(f"  {name}: {calculation_time:.2f}ms, {valid_values} valid values")
            
        except Exception as e:
            print(f"  {name}: Error - {e}")


async def test_edge_cases():
    """Test edge cases and error handling"""
    print("\n=== Testing Edge Cases ===")
    
    # Test with insufficient data
    short_data = [100, 101, 102]
    rsi = CustomRSI(period=14)
    result = rsi.calculate(short_data)
    print(f"RSI with insufficient data: {len(result.values)} values")
    
    # Test with NaN values
    nan_data = [100, 101, np.nan, 103, 104]
    try:
        result = rsi.calculate(nan_data)
        print(f"RSI with NaN values: handled gracefully")
    except Exception as e:
        print(f"RSI with NaN values: {e}")
    
    # Test with empty data
    empty_data = []
    result = rsi.calculate(empty_data)
    print(f"RSI with empty data: {len(result.values)} values")
    
    # Test with single value
    single_data = [100]
    result = rsi.calculate(single_data)
    print(f"RSI with single value: {len(result.values)} values")


async def main():
    """Run all tests"""
    print("Technical Indicators Test Suite")
    print("=" * 50)
    
    try:
        await test_individual_indicators()
        await test_signal_generation()
        await test_indicator_registry()
        await test_performance()
        await test_edge_cases()
        
        print("\n" + "=" * 50)
        print("All tests completed!")
        
    except Exception as e:
        print(f"Error running tests: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Fix import for SignalType
    from indicators.base import SignalType
    asyncio.run(main())
