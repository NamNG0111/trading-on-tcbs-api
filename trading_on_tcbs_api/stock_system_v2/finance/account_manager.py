
import asyncio
import json
import os
from pathlib import Path
from typing import Dict

from trading_on_tcbs_api.stock_system_v2.auth.auth import StockAuth
from trading_on_tcbs_api.stock_system_v2.config import BASE_DIR, TOKEN_FILE
from trading_on_tcbs_api.stock_system_v2.core.stock_api_client import StockTradingClient
from trading_on_tcbs_api.stock_system_v2.obs import get_logger, log_event
from trading_on_tcbs_api.utils.config_manager import get_config_manager

_logger = get_logger("account")


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
        
        log_event(
            _logger, "account.init",
            mock_mode=self.mock_mode, initial_cash=self.cash,
        )

    async def sync_from_api(self, target_account: str = None):
        """
        Attempt to fetch Real Assets from TCBS API.
        Updates self.cash, self.positions, self.buying_power.
        """
        log_event(_logger, "account.sync.start", target_account=target_account)

        auth = StockAuth()
        if not auth.validate():
            log_event(_logger, "account.sync.auth_invalid", level=40)
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
            # Attempt to discover active sub-accounts from Customer API
            if not accounts_to_probe:
                custody_id = creds.account_id
                try:
                    import base64
                    parts = auth.token.split(".")
                    if len(parts) > 1:
                        padding = '=' * (4 - len(parts[1]) % 4)
                        payload = json.loads(base64.b64decode(parts[1] + padding).decode('utf-8'))
                        custody_id = payload.get('custodyID') or custody_id
                except (ValueError, KeyError, AttributeError, TypeError):
                    # JWT parse failure — fall back to credentials.account_id.
                    pass
                
                if custody_id:
                    import requests
                    url = f"{client.base_url}/aion/v1/customers/{custody_id}/accounts"
                    try:
                        resp = await asyncio.to_thread(requests.get, url, headers=client.headers, timeout=5)
                        if resp.status_code == 200:
                            for acc in resp.json():
                                if acc.get('accountStatus') == 'A' and acc.get('accountNo'):
                                    accounts_to_probe.append(acc.get('accountNo'))
                    except (OSError, ValueError, KeyError, RuntimeError) as e:
                        log_event(_logger, "account.sync.subaccount_lookup_failed",
                                  level=30, cause=str(e))
            
            # Absolute fallback
            if not accounts_to_probe and creds.sub_account_id:
                accounts_to_probe.append(creds.sub_account_id)

            data_found = False

            for acc_id in accounts_to_probe:
                if target_account and acc_id != target_account:
                    continue
                    
                client.account_no = acc_id
                
                # Cash
                cash_data = await client.get_cash_balance()
                cash_dict = cash_data[0] if isinstance(cash_data, list) and len(cash_data) > 0 else cash_data
                if isinstance(cash_dict, dict):
                    c = float(cash_dict.get('totalCashBalance', 0) or cash_dict.get('cashBalance', 0) or 0)
                    real_cash += c
                
                # Positions
                pos_data = await client.get_stock_positions() or {}
                pos_list = pos_data.get('stock', []) if isinstance(pos_data, dict) else pos_data
                for p in pos_list:
                    if isinstance(p, dict):
                        sym = p.get('symbol')
                        qty = int(p.get('totalQtty', 0) or p.get('quantity', 0) or 0)
                        if sym and qty >= 0:
                            real_positions[sym] = real_positions.get(sym, 0) + qty
                
                # Power
                pp_data = await client.get_buying_power()
                pp_dict = pp_data[0] if isinstance(pp_data, list) and len(pp_data) > 0 else pp_data
                if isinstance(pp_dict, dict):
                    pp = float(pp_dict.get('ppse', 0) or pp_dict.get('buyingPower', 0) or 0)
                    real_power = max(real_power, pp) 
                
                if cash_data or pos_list:
                    data_found = True

            if data_found or real_cash > 0:
                # Phase-5 reconciliation: never silently overwrite. If
                # the local book has any non-zero positions and the
                # broker book disagrees, raise `PositionDriftError`.
                # The legacy first-time-sync (empty local book) is
                # always allowed.
                from trading_on_tcbs_api.stock_system_v2.finance.reconciler import (
                    assert_no_drift,
                )
                if any(qty > 0 for qty in self.positions.values()):
                    threshold = getattr(self, "drift_threshold_shares", 0)
                    assert_no_drift(
                        self.positions,
                        real_positions,
                        threshold_shares=threshold,
                    )
                log_event(
                    _logger, "account.sync.success",
                    real_cash=real_cash, n_positions=len(real_positions),
                )
                self.cash = real_cash
                self.positions = real_positions
                self.buying_power = real_power
                self.mock_mode = False
                self.last_sync_status = "Real (Synced)"
            else:
                log_event(_logger, "account.sync.empty", level=30)
                self.last_sync_status = "Mock (API Empty)"

        except (OSError, ValueError, KeyError, RuntimeError, AttributeError) as e:
            # Network / parse failures during sync. We keep the last
            # known mock state — silently overwriting positions on a
            # half-failed sync is the exact bug Phase 5 closes out.
            log_event(_logger, "account.sync.error", level=40, cause=str(e))
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
            
            log_event(
                _logger, "account.trade.bought",
                symbol=symbol, volume=volume, cash=self.cash,
                holdings=self.positions[symbol],
            )
            
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
            
            log_event(
                _logger, "account.trade.sold",
                symbol=symbol, volume=volume, cash=self.cash, holdings=new_qty,
            )

