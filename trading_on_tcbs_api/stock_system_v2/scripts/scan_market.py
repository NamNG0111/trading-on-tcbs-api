
import sys
import os


from trading_on_tcbs_api.stock_system_v2.core.market_scanner import MarketScanner
from trading_on_tcbs_api.stock_system_v2.auth.auth import StockAuth
from trading_on_tcbs_api.stock_system_v2.strategies import (
    SimpleMAStrategy,
    VolumeBoomStrategy,
    RSIStrategy,
    CombinedStrategy,
    DipBuyStrategy
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
    
    # 1. Define Strategy
    ma = SimpleMAStrategy(short_window=20, long_window=50)
    vol = VolumeBoomStrategy(window=20, threshold_pct=10)
    rsi = RSIStrategy(period=14)
    
    # Buy: Price Drops 10% from SMA(20) AND Volume Booms (10% over Vol_SMA)
    # Sell: Price crosses above SMA(20)
    dip_buy = DipBuyStrategy(sma_window=20, drop_pct=5.0)
    vol_boom = VolumeBoomStrategy(window=20, threshold_pct=10.0)
    sma_exit = SimpleMAStrategy(short_window=1, long_window=20, invert=True)
    
    strategy = CombinedStrategy(
        strategies=[],
        buy_strategies=[dip_buy],
        sell_strategies=[sma_exit],
        buy_mode="AND", 
        sell_mode="OR"
    )
    
    # 2. Initialize Scanner with Auth
    scanner = MarketScanner(strategy=strategy, auth=auth)
    
    # 3. Run Scan
    # Use list u wanted to run
    symbols = stock_list
    
    # Allow overriding symbols via command line args
    if len(sys.argv) > 1:
        symbols = sys.argv[1].split(",")
        
    # results = scanner.scan(symbols)
    # scanner.print_results(results)
    
    # User Request: Produce DataFrame
    df_results = scanner.scan_to_df(symbols)
    
    if not df_results.empty:
        # Sort by drop severity if the context column exists
        if '%_from_sma20' in df_results.columns:
            df_results = df_results.sort_values(by='%_from_sma20', ascending=True)
            
        print("\n" + "="*80)
        print("SCAN RESULTS (Enriched Context)")
        print("="*80)
        print(df_results.to_markdown(index=False) if hasattr(df_results, 'to_markdown') else df_results)
        print("="*80)
        return df_results
    else:
        print("\n[Scanner] No signals found.")
        return df_results

if __name__ == "__main__":
    signal = main()
