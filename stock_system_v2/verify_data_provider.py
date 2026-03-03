
import pandas as pd
from trading_on_tcbs_api.stock_system_v2.data_provider import DataProvider
from trading_on_tcbs_api.stock_system_v2.auth import StockAuth

def verify():
    # 1. Init Auth (needed for live price)
    print("Initializing Auth...")
    auth = StockAuth()
    if not auth.validate():
        print("Auth failed.")
        return

    # 2. Init DataProvider with Auth
    provider = DataProvider(auth=auth)
    
    symbol = "HPG"
    print(f"\nFetching data for {symbol} (History + Live)...")
    
    # 3. Get Data
    df = provider.get_historical_data(symbol, days=30, include_live=True)
    
    # 4. Show Result
    print("\nResult (Last 5 rows):")
    print(df.tail())
    
    print("\nLatest Row Details:")
    if not df.empty:
        last = df.iloc[-1]
        print(f"Date: {last['time']}")
        print(f"Close: {last['close']}")
        print(f"Source Type: {'Live' if last['volume'] == 0 else 'History'}") 
        # Note: My live logic sets volume=0 for the new row, vnstock history usually has volume. 
        # This is a good marker for now.

if __name__ == "__main__":
    verify()
