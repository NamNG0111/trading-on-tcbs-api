from vnstock import Vnstock
try:
    stock = Vnstock().stock(symbol='TCB', source='TCBS')
    df = stock.quote.history(start='2021-04-16', end='2026-04-15', interval='1D')
    print("TCBS Success. rows:", len(df) if df is not None else 0)
    print(df.head(2))
except Exception as e:
    print("TCBS Error:", e)

try:
    stock = Vnstock().stock(symbol='TCB', source='DNSE')
    df = stock.quote.history(start='2021-04-16', end='2026-04-15', interval='1D')
    print("DNSE Success. rows:", len(df) if df is not None else 0)
    print(df.head(2))
except Exception as e:
    print("DNSE Error:", e)
