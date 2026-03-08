
import pandas as pd
from typing import List, Dict, Any
from trading_on_tcbs_api.stock_system_v2.data_ingest.data_provider import DataProvider
from trading_on_tcbs_api.stock_system_v2.strategies import SignalStrategy
from trading_on_tcbs_api.stock_system_v2.core.indicator_engine import IndicatorEngine

class MarketScanner:
    """
    Scans a list of stocks using a specific SignalStrategy.
    """
    def __init__(self, strategy: SignalStrategy = None, auth=None, strategies: Dict[str, SignalStrategy] = None):
        self.strategies = strategies or {}
        if strategy:
            self.strategies["Default"] = strategy
            
        self.data_provider = DataProvider(auth=auth)
        self.indicator_engine = IndicatorEngine()

    def scan(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """
        Scan the list of symbols for TODAY's signals.
        """
        results = []
        print(f"[Scanner] Scanning {len(symbols)} symbols with {len(self.strategies)} strategies...")
        
        # 1. Flush any old prices from previous loops
        self.data_provider.clear_realtime_cache()
        # 2. Prefetch a 100% fresh snapshot of all live prices in one API call
        self.data_provider.prefetch_realtime_prices(symbols)
        
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
                    
                # 2. Run All Strategies
                original_cols = set(df.columns)
                for strat_name, strat in self.strategies.items():
                    df_sig = strat.generate_signals(df)
                    added_cols = set(df_sig.columns) - original_cols
                    
                    if df_sig.empty:
                        continue
                        
                    # 3. Check Last Signal (Today)
                    last_row = df_sig.iloc[-1]
                    signal = last_row.get('signal', 0)
                    
                    if signal != 0:
                        # Found a signal!
                        signal_type = "BUY" if signal == 1 else "SELL"
                        
                        # Base result
                        res = {
                            "date": last_row['time'].strftime('%Y-%m-%d') if hasattr(last_row.get('time'), 'strftime') else str(last_row.get('time', '')),
                            "symbol": symbol,
                            "strategy": strat_name,
                            "signal": signal_type,
                            "price": last_row.get('close', 0.0),
                        }
                        
                        # Extract officially required indicators
                        required_cols = strat.get_required_indicators() if hasattr(strat, 'get_required_indicators') else []
                        for col in required_cols:
                            if col in last_row.index:
                                res[col] = last_row[col]
                                
                        # Proactively capture ANY dynamic columns specifically produced by THIS strategy's math
                        # This safely ignores global upstream indicators not explicitly requested
                        for col in added_cols:
                            col_str = str(col)
                            if col_str not in ['signal', 'regime', 'prev_regime'] and not col_str.endswith('_sig') and col_str in last_row.index:
                                if col_str not in res:
                                    res[col_str] = last_row[col_str]

                        results.append(res)
                    # print(f"\n  ! Found {signal_type} for {symbol} at {last_row['close']}")
                    
            except Exception as e:
                print(f"\n  x {symbol}: Error {e}")
                
        print(f"\n[Scanner] Completed. Found {len(results)} signals.")
        return results

    def scan_to_df(self, symbols: List[str]) -> Dict[str, pd.DataFrame]:
        """
        Run scan and return results as a dictionary of Pandas DataFrames grouped by strategy.
        """
        results = self.scan(symbols)
        if not results:
            return {}
        
        df = pd.DataFrame(results)
        
        strategy_dfs = {}
        for strategy_name, group in df.groupby('strategy'):
            # Drop purely NaN columns (they belong to other strategies)
            group_cleaned = group.dropna(axis=1, how='all')
            # Remove the strategy column since it's the dict key
            group_cleaned = group_cleaned.drop(columns=['strategy'])
            
            # Reorder columns for readability
            cols = ['date', 'symbol', 'signal', 'price']
            cols = [c for c in cols if c in group_cleaned.columns] + [c for c in group_cleaned.columns if c not in cols]
            
            strategy_dfs[strategy_name] = group_cleaned[cols].reset_index(drop=True)
            
        return strategy_dfs

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
