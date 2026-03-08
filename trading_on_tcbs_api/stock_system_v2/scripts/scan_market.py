
import sys
import os


from trading_on_tcbs_api.stock_system_v2.core.market_scanner import MarketScanner
from trading_on_tcbs_api.stock_system_v2.auth.auth import StockAuth
from trading_on_tcbs_api.stock_system_v2.strategies import (
    SimpleMAStrategy,
    VolumeBoomStrategy,
    RSIStrategy,
    CombinedStrategy,
    DipBuyStrategy,
    CumulativeDropStrategy
)

# VN30 List (Approximate)
VN30 = [
    "ACB", "BCM", "BID", "BVH", "CTG", 
    "FPT", "GAS", "GVR", "HDB", "HPG", 
    "MBB", "MSN", "MWG", "PLX", "POW", 
    "SAB", "SHB", "SSB", "SSI", "STB", 
    "TCB", "TPB", "VCB", "VHM", "VIB", 
    "VIC", "VJC", "VNM", "VPB", "VRE"
]

# my current list

stock_list = [
    "TCX", "TCB", "BAF", "DXG", "MWG", "TPB", "VCI", "SHS", "EIB", "HDB",
    "BID", "DBC", "VIX", "GEX", "GEL", "VPB", "MSN", "FPT", "HPG", "MBB",
    "ACB", "CTG", "DGC", "GAS", "POW", "LPB", "SHB", "SSI", "STB", "VCB",
    "VIC", "VHM", "VRE", "VPL", "VIB", "VNM", "VJC", "GVR", "BMP", "PVT",
    "VCK", "VPX", "DPG", "HAG", "FRT", "OCB", "VTP", "CTR", "VGI", "HPA",
    "CTS", "FOX", "HCM", "PAN", "GEE", "VSC", "HAH", "VGC", "PC1", "CII",
    "MBS", "ORS", "GMD", "KHG", "PNJ", "MSB", "PLX", "KBC", "CEO", "PDR",
    "HDG", "BCM", "KDH", "NVL", "NLG", "DXS", "HDC", "VCG", "CTD", "HHV",
    "C4G", "FCN", "NKG", "HSG", "NTL", "VGS", "VND", "DSE", "VDS", "VFS",
    "DSC", "BSI", "DCM", "DPM", "BFC", "PVD", "PVS", "FMC", "MPC", "ANV",
    "VHC", "TNG", "TCM"
]

def main():
    print(f"--- DAILY MARKET SCANNER (VN30) ---")
    
    # 0. Initialize Auth (Crucial for Live Data)
    auth = StockAuth()
    if not auth.validate():
        print("[Error] Authentication failed. Exiting.")
        return
    
    # 1. Define Strategies
    sma_exit_buy_dip = SimpleMAStrategy(short_window=1, long_window=20, invert=True) # Exit when crossing above SMA 20 (for Dip Buy)
    sma_exit_basic = SimpleMAStrategy(short_window=1, long_window=20, invert=False)  # Basic exit condition: cross below SMA 20
    
    # Strategy 1: Dip Buy Combo
    dip_buy = DipBuyStrategy(sma_window=20, drop_pct=10.0)
    strat_dip = CombinedStrategy(
        strategies=[],
        buy_strategies=[dip_buy],
        sell_strategies=[sma_exit_buy_dip],
        buy_mode="AND", 
        sell_mode="OR"
    )
    
    # Strategy 2: Volume Breakout Combo
    vol_buy = VolumeBoomStrategy(window=20, threshold_pct=20.0)
    strat_vol = CombinedStrategy(
        strategies=[],
        buy_strategies=[vol_buy],
        sell_strategies=[],
        buy_mode="AND", 
        sell_mode="OR"
    )
    
    # Strategy 3a: RSI Basic (< 30)
    rsi_basic = RSIStrategy(period=14, oversold=30, overbought=70, is_reversal=False)
    strat_rsi_basic = CombinedStrategy(
        strategies=[],
        buy_strategies=[rsi_basic],
        sell_strategies=[],
        buy_mode="AND", 
        sell_mode="OR"
    )
    
    # Strategy 3b: RSI Reversal (Breakout > 30)
    rsi_reversal = RSIStrategy(period=14, oversold=30, overbought=70, is_reversal=True)
    strat_rsi_reversal = CombinedStrategy(
        strategies=[rsi_reversal],
        buy_strategies=[],
        sell_strategies=[],
        buy_mode="AND", 
        sell_mode="OR"
    )
    # Strategy 4: 3-Day Drop (>10%)
    roc_buy = CumulativeDropStrategy(days=3, drop_pct=10.0)
    strat_roc = CombinedStrategy(
        strategies=[],
        buy_strategies=[roc_buy],
        sell_strategies=[],
        buy_mode="AND",
        sell_mode="OR"
    )
    
    # Strategy 5: SMA Crossover (20/50)
    # A single SimpleMAStrategy naturally generates BUY (1) on cross up and SELL (-1) on cross down.
    sma_cross = SimpleMAStrategy(short_window=20, long_window=50, invert=False)
    strat_sma_cross = CombinedStrategy(
        strategies=[],
        buy_strategies=[sma_cross, vol_buy],
        sell_strategies=[sma_cross],
        buy_mode="AND",
        sell_mode="OR"
    )
    
    # Package them all up!
    my_strategies = {
        f"DipBuy ({dip_buy.drop_pct}%)": strat_dip,
        f"Volume Breakout ({vol_buy.threshold_multiplier * 100 - 100:.0f}%)": strat_vol,
        f"RSI Basic (<{rsi_basic.oversold})": strat_rsi_basic,
        f"RSI Reversal (Entry)": strat_rsi_reversal,
        f"{roc_buy.days}-Day Drop ({roc_buy.drop_pct}%)": strat_roc,
        f"SMA Crossover ({sma_cross.short_window}/{sma_cross.long_window})": strat_sma_cross
    }
    
    print("\n--- ACTIVE STRATEGIES CONFIGURATION ---")
    for key, strat in my_strategies.items():
        print(f"[{key}] -> {strat.get_brief() if hasattr(strat, 'get_brief') else 'No description available.'}")
    print("---------------------------------------\n")
    
    # 2. Initialize Scanner with Auth
    scanner = MarketScanner(strategies=my_strategies, auth=auth)
    
    # 3. Run Scan
    # Use list u wanted to run
    symbols = stock_list
    
    # Allow overriding symbols via command line args
    if len(sys.argv) > 1:
        symbols = sys.argv[1].split(",")
        
    # results = scanner.scan(symbols)
    # scanner.print_results(results)
    
    # User Request: Produce Dictionary of DataFrames
    df_results_dict = scanner.scan_to_df(symbols)
    
    if df_results_dict:
        print("\n" + "="*80)
        print("SCAN RESULTS (Enriched Context by Strategy)")
        print("="*80)
        
        for strat_name, df in df_results_dict.items():
            print(f"\n--- Strategy: {strat_name} ---")
            
            # Sort strategically based on available contextual percentage columns (dynamic names)
            sort_target = None
            sort_asc = True
            
            # Prioritize sorting by Volume if it's explicitly a volume-based scan
            if '%_vol_increase' in df.columns:
                sort_target = '%_vol_increase'
                sort_asc = False # Volume spikes are good; descending sort
            else:
                for col in df.columns:
                    if col.startswith('%_from_sma'):
                        sort_target = col
                        break
                    elif col.startswith('roc_'):
                        sort_target = col
                        break
                    elif col.startswith('rsi_'):
                        sort_target = col
                        sort_asc = True # Most oversold (lowest) first
                        break
                        
            if sort_target:
                df = df.sort_values(by=sort_target, ascending=sort_asc)
                
            print(df.to_markdown(index=False) if hasattr(df, 'to_markdown') else df)
            
        print("="*80)
        return df_results_dict
    else:
        print("\n[Scanner] No signals found.")
        return {}

if __name__ == "__main__":
    signals = main()
    
    # Export dictionary into separate global variables for PyCharm SciView Data Viewer
    if signals:
        import re
        for strat_name, df in signals.items():
            # Clean strategy name into a valid python variable (e.g. 'DipBuy (10.0%)' -> 'df_dipbuy_10')
            clean_name = re.sub(r'[^a-zA-Z0-9]+', '_', strat_name.replace('.0', 'pct')).strip('_').lower()
            var_name = f"df_{clean_name}"
            globals()[var_name] = df
            print(f"- Exported to IDE Variable: {var_name}")
