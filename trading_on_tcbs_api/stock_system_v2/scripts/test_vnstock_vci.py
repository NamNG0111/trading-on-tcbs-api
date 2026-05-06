
from vnstock.api.quote import Quote
import traceback

def test_vci():
    print("Testing vnstock with source='VCI'...")
    try:
        stock = Quote(symbol='HPG', source='VCI')
        df = stock.history(start='2024-01-01', end='2024-01-10', interval='1D')
        
        print("\nData retrieved successfully:")
        print(df.head())
        print(f"\nColumns: {df.columns.tolist()}")
        print(f"Rows: {len(df)}")
        
    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    test_vci()
