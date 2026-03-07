
import json
import requests
import datetime
import time
from trading_on_tcbs_api.stock_system_v2.auth.auth import StockAuth
from trading_on_tcbs_api.stock_system_v2 import config

def probe_endpoints():
    auth = StockAuth()
    if not auth.validate():
        print("Authentication failed. Please fix token first.")
        return

    symbol = "HPG"
    today = datetime.datetime.now()
    from_date = (today - datetime.timedelta(days=10)).strftime("%Y-%m-%d")
    to_date = today.strftime("%Y-%m-%d")
    
    # Common timestamps for API (milliseconds)
    to_ts = int(today.timestamp())
    from_ts = int((today - datetime.timedelta(days=30)).timestamp())

    print(f"Probing historical data for {symbol}...")
    print(f"Base URL: {config.BASE_URL}")
    
    # List of potential endpoints to try
    endpoints = [
        {
            "url": f"/stock-insight/v1/stock/bars-long-term",
            "method": "GET",
            "params": {
                "ticker": symbol,
                "type": "stock",
                "resolution": "D",
                "from": from_ts,
                "to": to_ts
            }
        },
        {
            "url": f"/stock-insight/v1/intra/stock/{symbol}",
            "method": "GET",
            "params": {
                "page": 0,
                "size": 100
            }
        },
        {
            "url": f"/data/v1/quotes/{symbol}/history",
            "method": "GET",
            "params": {
                "from": from_date,
                "to": to_date,
                "resolution": "1D"
            }
        },
        # Sometimes it's in a different service
        {
            "url": f"/market-data/v1/stock/{symbol}/history",
            "method": "GET",
            "params": {}
        }
    ]

    headers = {
        "Authorization": f"Bearer {auth.token}",
        "Content-Type": "application/json"
    }

    for ep in endpoints:
        full_url = f"{config.BASE_URL}{ep['url']}"
        print(f"\nProbing: {full_url}")
        try:
            if ep['method'] == 'GET':
                resp = requests.get(full_url, headers=headers, params=ep.get('params'))
            
            print(f"Status: {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                print("SUCCESS! Data sample:")
                print(str(data)[:200]) # Print first 200 chars
            else:
                print(f"Failed. Response: {resp.text[:100]}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    probe_endpoints()
