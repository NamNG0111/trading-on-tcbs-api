
import os
import sys
import time
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from vnstock import Vnstock

# Shim to allow running this file directly
if __name__ == "__main__" and (__package__ is None or __package__ == ""):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    sys.path.insert(0, parent_dir)
    __package__ = "stock_system_v2"

from . import config

class DataProvider:
    """
    Provides market data (Historical and Real-time) for the stock system.
    Uses 'vnstock' library (Source: VCI) for historical data as TCBS API 
    does not support history via Open API.
    """
    
    def __init__(self, auth=None):
        self.data_dir = config.DATA_DIR
        self.auth = auth  # Optional auth for real-time data
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)

    def get_realtime_price(self, symbol: str) -> Optional[float]:
        """Fetch real-time price from TCBS."""
        if not self.auth or not self.auth.token:
            return None
            
        url = f"{config.BASE_URL}/tartarus/v1/tickerCommons"
        params = {'tickers': symbol}
        headers = {
            "Authorization": f"Bearer {self.auth.token}",
            "Content-Type": "application/json"
        }
        
        try:
            import requests
            response = requests.get(url, headers=headers, params=params, timeout=5)
            if response.status_code == 200:
                data = response.json().get("data", [])
                if data:
                    # API returns 'matchPrice' for current price
                    price = data[0].get('matchPrice')
                    # Fallback to refPrice if no match (e.g. pre-market)
                    if not price:
                        price = data[0].get('refPrice')
                    return price
                else:
                    print(f"[Data] Realtime response empty: {response.json()}")
            else:
                 print(f"[Data] Realtime fetch error: {response.status_code} - {response.text[:100]}")
        except Exception as e:
            print(f"[Data] Error fetching realtime price: {e}")
        return None

    def get_historical_data(self, symbol: str, days: int = 365, resolution: str = '1D', force_update: bool = False, include_live: bool = True) -> pd.DataFrame:
        """
        Fetch historical data and optionally append latest live price.
        
        Args:
            include_live (bool): If True, appends current real-time price as the latest 'Close'
        """
        # Cache file path
        cache_file = os.path.join(self.data_dir, f"{symbol}_{resolution}.csv")
        
        today = datetime.now()
        start_date = (today - timedelta(days=days)).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")
        
        df = pd.DataFrame()
        
        # 1. Try Load Cache
        if not force_update and os.path.exists(cache_file):
            try:
                df = pd.read_csv(cache_file)
                df['time'] = pd.to_datetime(df['time'])
                
                # Check staleness AND depth
                if not df.empty:
                    last_date = df['time'].max().date()
                    first_date = df['time'].min().date()
                    requested_start = datetime.strptime(start_date, "%Y-%m-%d").date()
                    
                    # 1. Is it fresh? (Today or Yesterday)
                    is_fresh = last_date >= (today - timedelta(days=1)).date()
                    
                    # 2. Is it deep enough? (Does it cover the start date we need?)
                    # Note: Allow 5 days buffer for holidays/weekends divergence
                    is_deep_enough = first_date <= (requested_start + timedelta(days=5))
                    
                    if is_fresh and is_deep_enough:
                        # Cache is good
                        pass
                    else:
                        print(f"[Data] Cache invalid (Fresh: {is_fresh}, Deep: {is_deep_enough}). Fetching update...")
                        df = pd.DataFrame() # Force re-fetch
            except Exception:
                df = pd.DataFrame()
        
        # 2. Fetch from Source if needed
        if df.empty:
            print(f"[Data] Fetching {symbol} from {start_date} to {end_date} (Source: VCI)...")
            try:
                # Rate Limit: 20 req/min => 1 req every 3s.
                # We sleep to be safe.
                time.sleep(3.1) 
                
                stock = Vnstock().stock(symbol=symbol, source='VCI')
                # Note: vnstock history end_date is inclusive
                df = stock.quote.history(start=start_date, end=end_date, interval=resolution)
                if df is not None and not df.empty:
                    # Normalize prices to VND (if < 1000, assume it's in thousands)
                    # HPG shouldn't be 20 VND.
                    cols_to_fix = ['open', 'high', 'low', 'close']
                    if df['close'].mean() < 500: # Heuristic
                        for col in cols_to_fix:
                             if col in df.columns:
                                 df[col] = df[col] * 1000
                    
                    df['time'] = pd.to_datetime(df['time'])
                    df.to_csv(cache_file, index=False)
            except Exception as e:
                print(f"[Data] Error fetching data: {e}")
        
        if df.empty:
            return df
            
        # 3. Merge Real-time Price (The User Requirement)
        # Debug: Print what we have so far
        last_time = df.iloc[-1]['time']
        # print(f"[Data] History loaded. Last Date: {last_time.date()}")
        
        if include_live:
            if not self.auth:
                 print(f"[Data] Auth missing. Skipping live price.")
            else:
                 current_price = self.get_realtime_price(symbol)
                 if current_price and current_price > 0:
                     # print(f"[Data] Live Price for {symbol}: {current_price}")
                     
                     # Check dates
                     if today.date() > last_time.date():
                         # Append new row
                         print(f"[Data] Appending NEW LIVE CANDLE for {symbol}: {today.date()} @ {current_price}")
                         new_row = {
                             'time': today, 
                             'open': current_price,
                             'high': current_price,
                             'low': current_price,
                             'close': current_price,
                             'volume': 0
                         }
                         df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                     
                     elif today.date() == last_time.date():
                         # Update existing
                         print(f"[Data] Updating TODAY'S CANDLE for {symbol}: {today.date()} @ {current_price}")
                         df.at[df.index[-1], 'close'] = current_price
                 else:
                     print(f"[Data] Failed to fetch live price for {symbol} (Returned: {current_price})")
                     
        return df

    def get_latest_price(self, symbol: str) -> Optional[float]:
        """
        Get the absolute latest price (snapshot). 
        For now using last close of history, or could rely on market_scanner.
        """
        # TODO: Integrate with MarketScanner for real-time
        return 0.0

if __name__ == "__main__":
    # Test
    provider = DataProvider()
    df = provider.get_historical_data("HPG", days=30)
    print(df.tail())
