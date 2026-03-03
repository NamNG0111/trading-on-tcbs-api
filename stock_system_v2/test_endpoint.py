
import requests
import datetime
import time
from trading_on_tcbs_api.stock_system_v2.auth import StockAuth
from trading_on_tcbs_api.stock_system_v2 import config

def test_endpoint():
    auth = StockAuth()
    if not auth.validate():
        print("Auth failed.")
        return

    symbol = "HPG"
    to_ts = int(datetime.datetime.now().timestamp())
    
    # URL patterns to test
    urls = [
        "https://apiextaws.tcbs.com.vn/stock-insight/v2/stock/bars-long-term"
    ]

    for base_url in urls:
        print(f"\nTesting: {base_url}")
        params = {
            "ticker": symbol,
            "type": "stock",
            "resolution": "D",
            "to": to_ts,
            "countBack": 50
        }
        
        # Mimic vnstock headers AND add Auth
        headers = {
            "Authorization": f"Bearer {auth.token}",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9,vi-VN;q=0.8,vi;q=0.7",
            "Connection": "keep-alive",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
            "Referer": "https://tcinvest.tcbs.com.vn/",
            "Origin": "https://tcinvest.tcbs.com.vn/"
        }
        
        try:
            resp = requests.get(base_url, headers=headers, params=params)
            print(f"Status: {resp.status_code}")
            if resp.status_code == 200:
                print("SUCCESS! Data:")
                print(str(resp.json())[:300])
                break
            else:
                print(f"Response: {resp.text[:200]}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    test_endpoint()
