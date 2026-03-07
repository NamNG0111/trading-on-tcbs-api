
import time
import uuid
import requests
from typing import Dict, Any, Optional
from trading_on_tcbs_api.stock_system_v2 import config

class OrderManager:
    """
    Handles order placement and management on TCBS.
    Includes a SAFE MODE to prevent real trading during development.
    """
    
    def __init__(self, auth, safe_mode: bool = True):
        self.auth = auth
        self.safe_mode = safe_mode
        self.base_url = config.BASE_URL
        if self.safe_mode:
            print("[OrderManager] In SAFE MODE (Dry Run). No real orders will be placed.")
            
    def place_order(self, 
                   symbol: str, 
                   side: str, 
                   price: float, 
                   volume: int, 
                   order_type: str = "LO") -> Dict[str, Any]:
        """
        Place an order (Buy/Sell).
        
        Args:
            symbol (str): Ticker (e.g., HPG).
            side (str): 'NB' (Buy) or 'NS' (Sell).
            price (float): Price in VND.
            volume (int): Number of shares.
            order_type (str): 'LO', 'ATO', 'ATC', etc.
            
        Returns:
            Dict: Order execution result (mock or real).
        """
        # Validate Side
        if side not in ['NB', 'NS']: # NB: Buy, NS: Sell (TCBS Convention)
            if side.upper() == 'BUY': side = 'NB'
            elif side.upper() == 'SELL': side = 'NS'
            else:
                return {"status": "error", "message": f"Invalid side: {side}"}
                
        print(f"\n[OrderManager] Preparing to {side} {volume} {symbol} @ {price:,.0f} ({order_type})...")
        
        # --- SAFE MODE ---
        if self.safe_mode:
            mock_id = f"mock_{uuid.uuid4().hex[:8]}"
            print(f"[SAFE MODE] Order SIMULATED. ID: {mock_id}")
            return {
                "status": "success",
                "order_id": mock_id,
                "note": "This was a dry run."
            }
            
        # --- REAL MODE (Future Implementation) ---
        # TODO: Implement TCBS API call 
        # Endpoint: /equity/order (POST)
        # Needs detailed payload: account data, OTP (if high value), etc.
        
        print("[OrderManager] Real trading not yet fully connected explicitly. (Protection)")
        return {"status": "error", "message": "Real trading implementation pending safe-guard checks."}

    def cancel_order(self, order_id: str):
        if self.safe_mode:
            print(f"[SAFE MODE] Cancelled mock order {order_id}")
            return True
        return False
