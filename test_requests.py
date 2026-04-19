import requests
from vnstock.explorer.vci.const import _GRAPHQL_URL

url = _GRAPHQL_URL
payload = {"query":"query Query($ticker: String!, $lang: String!) {\n  TickerPriceInfo(ticker: $ticker) {\n    ticker\n  }\n}\n","variables":{"ticker":"TCB","lang":"vi"}}
headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
try:
    r = requests.post(url, json=payload, headers=headers)
    print("Status:", r.status_code)
    print("Headers:", r.headers)
    print("Text:", r.text[:200])
except Exception as e:
    print(e)
