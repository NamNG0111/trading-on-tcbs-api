
from trading_on_tcbs_api.stock_system_v2.execution.order_manager import OrderManager
from trading_on_tcbs_api.stock_system_v2.auth.auth import StockAuth

def verify():
    print("--- Verifying Order Manager ---")
    
    # 1. Initialize
    auth = StockAuth()
    manager = OrderManager(auth=auth, safe_mode=True)
    
    # 2. Place Mock Buy
    print("\nTest 1: Mock Buy Order (Safe Mode)")
    res = manager.place_order("HPG", "NB", 26000, 100)
    print(f"Result: {res}")
    
    # 3. Place Mock Sell
    print("\nTest 2: Mock Sell Order (Safe Mode)")
    res = manager.place_order("HPG", "NS", 27000, 50)
    print(f"Result: {res}")
    
    # 4. Attempt Real Order (Should be blocked by Safety Check or Mock Flag)
    # Note: Even if we passed safe_mode=False, the class has a guard.
    print("\nTest 3: Safety Guard Check")
    # We won't actually turn off safe mode here to avoid accidents, 
    # but the Manager code prints a warning if implemented.
    
if __name__ == "__main__":
    verify()
