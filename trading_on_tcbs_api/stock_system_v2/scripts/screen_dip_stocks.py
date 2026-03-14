"""
Screening Script: Identify stocks with strong "lower wick" characteristics.

Analyzes the distribution of intraday dip magnitude: (close_yesterday - low) / close_yesterday
across VN30 + TCX to find stocks that frequently dip hard intraday then recover.

Usage:
    python3 -m trading_on_tcbs_api.stock_system_v2.scripts.screen_dip_stocks
    python3 -m trading_on_tcbs_api.stock_system_v2.scripts.screen_dip_stocks TCX,FPT,HPG
"""

import sys
import pandas as pd
import numpy as np
from trading_on_tcbs_api.stock_system_v2.data_ingest.data_provider import DataProvider
from trading_on_tcbs_api.stock_system_v2.scripts.scan_market import VN30

# Default stock universe: VN30 + TCX
DEFAULT_SYMBOLS = sorted(set(VN30 + ["TCX"]))

# Analysis window
HISTORY_DAYS = 365  # 1 year of history


def compute_dip_stats(df: pd.DataFrame, symbol: str) -> dict:
    """
    Compute intraday dip statistics for a single stock.
    
    Dip = (close_yesterday - low_today) / close_yesterday
    This measures how far the price dropped from yesterday's close during today's session.
    """
    if df.empty or len(df) < 20:
        return None

    # Compute the dip metric: how far today's low is below yesterday's close
    prev_close = df['close'].shift(1)
    dip_pct = (prev_close - df['low']) / prev_close
    
    # Drop NaN (first row has no prev_close)
    dip_pct = dip_pct.dropna()
    
    # Only consider positive dips (low was actually below previous close)
    positive_dips = dip_pct[dip_pct > 0]
    
    # Also compute the recovery: how much closes recovered from the low
    recovery_pct = (df['close'] - df['low']) / df['low']
    recovery_pct = recovery_pct.iloc[1:].dropna()  # Align with dip_pct
    
    avg_volume = df['volume'].mean()
    
    return {
        'Symbol': symbol,
        'Sessions': len(dip_pct),
        'Avg Volume': f"{avg_volume:,.0f}",
        
        # Dip frequency: how often does price dip below prev close?
        'Dip Freq (%)': round(len(positive_dips) / len(dip_pct) * 100, 1),
        
        # Dip > 1%, 2%, 3% frequency
        '> 1% Freq': round((dip_pct > 0.01).sum() / len(dip_pct) * 100, 1),
        '> 2% Freq': round((dip_pct > 0.02).sum() / len(dip_pct) * 100, 1),
        '> 3% Freq': round((dip_pct > 0.03).sum() / len(dip_pct) * 100, 1),
        
        # Percentile distribution of ALL dip magnitudes (including 0 / negative)
        'P50 (%)': round(dip_pct.quantile(0.50) * 100, 2),
        'P75 (%)': round(dip_pct.quantile(0.75) * 100, 2),
        'P90 (%)': round(dip_pct.quantile(0.90) * 100, 2),
        'P95 (%)': round(dip_pct.quantile(0.95) * 100, 2),
        
        # Recovery stats: when it dips, how much does it recover by close?
        'Avg Recovery (%)': round(recovery_pct.mean() * 100, 2),
        'Median Recovery (%)': round(recovery_pct.median() * 100, 2),
    }


def main():
    # Parse symbols from command line or use defaults
    if len(sys.argv) > 1:
        symbols = sys.argv[1].split(",")
    else:
        symbols = DEFAULT_SYMBOLS

    print(f"--- INTRADAY DIP SCREENING ---")
    print(f"Analyzing {len(symbols)} stocks over {HISTORY_DAYS} days")
    print(f"Metric: (close_yesterday - low_today) / close_yesterday\n")

    data_provider = DataProvider(auth=None)
    results = []

    for i, symbol in enumerate(symbols):
        print(f"  [{i+1}/{len(symbols)}] Screening {symbol}...", end='\r', flush=True)
        try:
            df = data_provider.get_historical_data(symbol, days=HISTORY_DAYS, include_live=False)
            stats = compute_dip_stats(df, symbol)
            if stats:
                results.append(stats)
        except Exception as e:
            print(f"  [SKIP] {symbol}: {e}")

    print(f"\n\n{'='*100}")
    print(f"INTRADAY DIP CHARACTERISTICS — SCREENING RESULTS")
    print(f"{'='*100}")

    if results:
        df_results = pd.DataFrame(results)
        # Sort by P90 descending — stocks with the largest 90th-percentile dips
        df_results = df_results.sort_values(by='P90 (%)', ascending=False)
        print(df_results.to_markdown(index=False))
        
        print(f"\n{'='*100}")
        print("INTERPRETATION:")
        print("  - High P90/P95 = Frequently dips hard intraday (good candidate for dip-buy)")
        print("  - High 'Dip Freq' + High 'Avg Recovery' = Strong lower wick pattern")
        print("  - Low 'Avg Volume' = Low liquidity (matches the thesis)")
        print(f"{'='*100}\n")
        
        return df_results
    else:
        print("[No results]")
        return pd.DataFrame()


if __name__ == "__main__":
    screening_results = main()
