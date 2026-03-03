
import pandas as pd
import os
from collections import deque
from typing import Dict, List, Any

class PerformanceAnalyzer:
    """
    Analyzes trade history (ledger) to calculate performance metrics:
    - Realized P&L (FIFO method)
    - Win Rate
    - Total Trades
    - Profit Factor
    """
    
    def __init__(self, ledger_file: str):
        self.ledger_file = ledger_file
        self.trades_history = []  # List of closed trades
        self.open_positions = {}  # Symbol -> deque of (price, volume, date)
        
    def load_data(self) -> pd.DataFrame:
        if not os.path.exists(self.ledger_file):
            print(f"Ledger file not found: {self.ledger_file}")
            return pd.DataFrame()
            
        df = pd.read_csv(self.ledger_file)
        # Filter only successful trades
        df = df[df['status'] == 'success'].copy()
        df['time'] = pd.to_datetime(df['time'])
        df = df.sort_values('time')
        return df
    
    def calculate_performance(self):
        df = self.load_data()
        if df.empty:
            return {}
            
        self.trades_history = []
        self.open_positions = {} # Reset
        
        # FIFO Matching
        for _, row in df.iterrows():
            symbol = row['symbol']
            side = row['side'].upper()
            price = float(row['price'])
            volume = int(row['volume'])
            date = row['time']
            
            if side in ['NB', 'BUY']:
                # Add to inventory
                if symbol not in self.open_positions:
                    self.open_positions[symbol] = deque()
                self.open_positions[symbol].append({'price': price, 'vol': volume, 'date': date})
                
            elif side in ['NS', 'SELL']:
                remaining_sell_vol = volume
                
                if symbol not in self.open_positions or not self.open_positions[symbol]:
                    print(f"Warning: Sell {symbol} without position (Short Selling or Data Missing)")
                    # Treat as pure gain or ignore? For now, ignore short side P&L tracking complexity
                    continue
                    
                # Match against Buy queue
                while remaining_sell_vol > 0 and self.open_positions[symbol]:
                    buy_batch = self.open_positions[symbol][0] # Peek oldest
                    
                    matched_vol = min(remaining_sell_vol, buy_batch['vol'])
                    
                    # Calculate P&L for this chunk
                    pnl = (price - buy_batch['price']) * matched_vol
                    cost = buy_batch['price'] * matched_vol
                    revenue = price * matched_vol
                    
                    # Log Closed Trade
                    self.trades_history.append({
                        'symbol': symbol,
                        'close_date': date,
                        'open_date': buy_batch['date'],
                        'volume': matched_vol,
                        'buy_price': buy_batch['price'],
                        'sell_price': price,
                        'pnl': pnl,
                        'return_pct': (pnl / cost) * 100 if cost > 0 else 0
                    })
                    
                    # Update Queues
                    remaining_sell_vol -= matched_vol
                    buy_batch['vol'] -= matched_vol
                    
                    if buy_batch['vol'] == 0:
                        self.open_positions[symbol].popleft() # Remove empty batch
                        
        return self._compute_metrics()
        
    def _compute_metrics(self) -> Dict[str, Any]:
        if not self.trades_history:
            return {'total_trades': 0, 'total_pnl': 0, 'win_rate': 0}
            
        trades_df = pd.DataFrame(self.trades_history)
        
        total_pnl = trades_df['pnl'].sum()
        total_trades = len(trades_df)
        winning_trades = trades_df[trades_df['pnl'] > 0]
        losing_trades = trades_df[trades_df['pnl'] <= 0]
        
        win_rate = (len(winning_trades) / total_trades) * 100
        
        gross_profit = winning_trades['pnl'].sum()
        gross_loss = abs(losing_trades['pnl'].sum())
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        avg_return = trades_df['return_pct'].mean()
        
        return {
            'total_trades': total_trades,
            'total_pnl': total_pnl,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'avg_return_pct': avg_return,
            'best_trade': trades_df['pnl'].max(),
            'worst_trade': trades_df['pnl'].min()
        }
        
    def generate_report(self):
        metrics = self.calculate_performance()
        if not metrics or metrics['total_trades'] == 0:
            return "No closed trades to analyze."
            
        report = (
            "=== PERFORMANCE REPORT ===\n"
            f"Total Closed Trades: {metrics['total_trades']}\n"
            f"Total P&L:           {metrics['total_pnl']:,.0f} VND\n"
            f"Win Rate:            {metrics['win_rate']:.2f}%\n"
            f"Profit Factor:       {metrics['profit_factor']:.2f}\n"
            f"Avg Return:          {metrics['avg_return_pct']:.2f}%\n"
            "--------------------------\n"
            f"Best Trade:          {metrics['best_trade']:,.0f} VND\n"
            f"Worst Trade:         {metrics['worst_trade']:,.0f} VND\n"
        )
        return report

