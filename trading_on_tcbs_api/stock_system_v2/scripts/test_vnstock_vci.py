
from vnstock import Vnstock
import traceback

def test_vci():
    print("Testing vnstock with source='VCI'...")
    try:
        # Initialize with VCI source
        stock = Vnstock().stock(symbol='HPG', source='VCI')
        
        # Fetch history (last 10 days)
        # Note: vnstock v3 uses 'year' resolution by default if not specified? 
        # Let's specify interval='1D'
        df = stock.quote.history(start='2024-01-01', end='2024-01-10', interval='1D')
        
        print("\nData retrieved successfully:")
        print(df.head())
        print(f"\nColumns: {df.columns.tolist()}")
        print(f"Rows: {len(df)}")
        
    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    test_vci()
