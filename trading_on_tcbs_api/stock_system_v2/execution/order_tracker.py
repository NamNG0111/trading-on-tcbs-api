
import os
import pandas as pd
from datetime import datetime
from typing import Dict, Any
from trading_on_tcbs_api.stock_system_v2 import config

class OrderTracker:
    """
    Logs every order to a CSV file to maintain a permanent ledger of activity.
    """
    
    def __init__(self):
        # Save to trading_on_tcbs_api/data/orders.csv
        # Using the unified DATA_DIR from config which points to /data/stocks
        # We might want a separate folder or just putting it in data/ is fine.
        # Let's put it in data/ (parent of stocks) or just next to stocks.
        
        # Let's default to a dedicated ledger file
        # BASE_DIR/data/ledger.csv
        data_root = os.path.dirname(config.DATA_DIR) # Go up from data/stocks to data/
        self.ledger_file = os.path.join(data_root, "ledger.csv")
        
        if not os.path.exists(self.ledger_file):
            self._create_ledger()
            
    def _create_ledger(self):
        df = pd.DataFrame(columns=['time', 'order_id', 'symbol', 'side', 'price', 'volume', 'status', 'note'])
        df.to_csv(self.ledger_file, index=False)
        print(f"[Tracker] Created new ledger at {self.ledger_file}")
        
    def log_order(self, order_result: Dict[str, Any], symbol: str, side: str, price: float, volume: int):
        """Append a new order to the ledger."""
        
        entry = {
            'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'order_id': order_result.get('order_id', 'unknown'),
            'symbol': symbol,
            'side': side,
            'price': price,
            'volume': volume,
            'status': order_result.get('status', 'pending'),
            'note': order_result.get('note', '')
        }
        
        try:
            df = pd.DataFrame([entry])
            df.to_csv(self.ledger_file, mode='a', header=False, index=False)
            # print(f"[Tracker] Logged order {entry['order_id']}")
        except Exception as e:
            print(f"[Tracker] Error logging order: {e}")
            
    def get_history(self) -> pd.DataFrame:
        if os.path.exists(self.ledger_file):
            return pd.read_csv(self.ledger_file)
        return pd.DataFrame()
