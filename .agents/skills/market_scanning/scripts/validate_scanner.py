#!/usr/bin/env python3
"""
Market Scanning Validation Script — Part of the `market_scanning` Skill.

Performs a quick health check to verify:
1. TCBS Authentication works
2. DataProvider can fetch and cache data
3. Live candle merge logic works
4. MarketScanner produces valid results

Usage:
    python3 -m trading_on_tcbs_api.stock_system_v2.scripts.validate_scanner
"""

import sys
from datetime import datetime


def validate():
    print("=" * 60)
    print("MARKET SCANNER VALIDATION")
    print("=" * 60)
    errors = []

    # ── Step 1: Import Check ──────────────────────────────────
    print("\n[1/5] Checking imports...")
    try:
        from trading_on_tcbs_api.stock_system_v2.core.market_scanner import MarketScanner
        from trading_on_tcbs_api.stock_system_v2.auth.auth import StockAuth
        from trading_on_tcbs_api.stock_system_v2.data_ingest.data_provider import DataProvider
        from trading_on_tcbs_api.stock_system_v2.core.indicator_engine import IndicatorEngine
        from trading_on_tcbs_api.stock_system_v2.strategies import (
            RSIStrategy, CombinedStrategy
        )
        print("  ✅ All modules imported")
    except ImportError as e:
        errors.append(f"Import failed: {e}")
        print(f"  ❌ {e}")
        return False

    # ── Step 2: Authentication ────────────────────────────────
    print("\n[2/5] Testing TCBS authentication...")
    try:
        auth = StockAuth()
        if auth.validate():
            print(f"  ✅ Auth successful (token length: {len(auth.token)})")
        else:
            errors.append("Auth validation returned False")
            print("  ❌ Auth failed — live prices will not work")
    except Exception as e:
        errors.append(f"Auth error: {e}")
        print(f"  ❌ {e}")

    # ── Step 3: DataProvider Cache + Freshness ────────────────
    print("\n[3/5] Testing DataProvider...")
    try:
        provider = DataProvider(auth=auth)
        expected_date = provider.get_expected_fresh_date()
        is_trading = provider.is_trading_day(datetime.now().date())
        print(f"  Expected fresh date: {expected_date}")
        print(f"  Today is trading day: {is_trading}")

        df = provider.get_historical_data("FPT", days=30, include_live=False)
        if not df.empty:
            print(f"  FPT data: {len(df)} rows, last date: {df['time'].max().date()}")
            print("  ✅ DataProvider working")
        else:
            errors.append("DataProvider returned empty DataFrame for FPT")
            print("  ❌ No data returned")
    except Exception as e:
        errors.append(f"DataProvider error: {e}")
        print(f"  ❌ {e}")

    # ── Step 4: Live Candle Merge ─────────────────────────────
    print("\n[4/5] Testing live candle merge...")
    try:
        df_live = provider.get_historical_data("FPT", days=30, include_live=True)
        df_no_live = provider.get_historical_data("FPT", days=30, include_live=False)

        live_last = df_live['time'].max().date()
        no_live_last = df_no_live['time'].max().date()
        rows_diff = len(df_live) - len(df_no_live)

        print(f"  Without live: last date = {no_live_last}, rows = {len(df_no_live)}")
        print(f"  With live:    last date = {live_last}, rows = {len(df_live)}")

        if datetime.now().weekday() < 5 and datetime.now().hour >= 9:
            if rows_diff > 0 or live_last > no_live_last:
                print("  ✅ Live candle appended successfully")
            else:
                print("  ⚠️  Live candle not appended (may be outside market hours or weekend)")
        else:
            print("  ℹ️  Market closed — live candle not expected")
    except Exception as e:
        errors.append(f"Live candle error: {e}")
        print(f"  ❌ {e}")

    # ── Step 5: Full Scanner Cycle ────────────────────────────
    print("\n[5/5] Running mini scanner cycle...")
    try:
        strat = CombinedStrategy(
            strategies=[],
            buy_strategies=[RSIStrategy(period=14, oversold=30, overbought=70, is_reversal=False)],
            sell_strategies=[],
            buy_mode="AND",
            sell_mode="OR"
        )
        scanner = MarketScanner(
            strategies={"RSI Test": strat},
            auth=auth
        )
        results = scanner.scan_to_df(["FPT", "HPG", "TCB"])

        if results:
            total_signals = sum(len(df) for df in results.values())
            print(f"  Found {total_signals} signal(s) across {len(results)} strategy group(s)")
            for name, df in results.items():
                print(f"    {name}: {len(df)} signal(s)")
        else:
            print("  ℹ️  No signals found (this is normal if market is calm)")

        print("  ✅ Scanner cycle completed without errors")
    except Exception as e:
        errors.append(f"Scanner error: {e}")
        print(f"  ❌ {e}")

    # ── Summary ───────────────────────────────────────────────
    print("\n" + "=" * 60)
    if errors:
        print(f"⚠️  VALIDATION COMPLETED WITH {len(errors)} ERROR(S):")
        for err in errors:
            print(f"  - {err}")
        return False
    else:
        print("✅ ALL CHECKS PASSED — Scanner system is healthy!")
        return True


if __name__ == "__main__":
    success = validate()
    sys.exit(0 if success else 1)
