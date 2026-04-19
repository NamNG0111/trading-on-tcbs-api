from vnstock import Vnstock
import traceback

sources = ['KBS', 'MSN', 'FMP']
for src in sources:
    print(f"--- Trying {src} ---")
    try:
        stock = Vnstock().stock(symbol='TCB', source=src)
        df = stock.quote.history(start='2021-04-16', end='2026-04-15', interval='1D')
        print(f"{src} Success. rows:", len(df) if (df is not None and len(df) > 0) else 0)
        if df is not None and not df.empty:
            print(df.head(1).to_string())
    except Exception as e:
        print(f"{src} Error:", type(e).__name__, str(e))
