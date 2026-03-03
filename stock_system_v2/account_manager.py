
import json
import os
import asyncio
from typing import Dict, Any, Optional
from trading_on_tcbs_api.stock_system_v2.auth import StockAuth
from trading_on_tcbs_api.stock_system_v2.config import TOKEN_FILE, BASE_DIR
from trading_on_tcbs_api.stock_strategy.stock_api_client import StockTradingClient
from trading_on_tcbs_api.utils.config_manager import get_config_manager
from pathlib import Path

class AccountManager:
    """
    Manages the financial state of the trading system:
    - Cash Balance (Real or Mock)
    - Current Positions (Real or Mock)
    - Buying Power Logic
    
    Hybrid Mode:
    - Default: Mock Mode (Simulation)
    - call `sync_from_api()` to override state with Real TCBS Data.
    """
    
    def __init__(self, initial_cash: float = 100_000_000, mock_mode: bool = True):
        # Todo: Persist this to a file (wallet.json) so it survives restarts
        self.cash = initial_cash
        self.positions: Dict[str, int] = {} # Symbol -> Quantity
        self.locked_cash = 0.0 # Cash locked in pending buy orders
        self.buying_power = initial_cash 
        self.mock_mode = mock_mode
        self.last_sync_status = "Mock"
        
        print(f"[Account] Initialized. Mock Mode: {self.mock_mode}")
        if self.mock_mode:
            print(f"[Account] Initial Cash: {self.cash:,.0f} VND")

    async def sync_from_api(self):
        """
        Attempt to fetch Real Assets from TCBS API.
        Updates self.cash, self.positions, self.buying_power.
        """
        print("\n[Account] Syncing with Real API...")
        
        auth = StockAuth()
        if not auth.validate():
            print("[Account] Sync Failed: Auth invalid.")
            return

        try:
            # Init Client
            # Setup Config Manager for absolute path
            cm = get_config_manager()
            cm.config_dir = Path(os.path.join(BASE_DIR, "config"))
            
            client = StockTradingClient(token_file=TOKEN_FILE)
            client.token = auth.token
            
            creds = cm.load_credentials()
            
            # Aggregate Assets
            real_cash = 0.0
            real_positions = {}
            real_power = 0.0
            
            # Define accounts to probe (Normal + Margin)
            accounts_to_probe = []
            if creds.normal_sub_account_id: accounts_to_probe.append(creds.normal_sub_account_id)
            if creds.margin_sub_account_id: accounts_to_probe.append(creds.margin_sub_account_id)
            if not accounts_to_probe and creds.sub_account_id: accounts_to_probe.append(creds.sub_account_id) # Fallback

            data_found = False

            for acc_id in accounts_to_probe:
                client.account_no = acc_id
                
                # Cash
                cash_data = await client.get_cash_balance()
                # Adapting to unknown structure returned by failed checks - assume 'cashBalance' or similar
                # If empty, it adds 0
                c = float(cash_data.get('cashBalance', 0) or cash_data.get('totalCash', 0) or 0)
                real_cash += c
                
                # Positions
                pos_list = await client.get_stock_positions() or []
                for p in pos_list:
                    sym = p.get('symbol')
                    qty = int(p.get('quantity', 0))
                    if sym and qty > 0:
                        real_positions[sym] = real_positions.get(sym, 0) + qty
                
                # Power
                pp_data = await client.get_buying_power()
                pp = float(pp_data.get('buyingPower', 0) or pp_data.get('purchasingPower', 0) or 0)
                # Buying power isn't strictly additive (margin overlaps), but for safe view taking max or sum
                # Taking MAX for conservative estimate of *single account* power, or Sum?
                # Usually Margin account has the relevant power.
                real_power = max(real_power, pp) 
                
                if cash_data or pos_list:
                    data_found = True

            if data_found or real_cash > 0:
                print(f"[Account] Sync Success. Real Cash: {real_cash:,.0f}, Pos: {len(real_positions)}")
                self.cash = real_cash
                self.positions = real_positions
                self.buying_power = real_power
                self.mock_mode = False
                self.last_sync_status = "Real (Synced)"
            else:
                print("[Account] Sync Warning: API returned empty data. Keeping Mock state.")
                self.last_sync_status = "Mock (API Empty)"

        except Exception as e:
            print(f"[Account] Sync Error: {e}")
            self.last_sync_status = f"Mock (Error: {e})"

    def get_balance(self) -> float:
        """Return available cash."""
        return self.cash - self.locked_cash
    
    def get_buying_power_amount(self) -> float:
        """Return actual buying power (Real or Mock)"""
        if self.mock_mode:
             return self.get_balance()
        return self.buying_power

    def get_positions(self) -> Dict[str, int]:
        """Return current holdings."""
        return self.positions
    
    def check_buying_power(self, cost: float) -> bool:
        """Can we afford this trade?"""
        if self.mock_mode:
            return self.get_balance() >= cost
        else:
            return self.buying_power >= cost
    
    def lock_cash(self, amount: float):
        """Lock cash for a pending buy order"""
        if self.check_buying_power(amount):
            self.locked_cash += amount
            # If real mode, we don't strictly decrease 'buying_power' locally 
            # because the API will update it on next sync. 
            # But for safety in tight loops:
            if not self.mock_mode:
                 self.buying_power -= amount
            return True
        return False
        
    def release_cash(self, amount: float):
        """Release locked cash (e.g. order cancelled)"""
        self.locked_cash = max(0.0, self.locked_cash - amount)
        if not self.mock_mode:
             self.buying_power += amount # Restore hint

    def update_after_trade(self, side: str, symbol: str, price: float, volume: int):
        """
        Update the wallet after a successful trade execution.
        """
        total_cost = price * volume
        
        if side in ['NB', 'BUY']:
            if self.locked_cash >= total_cost:
                self.locked_cash -= total_cost
                self.cash -= total_cost
            else:
                self.cash -= total_cost 
                
            current_qty = self.positions.get(symbol, 0)
            self.positions[symbol] = current_qty + volume
            
            # Update Mock Power
            if self.mock_mode:
                 pass # managed by get_balance()
            
            print(f"[Account] Bought {volume} {symbol}. Cash: {self.cash:,.0f}, Pos: {self.positions[symbol]}")
            
        elif side in ['NS', 'SELL']:
            self.cash += total_cost
            self.buying_power += total_cost
            
            current_qty = self.positions.get(symbol, 0)
            new_qty = max(0, current_qty - volume)
            if new_qty == 0:
                if symbol in self.positions:
                    del self.positions[symbol]
            else:
                self.positions[symbol] = new_qty
            
            print(f"[Account] Sold {volume} {symbol}. Cash: {self.cash:,.0f}, Pos: {new_qty}")

