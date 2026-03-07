import sys
import os
import time



# Relative imports work now because we forced package context above if needed
from trading_on_tcbs_api.stock_system_v2 import config
from trading_on_tcbs_api.stock_system_v2.auth.auth import StockAuth
from trading_on_tcbs_api.stock_system_v2.core.market_scanner import MarketScanner
from trading_on_tcbs_api.stock_system_v2.execution.trade_manager import TradeManager

def main():
    print("==========================================")
    print("   Stock System V2 - Standalone           ")
    print("==========================================")
    
    # 1. Authentication
    auth = StockAuth()
    print("Initializing Authentication...")
    if not auth.validate():
        print("❌ Authentication failed. Exiting.")
        return

    print(f"✅ Authenticated. Monitoring {len(config.SYMBOLS)} symbols: {config.SYMBOLS}")
    
    # 2. Initialize Components
    scanner = MarketScanner(auth)
    trader = TradeManager(auth)
    
    print("\nStarting Main Loop (Press Ctrl+C to stop)...")
    try:
        while True:
            print(f"[{time.strftime('%H:%M:%S')}] Scanning market...")
            
            # --- Logic ---
            opportunities = scanner.scan(config.SYMBOLS)
            for opp in opportunities:
                trader.execute(opp)
            # -------------
            
            time.sleep(10) # Wait 10 seconds between scans
            
    except KeyboardInterrupt:
        print("\n🛑 System stopped by user.")
    except Exception as e:
        print(f"\n⛔ Unexpected error: {e}")

if __name__ == "__main__":
    main()
