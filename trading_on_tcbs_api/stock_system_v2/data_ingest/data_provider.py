
import os
import sys
import time
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from vnstock import Vnstock


from trading_on_tcbs_api.stock_system_v2 import config

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
        self._live_price_cache = {}  # {symbol: {'price': float, 'time': datetime}}

    def clear_realtime_cache(self):
        """Manually flush the realtime price cache to guarantee fresh data on the next fetch."""
        self._live_price_cache.clear()

    def prefetch_realtime_prices(self, symbols: list):
        """Batch fetch realtime prices for multiple symbols to minimize API calls."""
        if not self.auth or not self.auth.token or not symbols:
            return
            
        # TCBS can typically handle up to 50 tickers in one comma-separated string
        chunk_size = 50
        for i in range(0, len(symbols), chunk_size):
            chunk = symbols[i:i+chunk_size]
            url = f"{config.BASE_URL}/tartarus/v1/tickerCommons"
            params = {'tickers': ",".join(chunk)}
            headers = {
                "Authorization": f"Bearer {self.auth.token}",
                "Content-Type": "application/json"
            }
            try:
                import requests
                response = requests.get(url, headers=headers, params=params, timeout=5)
                if response.status_code == 200:
                    data = response.json().get("data", [])
                    now = datetime.now()
                    for item in data:
                        sym = item.get('ticker')
                        price = item.get('matchPrice') or item.get('refPrice')
                        if sym and price:
                            self._live_price_cache[sym] = {'price': price, 'time': now}
            except Exception as e:
                print(f"[Data] Error prefetching realtime prices: {e}")

    def get_realtime_price(self, symbol: str) -> Optional[float]:
        """Fetch real-time price from TCBS (Checks prefetch cache first)."""
        # Check cache (Populated by prefetch_realtime_prices)
        if symbol in self._live_price_cache:
            return self._live_price_cache[symbol]['price']

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
                    
                    if price: # Update cache
                         self._live_price_cache[symbol] = {'price': price, 'time': datetime.now()}
                    return price
                else:
                    print(f"[Data] Realtime response empty: {response.json()}")
            else:
                 print(f"[Data] Realtime fetch error: {response.status_code} - {response.text[:100]}")
        except Exception as e:
            print(f"[Data] Error fetching realtime price: {e}")
        return None

    def _get_holidays(self) -> set:
        """Load holidays from CSV"""
        holidays = set()
        holiday_file = os.path.join(config.BASE_DIR, "config", "holidays_vn.csv")
        if os.path.exists(holiday_file):
            try:
                df_holidays = pd.read_csv(holiday_file)
                if 'date' in df_holidays.columns:
                    holidays = set(pd.to_datetime(df_holidays['date']).dt.date)
            except Exception as e:
                print(f"[Data] Warning: Could not read {holiday_file}: {e}")
        return holidays

    def is_trading_day(self, d: datetime.date) -> bool:
        """Check if date is a valid trading day (Mon-Fri and not holiday)"""
        if d.weekday() >= 5:
            return False
        return d not in self._get_holidays()

    def get_expected_fresh_date(self) -> datetime.date:
        """
        Determines the date we expect the historical data to be updated to.
        Checks config/holidays_vn.csv to safely account for Weekends and Holidays.
        """
        today = datetime.now()
        
        # Cache for 60 minutes
        if hasattr(self, '_expected_date') and hasattr(self, '_expected_date_time'):
            if (today - self._expected_date_time).total_seconds() < 3600:
                return self._expected_date

        # If today is a trading day and market has closed (after 16:00), we expect today's data
        if self.is_trading_day(today.date()) and today.hour >= 16:
            self._expected_date = today.date()
        else:
            # Otherwise, step backwards to find the last completed trading day
            check_date = today.date() - timedelta(days=1)
            while not self.is_trading_day(check_date):
                check_date -= timedelta(days=1)
            self._expected_date = check_date
            
        self._expected_date_time = today
        return self._expected_date

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
                    
                    # 1. Is it fresh? (Compare against expected fresh date from local logic)
                    expected_date = self.get_expected_fresh_date()
                    is_fresh = last_date >= expected_date
                    
                    # 2. Is it deep enough? (Does it cover the start date we need?)
                    # Note: Allow 5 days buffer for holidays/weekends divergence
                    is_ipo_reached = 'is_ipo' in df.columns and df['is_ipo'].any()
                    is_deep_enough = first_date <= (requested_start + timedelta(days=5)) or is_ipo_reached
                    
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
                    
                    # 1b. Mark IPO truncation
                    # If we asked for 365 days of data but the API only returned 50 days, 
                    # it means the stock was recently listed. We mark it so we don't re-fetch endlessly.
                    fetched_first = df['time'].min().date()
                    req_start = datetime.strptime(start_date, "%Y-%m-%d").date()
                    if fetched_first > req_start + timedelta(days=10):
                        df['is_ipo'] = True
                        print(f"[Data] Marked {symbol} as IPO limited (Listed: {fetched_first})")
                    else:
                        df['is_ipo'] = False
                        
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
            elif not self.is_trading_day(today.date()):
                 pass # Skip appending fake live candles on weekends and holidays
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
                     
        # 4. Truncate to requested number of days
        df = df[df['time'] >= start_date].reset_index(drop=True)
        return df

if __name__ == "__main__":
    # Test
    provider = DataProvider()
    df = provider.get_historical_data("HPG", days=30)
    print(df.tail())
