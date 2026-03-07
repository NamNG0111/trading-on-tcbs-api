
from trading_on_tcbs_api.stock_system_v2.data_ingest.data_provider import DataProvider
from trading_on_tcbs_api.stock_system_v2.auth.auth import StockAuth
import json

def verify():
    print("--- Verifying Live Price Fetching ---")
    
    # 1. Auth
    auth = StockAuth()
    if not auth.validate():
        print("Auth failed.")
        return
        
    print(f"Token: {auth.token[:10]}...")
    
    # 2. Provider
    provider = DataProvider(auth=auth)
    
    # 3. Test HPG
    symbol = "HPG"
    print(f"\nFetching live price for {symbol}...")
    price = provider.get_realtime_price(symbol)
    
    print(f"Result: {price}")
    
    if price:
        print("SUCCESS: Live price fetched.")
    else:
        print("FAILURE: Live price is None/0.")
        
    # 4. Debug API Logic Specifics (Simulate inside get_realtime_price)
    # We want to see the RAW response to ensure field names are correct
    import requests
    from trading_on_tcbs_api.stock_system_v2 import config
    
    url = f"{config.BASE_URL}/tartarus/v1/tickerCommons"
    params = {'tickers': symbol}
    headers = {
        "Authorization": f"Bearer {auth.token}",
        "Content-Type": "application/json"
    }
    print(f"\n[DEBUG] Raw API Call to {url}")
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=5)
        print(f"Status: {resp.status_code}")
        print(f"Body: {json.dumps(resp.json(), indent=2)}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    verify()
