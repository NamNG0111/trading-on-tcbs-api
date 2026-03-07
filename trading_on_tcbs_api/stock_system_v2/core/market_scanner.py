
import pandas as pd
from typing import List, Dict, Any
from trading_on_tcbs_api.stock_system_v2.data_ingest.data_provider import DataProvider
from trading_on_tcbs_api.stock_system_v2.strategies import SignalStrategy
from trading_on_tcbs_api.stock_system_v2.core.indicator_engine import IndicatorEngine

class MarketScanner:
    """
    Scans a list of stocks using a specific SignalStrategy.
    """
    def __init__(self, strategy: SignalStrategy, auth=None):
        self.strategy = strategy
        self.data_provider = DataProvider(auth=auth)
        self.indicator_engine = IndicatorEngine()

    def scan(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """
        Scan the list of symbols for TODAY's signals.
        """
        results = []
        print(f"[Scanner] Scanning {len(symbols)} symbols with {type(self.strategy).__name__}...")
        
        for i, symbol in enumerate(symbols):
            try:
                # Progress indicator
                # Progress indicator (Verbose)
                # print(f"[{i+1}/{len(symbols)}] Checking {symbol}...", end='\r', flush=True)
                
                # 1. Get Data (History + Live)
                # We need enough history for indicators (e.g. 200 days)
                df = self.data_provider.get_historical_data(symbol, days=365, include_live=True)
                
                if df.empty:
                    continue
                    
                # 1b. Compute centralized indicators via pandas-ta
                df = self.indicator_engine.append_indicators(df)
                    
                # 2. Run Strategy (now reading pre-computed columns)
                df_sig = self.strategy.generate_signals(df)
                
                if df_sig.empty:
                    continue
                    
                # 3. Check Last Signal (Today)
                last_row = df_sig.iloc[-1]
                signal = last_row.get('signal', 0)
                
                if signal != 0:
                    # Found a signal!
                    signal_type = "BUY" if signal == 1 else "SELL"
                    results.append({
                        "symbol": symbol,
                        "signal": signal_type,
                        "price": last_row['close'],
                        "date": last_row['time'].strftime('%Y-%m-%d')
                    })
                    # print(f"\n  ! Found {signal_type} for {symbol} at {last_row['close']}")
                    
            except Exception as e:
                print(f"\n  x {symbol}: Error {e}")
                
        print(f"\n[Scanner] Completed. Found {len(results)} signals.")
        return results

    def scan_to_df(self, symbols: List[str]) -> pd.DataFrame:
        """
        Run scan and return results as a Pandas DataFrame.
        """
        results = self.scan(symbols)
        if not results:
            return pd.DataFrame()
        
        df = pd.DataFrame(results)
        # Reorder columns for readability if possible
        cols = ['date', 'symbol', 'signal', 'price']
        # Only keep columns that exist in df (in case of empty or different keys)
        cols = [c for c in cols if c in df.columns] + [c for c in df.columns if c not in cols]
        df = df[cols]
        return df

    def print_results(self, results: List[Dict[str, Any]]):
        """
        Pretty print the results.
        """
        if not results:
            print("\nNo signals found for today.")
            return
            
        print("\n" + "="*40)
        print(f"MARKET SCAN RESULTS ({len(results)} FOUND)")
        print("="*40)
        print(f"{'SYMBOL':<10} {'SIGNAL':<10} {'PRICE':<12} {'DATE':<12}")
        print("-" * 40)
        
        for res in results:
            # Color coding (ANSI)
            GREEN = '\033[92m'
            RED = '\033[91m'
            RESET = '\033[0m'
            
            color = GREEN if res['signal'] == 'BUY' else RED
            print(f"{color}{res['symbol']:<10} {res['signal']:<10} {res['price']:<12,.0f} {res['date']:<12}{RESET}")
        print("="*40)
