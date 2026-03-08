from trading_on_tcbs_api.stock_system_v2.core.market_scanner import MarketScanner
from trading_on_tcbs_api.stock_system_v2.auth.auth import StockAuth
from trading_on_tcbs_api.stock_system_v2.strategies import SimpleMAStrategy, RSIStrategy, VolumeStrategy
from trading_on_tcbs_api.stock_system_v2.strategies.combined_strategy import CombinedStrategy
from trading_on_tcbs_api.stock_system_v2 import config

def test():
    auth = StockAuth()
    auth.validate()
    
    strategies = [
        SimpleMAStrategy(short_window=10, long_window=50),
        RSIStrategy(period=14, oversold=30, overbought=70),
        VolumeStrategy(ma_window=20, volume_factor=1.5)
    ]
    strategy = CombinedStrategy(strategies)
    scanner = MarketScanner(auth=auth, strategy=strategy)
    
    scanner.data_provider.prefetch_realtime_prices(config.SYMBOLS)
    
    for sym in config.SYMBOLS:
        df = scanner.data_provider.get_historical_data(sym, days=365, include_live=True)
        if df.empty: continue
        
        df = scanner.indicator_engine.append_indicators(df)
        df_sig = strategy.generate_signals(df)
        
        # Look at the raw signals of each individual strategy for the last row (Friday)
        last_row = df_sig.iloc[-1]
        
        # In CombinedStrategy, the final signal only triggers if ALL sub-strategies agree
        print(f"{sym}: Date={last_row['time'].date()} | Final Signal={last_row['signal']} | MA={last_row.get('signal_ma_10_50', 0)} | RSI={last_row.get('signal_rsi_14', 0)} | VOL={last_row.get('signal_vol_20', 0)}")

if __name__ == "__main__":
    test()
