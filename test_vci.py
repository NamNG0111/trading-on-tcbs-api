from vnstock.core.utils import client
from vnstock.core.utils.user_agent import get_headers
from vnstock.explorer.vci.const import _GRAPHQL_URL

url = _GRAPHQL_URL
headers = get_headers(data_source='VCI', random_agent=False)

payload = {"query":"query Query($ticker: String!, $lang: String!) {\n  TickerPriceInfo(ticker: $ticker) {\n    ticker\n  }\n}\n","variables":{"ticker":"TCB","lang":"vi"}}
response = client.send_request(url=url, headers=headers, method="POST", payload=payload)
print(response)
