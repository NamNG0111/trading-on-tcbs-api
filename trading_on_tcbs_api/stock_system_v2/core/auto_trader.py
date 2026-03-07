
import sys
import os
import asyncio
import pandas as pd
from datetime import datetime

# Shim for direct execution
if __name__ == "__main__" and (__package__ is None or __package__ == ""):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # Go up 3 levels from core/ to repo root
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
    if root_dir not in sys.path:
        sys.path.insert(0, root_dir)

from trading_on_tcbs_api.stock_system_v2 import config
from trading_on_tcbs_api.stock_system_v2.auth.auth import StockAuth
from trading_on_tcbs_api.stock_system_v2.core.market_scanner import MarketScanner
from trading_on_tcbs_api.stock_system_v2.execution.order_manager import OrderManager
from trading_on_tcbs_api.stock_system_v2.finance.account_manager import AccountManager
from trading_on_tcbs_api.stock_system_v2.execution.order_tracker import OrderTracker
from trading_on_tcbs_api.stock_system_v2.strategies.ma_strategy import SimpleMAStrategy
from trading_on_tcbs_api.stock_system_v2.strategies.volume_strategy import VolumeBoomStrategy
from trading_on_tcbs_api.stock_system_v2.strategies.rsi_strategy import RSIStrategy
from trading_on_tcbs_api.stock_system_v2.strategies.combined_strategy import CombinedStrategy

class AutoTrader:
    def __init__(self, safe_mode=True):
        print(f"--- AUTO TRADER INITIALIZED (Safe Mode: {safe_mode}) ---")
        self.auth = StockAuth()
        self.auth.validate()
        
        # 1. Setup Strategy (Split Logic)
        self.ma = SimpleMAStrategy(short_window=20, long_window=50)
        self.vol = VolumeBoomStrategy(window=20, threshold_pct=10)
        self.rsi = RSIStrategy(period=14)
        
        self.strategy = CombinedStrategy(
            strategies=[],
            buy_strategies=[self.ma, self.vol],
            sell_strategies=[self.rsi],
            buy_mode="AND",
            sell_mode="OR"
        )
        
        # 2. Setup Components
        self.scanner = MarketScanner(strategy=self.strategy, auth=self.auth)
        self.order_manager = OrderManager(auth=self.auth, safe_mode=safe_mode)
        
        # 3. Financial Core (Wallet & Ledger)
        self.account = AccountManager(initial_cash=100_000_000) # 100M VND Mock
        self.tracker = OrderTracker()
        
        # Target List
        self.symbols = config.SYMBOLS # Default list from config
        
    async def run(self):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting Scan on {len(self.symbols)} symbols...")
        
        # 0. Sync Wallet (Try Real Data)
        await self.account.sync_from_api()
        
        print(f"[Wallet] Balance: {self.account.get_balance():,.0f} VND | Positions: {self.account.get_positions()}")
        
        # 1. Scan
        results_df = self.scanner.scan_to_df(self.symbols)
        
        if results_df.empty:
            print("No signals found.")
            return
            
        print(f"Found {len(results_df)} signals!")
        print(results_df)
        
        # 2. Execute
        for _, row in results_df.iterrows():
            symbol = row['symbol']
            signal = row['signal'] # BUY or SELL
            price = row['price']
            
            # Simple Position Sizing for Demo
            volume = 100 
            
            # Financial Check
            if signal == 'BUY':
                cost = price * volume
                if not self.account.check_buying_power(cost):
                     print(f"[Skip] Not enough cash to BUY {volume} {symbol} (Cost: {cost:,.0f}).")
                     continue
            elif signal == 'SELL':
                # Check if we have position
                current_qty = self.account.get_positions().get(symbol, 0)
                if current_qty < volume:
                    # Adjust volume or skip?
                    # For now just skip or warn
                    print(f"[Warn] Selling {volume} {symbol} but only have {current_qty}. (Short selling not detecting yet)")
            
            # Place Order
            result = self.order_manager.place_order(
                symbol=symbol,
                side=signal,
                price=price,
                volume=volume
            )
            
            # Post-Trade Logic (Update Wallet & Ledger)
            if result.get('status') == 'success':
                # 1. Log to CSV
                self.tracker.log_order(result, symbol, signal, price, volume)
                
                # 2. Update Mock Wallet
                self.account.update_after_trade(signal, symbol, price, volume)
            
if __name__ == "__main__":
    # Default to Safe Mode
    bot = AutoTrader(safe_mode=True)
    asyncio.run(bot.run())
