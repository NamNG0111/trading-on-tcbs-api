
import pandas as pd
from trading_on_tcbs_api.stock_system_v2.core.backtester import DataProvider
from trading_on_tcbs_api.stock_system_v2.core.indicator_engine import IndicatorEngine
from trading_on_tcbs_api.stock_system_v2.strategies import SimpleMAStrategy, VolumeBoomStrategy

def probe():
    provider = DataProvider()
    engine = IndicatorEngine()
    df = provider.get_historical_data("HPG", days=730)
    df = engine.append_indicators(df)
    
    # Run individual strategies
    ma = SimpleMAStrategy(short_window=20, long_window=50)
    vol = VolumeBoomStrategy(window=20, threshold_pct=10)
    
    df_ma = ma.generate_signals(df)
    df_vol = vol.generate_signals(df)
    
    # Inspect around 2025-10-21
    target_date = "2025-10-21"
    
    # Filter 5 days around target
    mask = (df['time'] >= "2025-10-18") & (df['time'] <= "2025-10-25")
    subset = df.loc[mask].copy()
    
    subset['ma_signal'] = df_ma.loc[mask, 'signal']
    subset['vol_signal'] = df_vol.loc[mask, 'signal']
    subset['vol_boom'] = df_vol.loc[mask, 'vol_boom']
    subset['close'] = df.loc[mask, 'close']
    subset['open'] = df.loc[mask, 'open']
    
    # Combined Logic (AND) simulation
    subset['combined_sell'] = (subset['ma_signal'] == -1) & (subset['vol_signal'] == -1)
    
    print(f"--- Signal Probe for HPG around {target_date} ---")
    print(subset[['time', 'close', 'open', 'ma_signal', 'vol_signal', 'vol_boom', 'combined_sell']])

if __name__ == "__main__":
    probe()
