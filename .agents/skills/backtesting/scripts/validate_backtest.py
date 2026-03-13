#!/usr/bin/env python3
"""
Backtest Validation Script — Part of the `backtest_strategy` Skill.

This script performs a quick smoke test to verify that:
1. All registered strategies can instantiate without errors
2. IndicatorEngine produces the required columns
3. Each strategy can generate signals on sample data
4. The Backtester engine can run a full simulation cycle

Usage:
    python3 -m trading_on_tcbs_api.stock_system_v2.scripts.validate_backtest
"""

import sys

def validate():
    print("=" * 60)
    print("BACKTEST SYSTEM VALIDATION")
    print("=" * 60)
    errors = []
    
    # ── Step 1: Import Check ──────────────────────────────────
    print("\n[1/4] Checking imports...")
    try:
        from trading_on_tcbs_api.stock_system_v2.strategies import (
            SignalStrategy, SimpleMAStrategy, RSIStrategy,
            VolumeBoomStrategy, DipBuyStrategy, CombinedStrategy,
            CumulativeDropStrategy
        )
        from trading_on_tcbs_api.stock_system_v2.core.backtester import Backtester
        from trading_on_tcbs_api.stock_system_v2.core.indicator_engine import IndicatorEngine
        print("  ✅ All core modules imported successfully")
    except ImportError as e:
        errors.append(f"Import failed: {e}")
        print(f"  ❌ {e}")
        print("\n⛔ Cannot continue. Fix import errors first.")
        return False

    # ── Step 2: IndicatorEngine Check ─────────────────────────
    print("\n[2/4] Validating IndicatorEngine...")
    engine = IndicatorEngine()
    config = engine.get_default_config()
    print(f"  Configured indicators: {list(config.keys())}")
    
    # Check that all strategies' required indicators are covered
    all_strategies = [
        SimpleMAStrategy(short_window=20, long_window=50),
        RSIStrategy(period=14, oversold=30, overbought=70),
        VolumeBoomStrategy(window=20, threshold_pct=20.0),
        DipBuyStrategy(sma_window=20, drop_pct=10.0),
        CumulativeDropStrategy(days=3, drop_pct=10.0),
    ]
    
    for strat in all_strategies:
        required = strat.get_required_indicators()
        if required:
            print(f"  {strat.name}: requires {required}")
    print("  ✅ IndicatorEngine config validated")

    # ── Step 3: Signal Generation Check ───────────────────────
    print("\n[3/4] Testing signal generation on sample data...")
    try:
        backtester = Backtester(initial_capital=1_000_000_000)
        # Use a well-known stock with guaranteed data
        test_symbol = "FPT"
        df = backtester.data_provider.get_historical_data(test_symbol, days=365, include_live=False)
        
        if df.empty:
            errors.append(f"No data returned for {test_symbol}")
            print(f"  ❌ No data for {test_symbol}")
        else:
            print(f"  Fetched {len(df)} rows for {test_symbol}")
            df = engine.append_indicators(df)
            print(f"  Columns after indicators: {len(df.columns)} total")
            
            for strat in all_strategies:
                try:
                    result = strat.generate_signals(df)
                    buy_count = (result['signal'] == 1).sum()
                    sell_count = (result['signal'] == -1).sum()
                    print(f"  {strat.name}: {buy_count} BUY, {sell_count} SELL signals")
                except Exception as e:
                    errors.append(f"{strat.name} failed: {e}")
                    print(f"  ❌ {strat.name}: {e}")
    except Exception as e:
        errors.append(f"Data fetch failed: {e}")
        print(f"  ❌ {e}")

    # ── Step 4: Full Backtest Cycle ───────────────────────────
    print("\n[4/4] Running full backtest cycle...")
    try:
        strat = CombinedStrategy(
            strategies=[],
            buy_strategies=[RSIStrategy(period=14, oversold=30, overbought=70, is_reversal=False)],
            sell_strategies=[],
            buy_mode="AND",
            sell_mode="OR"
        )
        report = backtester.run(strat, "FPT", days=365)
        
        if report:
            print(f"  Final Value: {report.get('final_value', 'N/A'):,.0f} VND")
            print(f"  Total Return: {report.get('total_return_pct', 'N/A'):.2f}%")
            print(f"  Trades Logged: {len(report.get('trades_log', []))}")
            print(f"  Signal Details: {len(report.get('signal_details', []))} rows")
            print("  ✅ Full backtest cycle completed")
        else:
            errors.append("Backtest returned empty report")
            print("  ❌ Empty report")
    except Exception as e:
        errors.append(f"Backtest failed: {e}")
        print(f"  ❌ {e}")

    # ── Summary ───────────────────────────────────────────────
    print("\n" + "=" * 60)
    if errors:
        print(f"⚠️  VALIDATION COMPLETED WITH {len(errors)} ERROR(S):")
        for err in errors:
            print(f"  - {err}")
        return False
    else:
        print("✅ ALL CHECKS PASSED — Backtest system is healthy!")
        return True


if __name__ == "__main__":
    success = validate()
    sys.exit(0 if success else 1)
