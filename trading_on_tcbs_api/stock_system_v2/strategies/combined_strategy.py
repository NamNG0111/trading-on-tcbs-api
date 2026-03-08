
import pandas as pd
from typing import List, Optional
from .strategy import SignalStrategy

class CombinedStrategy(SignalStrategy):
    """
    Generic Combined Strategy with separate logic for Entry (Buy) and Exit (Sell).
    Supports using different strategies for Buy vs Sell.
    """
    
    def __init__(self, 
                 strategies: Optional[List[SignalStrategy]] = None, 
                 buy_strategies: Optional[List[SignalStrategy]] = None,
                 sell_strategies: Optional[List[SignalStrategy]] = None,
                 buy_mode: str = "AND", 
                 sell_mode: str = "OR"):
        """
        Args:
            strategies (List): Strategies used for BOTH Buy and Sell decisions.
            buy_strategies (List): Strategies used ONLY for Buy decisions.
            sell_strategies (List): Strategies used ONLY for Sell decisions.
            buy_mode (str): "AND" or "OR" for Buy signal aggregation.
            sell_mode (str): "AND" or "OR" for Sell signal aggregation.
        """
        self.common_strategies = strategies or []
        self.buy_only_strategies = buy_strategies or []
        self.sell_only_strategies = sell_strategies or []
        
        self.buy_mode = buy_mode.upper()
        self.sell_mode = sell_mode.upper()
        self.name = "Combined Strategy"
        self.description = "Aggregates underlying strategies."
        
    def get_brief(self) -> str:
        briefs = []
        for s in self.common_strategies + self.buy_only_strategies:
            if hasattr(s, 'get_brief'):
                briefs.append(s.get_brief())
        if not briefs:
            return super().get_brief()
        return " AND ".join(briefs) if self.buy_mode == "AND" else " OR ".join(briefs)
        
    def get_required_indicators(self) -> list:
        reqs = []
        for s in self.common_strategies + self.buy_only_strategies + self.sell_only_strategies:
            if hasattr(s, 'get_required_indicators'):
                for req in s.get_required_indicators():
                    if req not in reqs:
                        reqs.append(req)
        return reqs
        
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        
        # Helper to run specific list of strategies
        def get_sub_results(strat_list, prefix):
            results = []
            for i, strat in enumerate(strat_list):
                # Pass df explicitly so it accumulates any upstream added columns
                res = strat.generate_signals(df)
                col = f'{prefix}_{i}_sig'
                df[col] = res['signal']
                
                # Propagate contextual columns added by the sub-strategy forward into df
                new_cols = [c for c in res.columns if c not in df.columns]
                for c in new_cols:
                    df[c] = res[c]
                    
                results.append(col)
            return results

        # Run all unique strategy sets
        common_sigs = get_sub_results(self.common_strategies, 'common')
        buy_only_sigs = get_sub_results(self.buy_only_strategies, 'buy_only')
        sell_only_sigs = get_sub_results(self.sell_only_strategies, 'sell_only')
        
        # Define the Pools
        buy_pool = common_sigs + buy_only_sigs
        sell_pool = common_sigs + sell_only_sigs
        
        # Initialize
        df['signal'] = 0
        
        # --- BUY LOGIC ---
        if buy_pool:
            if self.buy_mode == 'AND':
                is_buy = (df[buy_pool] == 1).all(axis=1)
            else: # OR
                is_buy = (df[buy_pool] == 1).any(axis=1)
        else:
            is_buy = pd.Series(False, index=df.index)
            
        # --- SELL LOGIC ---
        if sell_pool:
            if self.sell_mode == 'AND':
                is_sell = (df[sell_pool] == -1).all(axis=1)
            else: # OR
                is_sell = (df[sell_pool] == -1).any(axis=1)
        else:
            is_sell = pd.Series(False, index=df.index)
            
        # Apply Signals (Sell Priority)
        df.loc[is_buy, 'signal'] = 1
        df.loc[is_sell, 'signal'] = -1
        
        return df
