import sys
import os
import pandas as pd
from datetime import datetime

# ==========================================
# BACKTEST CONFIGURATION
# ==========================================
INITIAL_CAPITAL = 1_000_000_000  # 1 Billion VND
TEST_DAYS = 1825                 # 5 Years (~1250 Trading Days)

# Analysis Modules
SHOW_PORTFOLIO_SUMMARY = False    # Table 1: Standard strategy execution mapping (BUY+SELL)
SHOW_FORWARD_RETURNS = True      # Table 2: Mathematical prediction X days after BUY signal
SHOW_FIXED_HOLD = False           # Table 3: Chronological portfolio simulating fixed holding period
FORWARD_DAYS = [3, 5, 10, 20]    # N-Day holding periods to analyze after every BUY signal
# ==========================================

import numpy as np
from trading_on_tcbs_api.stock_system_v2.core.backtester import Backtester
from trading_on_tcbs_api.stock_system_v2.strategies import (
    SimpleMAStrategy,
    VolumeBoomStrategy,
    RSIStrategy,
    CombinedStrategy,
    DipBuyStrategy,
    CumulativeDropStrategy
)
from trading_on_tcbs_api.stock_system_v2.scripts.scan_market import stock_list, VN30

def main():
    print(f"--- MARKET WIDE BACKTESTER ---")
    
    # 1. Define Strategies (Same as scan_market.py)
    sma_exit_buy_dip = SimpleMAStrategy(short_window=1, long_window=20, invert=True)
    sma_exit_basic = SimpleMAStrategy(short_window=1, long_window=20, invert=False)
    
    dip_buy = DipBuyStrategy(sma_window=20, drop_pct=10.0)
    strat_dip = CombinedStrategy(
        strategies=[], buy_strategies=[dip_buy], sell_strategies=[sma_exit_buy_dip], buy_mode="AND", sell_mode="OR"
    )
    
    vol_buy = VolumeBoomStrategy(window=20, threshold_pct=100.0)
    strat_vol = CombinedStrategy(
        strategies=[], buy_strategies=[vol_buy], sell_strategies=[sma_exit_basic], buy_mode="AND", sell_mode="OR"
    )
    
    rsi_basic = RSIStrategy(period=14, oversold=30, overbought=70, is_reversal=False)
    strat_rsi_basic = CombinedStrategy(
        strategies=[], buy_strategies=[rsi_basic], sell_strategies=[], buy_mode="AND", sell_mode="OR"
    )
    
    rsi_reversal = RSIStrategy(period=14, oversold=30, overbought=70, is_reversal=True)
    strat_rsi_reversal = CombinedStrategy(
        strategies=[rsi_reversal], buy_strategies=[], sell_strategies=[], buy_mode="AND", sell_mode="OR"
    )
    
    roc_buy = CumulativeDropStrategy(days=3, drop_pct=10.0)
    strat_roc = CombinedStrategy(
        strategies=[], buy_strategies=[roc_buy], sell_strategies=[], buy_mode="AND", sell_mode="OR"
    )
    
    sma_cross = SimpleMAStrategy(short_window=20, long_window=50, invert=False)
    strat_sma_cross = CombinedStrategy(
        strategies=[], buy_strategies=[sma_cross, vol_buy], sell_strategies=[sma_cross], buy_mode="AND", sell_mode="OR"
    )
    
    my_strategies = {
        f"DipBuy ({dip_buy.drop_pct}%)": strat_dip,
        f"Volume Breakout ({vol_buy.threshold_multiplier * 100 - 100:.0f}%)": strat_vol,
        f"RSI Basic (<{rsi_basic.oversold})": strat_rsi_basic,
        f"RSI Reversal (Entry)": strat_rsi_reversal,
        f"{roc_buy.days}-Day Drop ({roc_buy.drop_pct}%)": strat_roc,
        f"SMA Crossover ({sma_cross.short_window}/{sma_cross.long_window}) + Vol": strat_sma_cross
    }
    
    print("\n--- STRATEGIES TO BACKTEST ---")
    for key in my_strategies.keys():
        print(f"[*] {key}")
    print("------------------------------\n")
    
    # 2. Initialize Backtester using global configuration
    backtester = Backtester(initial_capital=INITIAL_CAPITAL)
    
    # Allow overriding symbols via command line args
    symbols = VN30
    if len(sys.argv) > 1:
        symbols = sys.argv[1].split(",")
    
    print(f"Running Backtest for {len(symbols)} symbols over the last {TEST_DAYS} days...\n")
    
    # Results dictionary: { strategy_name: [ list of reports ] }
    all_results = {}
    
    for i, symbol in enumerate(symbols):
        print(f"[{i+1}/{len(symbols)}] Backtesting {symbol}...", end='\\r', flush=True)
        # To avoid re-fetching data per strategy, the backtester internally fetches it.
        # It's okay for now, DataProvider caches it in memory/disk.
        
        for strat_name, strat in my_strategies.items():
            if strat_name not in all_results:
                all_results[strat_name] = []
                
            report = backtester.run(strat, symbol, days=TEST_DAYS, forward_returns_days=FORWARD_DAYS)
            if report and 'total_return_pct' in report:
                all_results[strat_name].append(report)
                
    print(f"\\n\\n[Backtest Completed]")
    print(f"================================================================================")
    print(f"MARKET-WIDE PERFORMANCE SUMMARY ({TEST_DAYS} Days | {INITIAL_CAPITAL:,.0f} VND Start)")
    print(f"================================================================================")
    
    summary_data = []
    
    for strat_name, reports in all_results.items():
        if not reports:
            continue
            
        returns = [r['total_return_pct'] for r in reports]
        trades = [r['total_trades'] for r in reports]
        win_rates = [r.get('win_rate_pct', 0) for r in reports]
        mdds = [r.get('max_drawdown_pct', 0) for r in reports]
        hold_days = [r.get('avg_hold_days', 0) for r in reports]
        
        # Filter infinite profit factors completely wiping out arrays
        pfs = [r.get('profit_factor', 0) for r in reports if r.get('profit_factor', 0) != float('inf')]
        
        avg_return = sum(returns) / len(returns) if returns else 0
        avg_win_rate = sum(win_rates) / len(win_rates) if win_rates else 0
        avg_mdd = sum(mdds) / len(mdds) if mdds else 0
        avg_pf = sum(pfs) / len(pfs) if pfs else 0
        avg_hold = sum(hold_days) / len(hold_days) if hold_days else 0
        
        total_trades = sum(trades)
        max_return = max(returns) if returns else 0
        min_return = min(returns) if returns else 0
        
        summary_data.append({
            "Strategy": strat_name,
            "Avg Return (%)": round(avg_return, 2),
            "Avg MDD (%)": round(avg_mdd, 2),
            "Win Rate (%)": round(avg_win_rate, 2),
            "Profit Factor": round(avg_pf, 2),
            "Avg Hold (Days)": round(avg_hold, 1),
            "Best Stock (%)": round(max_return, 2),
            "Worst Stock (%)": round(min_return, 2),
            "Avg Trades": round(total_trades / len(returns), 1) if len(returns) > 0 else 0
        })
        
    df_summary = pd.DataFrame(summary_data)
    # Sort by Average Return primarily
    df_summary = df_summary.sort_values(by="Avg Return (%)", ascending=False)
    
    if SHOW_PORTFOLIO_SUMMARY:
        print(df_summary.to_markdown(index=False))
        print(f"================================================================================\n")
    else:
        print(f"[Table 1: Portfolio Summary Hidden]\n")
    
    df_fwd = pd.DataFrame()
    df_fixed = pd.DataFrame()
    
    # --------------------------------------------------------------------------------
    # ADVANCED METRIC: N-DAY FORWARD RETURNS ANALYSIS
    # --------------------------------------------------------------------------------
    if SHOW_FORWARD_RETURNS:
        fwd_data = []
        
        for strat_name, reports in all_results.items():
            if not reports:
                continue
                
            sample_report = reports[0]
            if 'forward_returns' not in sample_report:
                continue
                
            for d in FORWARD_DAYS:
                all_rets = []
                for r in reports:
                    if 'forward_returns' in r and d in r['forward_returns']:
                        all_rets.extend(r['forward_returns'][d])
                
                if not all_rets:
                    continue
                    
                mean_ret = np.mean(all_rets) * 100
                median_ret = np.median(all_rets) * 100
                win_rate = (sum(1 for x in all_rets if x > 0) / len(all_rets)) * 100
                best_ret = np.max(all_rets) * 100
                worst_ret = np.min(all_rets) * 100
                
                fwd_data.append({
                    "Strategy": strat_name,
                    "Hold (Days)": d,
                    "Mean (%)": round(mean_ret, 2),
                    "Median (%)": round(median_ret, 2),
                    "Win Rate (%)": round(win_rate, 2),
                    "Best (%)": round(best_ret, 2),
                    "Worst (%)": round(worst_ret, 2),
                    "Total Signals": len(all_rets)
                })
                
        if fwd_data:
            df_fwd = pd.DataFrame(fwd_data)
            df_fwd = df_fwd.sort_values(by=["Strategy", "Hold (Days)"])
            
            print(f"================================================================================")
            print(f"FORWARD RETURNS ANALYSIS (Static N-Day Hold after every BUY signal)")
            print(f"================================================================================")
            print(df_fwd.to_markdown(index=False))
            print(f"================================================================================\n")
        
    # --------------------------------------------------------------------------------
    # ADVANCED METRIC: FIXED N-DAY HOLD PORTFOLIO SIMULATION
    # --------------------------------------------------------------------------------
    if SHOW_FIXED_HOLD:
        fixed_data = []
        
        for strat_name, reports in all_results.items():
            if not reports:
                continue
                
            sample_report = reports[0]
            if 'fixed_hold_results' not in sample_report:
                continue
                
            for d in FORWARD_DAYS:
                sim_returns = []
                sim_wins = []
                sim_trades = []
                sim_bests = []
                sim_worsts = []
                
                for r in reports:
                    if 'fixed_hold_results' in r and d in r['fixed_hold_results']:
                        res = r['fixed_hold_results'][d]
                        if res['total_trades'] > 0:
                            sim_returns.append(res['total_return_pct'])
                            sim_wins.append(res['win_rate_pct'])
                            sim_trades.append(res['total_trades'])
                            sim_bests.append(res['best_trade_pct'])
                            sim_worsts.append(res['worst_trade_pct'])
                
                if not sim_returns:
                    continue
                    
                avg_return = np.mean(sim_returns)
                avg_win_rate = np.mean(sim_wins)
                avg_trades = np.mean(sim_trades)
                best_trade = np.max(sim_bests)
                worst_trade = np.min(sim_worsts)
                
                fixed_data.append({
                    "Strategy": strat_name,
                    "Hold (Days)": d,
                    "Avg Portfolio Return (%)": round(avg_return, 2),
                    "Avg Win Rate (%)": round(avg_win_rate, 2),
                    "Best Trade (%)": round(best_trade, 2),
                    "Worst Trade (%)": round(worst_trade, 2),
                    "Avg Trades / Stock": round(avg_trades, 1)
                })
                
        if fixed_data:
            df_fixed = pd.DataFrame(fixed_data)
            df_fixed = df_fixed.sort_values(by=["Strategy", "Hold (Days)"])
            print(f"================================================================================")
            print(f"FIXED N-DAY HOLD PORTFOLIO SIMULATION (Chronological Execution | 1 Trade at a time)")
            print(f"================================================================================")
            print(df_fixed.to_markdown(index=False))
            print(f"================================================================================\n")
            
    # --------------------------------------------------------------------------------
    # EXPORT RAW SIGNALS LOG TO CSV
    # --------------------------------------------------------------------------------
    dict_details = {}
    export_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "exports")
    os.makedirs(export_dir, exist_ok=True)
    
    for strat_name, reports in all_results.items():
        strat_details = []
        for r in reports:
            if 'signal_details' in r:
                strat_details.extend(r['signal_details'])
                
        if strat_details:
            df_det = pd.DataFrame(strat_details)
            # Reorder columns to put Ticker and time first
            cols = df_det.columns.tolist()
            if 'Ticker' in cols and 'time' in cols:
                cols.insert(0, cols.pop(cols.index('Ticker')))
                cols.insert(1, cols.pop(cols.index('time')))
                df_det = df_det[cols]
                
            dict_details[strat_name] = df_det
            
            # Save to CSV
            safe_name = "".join([c if c.isalnum() else "_" for c in strat_name])
            csv_path = os.path.join(export_dir, f"{safe_name}_signals.csv")
            df_det.to_csv(csv_path, index=False)
            
    if dict_details:
        print(f"[*] Detailed strategy signals exported to: {export_dir}")
        print(f"================================================================================\n")
    
    return df_summary, df_fwd, df_fixed, dict_details

if __name__ == "__main__":
    summary_strats, forward_return, fixed_return, detailed_signals = main()
