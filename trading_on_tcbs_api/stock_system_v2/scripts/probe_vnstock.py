

import requests
from vnstock.api.quote import Quote

# Monkey patch requests.get to print URL
# (Same patching logic as before)
original_get = requests.get

def patched_get(url, **kwargs):
    print(f"CAPTURED URL: {url}")
    if 'params' in kwargs:
        print(f"PARAMS: {kwargs['params']}")
    if 'headers' in kwargs:
        print(f"HEADERS: {kwargs['headers']}")
    return original_get(url, **kwargs)

requests.get = patched_get

def probe():
    print("Calling Quote(...).history...")
    try:
        stock = Quote(symbol='HPG', source='TCBS')
        df = stock.history(start='2024-01-01', end='2024-01-05', interval='1D')
        
        print("\nData retrieved successfully:")
        print(df.head())
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    probe()
