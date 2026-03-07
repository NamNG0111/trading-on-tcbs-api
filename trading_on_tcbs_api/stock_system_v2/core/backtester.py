
import pandas as pd
import numpy as np
from datetime import datetime
from typing import List, Dict
from trading_on_tcbs_api.stock_system_v2.data_ingest.data_provider import DataProvider
from trading_on_tcbs_api.stock_system_v2.strategies.strategy import SignalStrategy
from trading_on_tcbs_api.stock_system_v2.auth.auth import StockAuth
from trading_on_tcbs_api.stock_system_v2.core.indicator_engine import IndicatorEngine

class Backtester:
    """
    Engine to backtest a SignalStrategy against historical data.
    """
    
    def __init__(self, initial_capital: float = 100_000_000):
        self.initial_capital = initial_capital
        self.data_provider = DataProvider(auth=None)  # No auth needed for pure history backtest usually
        self.indicator_engine = IndicatorEngine()
        
    def run(self, strategy: SignalStrategy, symbol: str, days: int = 365) -> Dict:
        """
        Run the backtest.
        
        Args:
            strategy (SignalStrategy): The strategy instance
            symbol (str): Stock ticker
            days (int): History duration
            
        Returns:
            Dict: Performance report
        """
        # 1. Fetch Data
        df = self.data_provider.get_historical_data(symbol, days=days, include_live=False)
        if df.empty:
            print(f"[Backtest] No data for {symbol}")
            return {}

        # 1b. Compute centralized indicators
        df = self.indicator_engine.append_indicators(df)

        # 2. Generate Signals (Strategy now reads pre-computed columns)
        df = strategy.generate_signals(df)
        if 'signal' not in df.columns:
            print("[Backtest] Strategy did not return 'signal' column")
            return {}

        # 3. Simulate Trades
        cash = self.initial_capital
        shares = 0
        trades = []
        portfolio_values = []
        
        # We start loop. Note: Strategies usually need some warmup (e.g. MA20 needs 20 days).
        # We assume 'signal' column accounts for this (NaN or 0 at start).
        
        for i, row in df.iterrows():
            price = row['close']
            signal = row['signal']
            date = row['time']
            
            # Record Portfolio Value (Cash + Stock Value)
            pv = cash + (shares * price)
            portfolio_values.append(pv)
            
            # Execute Signal
            if signal == 1: # BUY
                # Simple logic: Buy with 100% allowed cash (minus some buffer/fees?)
                # For basic test: Buy max possible shares
                if cash > price:
                    shares_to_buy = int(cash // price)
                    if shares_to_buy > 0:
                        cost = shares_to_buy * price
                        cash -= cost
                        shares += shares_to_buy
                        trades.append({
                            'date': date,
                            'type': 'BUY',
                            'price': price,
                            'shares': shares_to_buy,
                            'value': cost
                        })
                        # print(f"BUY {shares_to_buy} @ {price} on {date}")
                        
            elif signal == -1: # SELL
                # Simple logic: Sell all
                if shares > 0:
                    revenue = shares * price
                    sold_shares = shares
                    cash += revenue
                    shares = 0
                    trades.append({
                        'date': date,
                        'type': 'SELL',
                        'price': price,
                        'shares': sold_shares, # All sold
                        'value': revenue
                    })
                    # print(f"SELL ALL @ {price} on {date}")

        # Final Settlement
        final_value = cash + (shares * df.iloc[-1]['close'])
        
        # 4. Calculate Metrics
        total_return = (final_value - self.initial_capital) / self.initial_capital
        
        # Win Rate (Simplified: simplistic loop over trades)
        # TODO: Implement proper trade pairing for accurate PnL per trade
        
        report = {
            'symbol': symbol,
            'start_date': df.iloc[0]['time'].strftime('%Y-%m-%d'),
            'end_date': df.iloc[-1]['time'].strftime('%Y-%m-%d'),
            'initial_capital': self.initial_capital,
            'final_value': final_value,
            'total_return_pct': total_return * 100,
            'total_trades': len(trades),
            'history_days': days,
            'trades_log': trades # Return full log
        }
        
        return report

if __name__ == "__main__":
    pass
