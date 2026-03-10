
import pandas as pd
import numpy as np
from datetime import datetime
from typing import List, Dict
from trading_on_tcbs_api.stock_system_v2.data_ingest.data_provider import DataProvider
from trading_on_tcbs_api.stock_system_v2.strategies import SignalStrategy
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
        
    def run(self, strategy: SignalStrategy, symbol: str, days: int = 365, forward_returns_days: List[int] = None, allow_multiple_buys: bool = False) -> Dict:
        """
        Run the backtest.
        
        Args:
            strategy (SignalStrategy): The strategy instance
            symbol (str): Stock ticker
            days (int): History duration
            forward_returns_days (List[int]): Days to statically hold after BUY
            allow_multiple_buys (bool): Plot subsequent BUY signals even if holding shares (visualizer only)
        
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

        if forward_returns_days is None:
            forward_returns_days = [3, 5, 10, 20]
            
        forward_returns = {d: [] for d in forward_returns_days}
        df_len = len(df)
        prices = df['close'].values
        signals = df['signal'].values
        
        # Fast compute forward returns for ALL generated BUY signals
        for idx in range(df_len):
            if signals[idx] == 1:
                entry_price = prices[idx]
                for d in forward_returns_days:
                    if idx + d < df_len:
                        exit_price = prices[idx + d]
                        forward_returns[d].append((exit_price - entry_price) / entry_price)

        # 3. Simulate Trades
        cash = self.initial_capital
        shares = 0
        trades = []
        portfolio_values = []
        
        peak_value = self.initial_capital
        max_drawdown = 0.0
        
        current_position = None
        closed_trades = []
        
        # We start loop. Note: Strategies usually need some warmup (e.g. MA20 needs 20 days).
        # We assume 'signal' column accounts for this (NaN or 0 at start).
        
        for i, row in df.iterrows():
            price = row['close']
            signal = row['signal']
            date = row['time']
            
            # Record Portfolio Value (Cash + Stock Value)
            pv = cash + (shares * price)
            portfolio_values.append(pv)
            
            # Update Max Drawdown
            if pv > peak_value:
                peak_value = pv
            drawdown = (pv - peak_value) / peak_value if peak_value > 0 else 0
            if drawdown < max_drawdown:
                max_drawdown = drawdown
            
            # Execute Signal
            if signal == 1: # BUY Triggered
                if shares == 0:
                    # Actually execute portfolio allocation
                    if cash > price:
                        shares_to_buy = int(cash // price)
                        if shares_to_buy > 0:
                            cost = shares_to_buy * price
                            cash -= cost
                            shares += shares_to_buy
                            
                            current_position = {
                                'entry_price': price,
                                'entry_date': date,
                                'shares': shares_to_buy,
                                'cost': cost
                            }
                            
                            trades.append({
                                'date': date,
                                'type': 'BUY',
                                'price': price,
                                'shares': shares_to_buy,
                                'value': cost
                            })
                elif allow_multiple_buys:
                    # Visualizer mode: We are already holding max shares, but we want 
                    # to plot this exact subsequent trigger on the chart anyway.
                    # We 'phantom log' it without changing cash.
                    trades.append({
                        'date': date,
                        'type': 'BUY',
                        'price': price,
                        'shares': 0, # Phantom trade
                        'value': 0
                    })
                        
            elif signal == -1 and shares > 0: # SELL
                # Simple logic: Sell all
                revenue = shares * price
                sold_shares = shares
                cash += revenue
                shares = 0
                
                if current_position:
                    pnl = revenue - current_position['cost']
                    # Calculate holding period
                    entry_d = pd.to_datetime(current_position['entry_date'])
                    exit_d = pd.to_datetime(date)
                    hold_days = (exit_d - entry_d).days
                    
                    closed_trades.append({
                        'pnl': pnl,
                        'hold_days': hold_days
                    })
                    current_position = None
                
                trades.append({
                    'date': date,
                    'type': 'SELL',
                    'price': price,
                    'shares': sold_shares, # All sold
                    'value': revenue
                })

        # Final Settlement
        final_value = cash + (shares * df.iloc[-1]['close'])
        
        # 4. Calculate Metrics
        total_return = (final_value - self.initial_capital) / self.initial_capital
        
        # Advanced Metrics
        gross_profit = sum(t['pnl'] for t in closed_trades if t['pnl'] > 0)
        gross_loss = abs(sum(t['pnl'] for t in closed_trades if t['pnl'] < 0))
        profit_factor = (gross_profit / gross_loss) if gross_loss != 0 else (float('inf') if gross_profit > 0 else 0)
        avg_hold_days = sum(t['hold_days'] for t in closed_trades) / len(closed_trades) if closed_trades else 0
        
        winning_trades = sum(1 for t in closed_trades if t['pnl'] > 0)
        win_rate = (winning_trades / len(closed_trades)) * 100 if closed_trades else 0
        
        # ------------------------------------------------------------------
        # NEW: Fixed Holding Time Portfolio Simulation
        # Simulate an actual chronological portfolio that BUYS and holds for exactly N days.
        # Ignores native strategy SELL signals.
        # ------------------------------------------------------------------
        fixed_hold_results = {}
        for d in forward_returns_days:
            sim_cash = self.initial_capital
            sim_shares = 0
            sim_entry_cost = 0
            sim_entry_idx = -1
            sim_pnl_list = []
            
            for idx in range(df_len):
                price = prices[idx]
                
                # Check for forced exit first
                if sim_shares > 0 and (idx - sim_entry_idx == d or idx == df_len - 1):
                    # Sell
                    revenue = sim_shares * price
                    pnl_pct = (revenue - sim_entry_cost) / sim_entry_cost
                    sim_pnl_list.append(pnl_pct)
                    sim_cash += revenue
                    sim_shares = 0
                    sim_entry_idx = -1
                
                # Check for new entry if we have cash and a BUY signal
                if sim_shares == 0 and signals[idx] == 1:
                    if sim_cash > price:
                        shares_to_buy = int(sim_cash // price)
                        if shares_to_buy > 0:
                            sim_entry_cost = shares_to_buy * price
                            sim_cash -= sim_entry_cost
                            sim_shares = shares_to_buy
                            sim_entry_idx = idx
            
            # Record fixed-hold metrics for this N-day period
            sim_final_value = sim_cash + (sim_shares * prices[-1]) # Safe catch
            sim_total_ret = (sim_final_value - self.initial_capital) / self.initial_capital
            
            win_r = (sum(1 for x in sim_pnl_list if x > 0) / len(sim_pnl_list) * 100) if sim_pnl_list else 0
            avg_r = (sum(sim_pnl_list) / len(sim_pnl_list) * 100) if sim_pnl_list else 0
            max_r = (max(sim_pnl_list) * 100) if sim_pnl_list else 0
            min_r = (min(sim_pnl_list) * 100) if sim_pnl_list else 0
            
            fixed_hold_results[d] = {
                'total_return_pct': sim_total_ret * 100,
                'win_rate_pct': win_r,
                'avg_trade_pct': avg_r,
                'best_trade_pct': max_r,
                'worst_trade_pct': min_r,
                'total_trades': len(sim_pnl_list)
            }
        
        report = {
            'symbol': symbol,
            'start_date': df.iloc[0]['time'].strftime('%Y-%m-%d'),
            'end_date': df.iloc[-1]['time'].strftime('%Y-%m-%d'),
            'initial_capital': self.initial_capital,
            'final_value': final_value,
            'total_return_pct': total_return * 100,
            'total_trades': len(trades),
            'win_rate_pct': win_rate,
            'max_drawdown_pct': max_drawdown * 100,
            'profit_factor': profit_factor,
            'avg_hold_days': avg_hold_days,
            'history_days': days,
            'forward_returns': forward_returns,
            'fixed_hold_results': fixed_hold_results,
            'trades_log': trades # Return full log
        }
        
        return report

if __name__ == "__main__":
    pass
