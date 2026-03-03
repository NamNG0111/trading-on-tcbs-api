import sys
import os
import time

# Shim to allow running this file directly
if __name__ == "__main__" and (__package__ is None or __package__ == ""):
    # Add the parent directory (trading_on_tcbs_api root) to sys.path
    # This allows us to import 'stock_system_v2' as a package
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    sys.path.insert(0, parent_dir)
    
    # Import and run the main function continuously from the package context
    from stock_system_v2.main import main
    sys.exit(main())

# Relative imports work now because we forced package context above if needed
from . import config
from .auth import StockAuth
from .market_scanner import MarketScanner
from .trade_manager import TradeManager

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
