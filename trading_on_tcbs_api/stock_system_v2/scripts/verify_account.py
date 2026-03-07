
from trading_on_tcbs_api.stock_system_v2.finance.account_manager import AccountManager
from trading_on_tcbs_api.stock_system_v2.execution.order_tracker import OrderTracker
import pandas as pd
import os

def verify():
    print("--- Verifying Financial Core (Wallet & Ledger) ---")
    
    # 1. Setup
    account = AccountManager(initial_cash=5_000_000) # 5M VND
    tracker = OrderTracker()
    
    print(f"Initial: {account.get_balance():,.0f} VND | Pos: {account.get_positions()}")
    
    # 2. Simulate Trade Details
    symbol = "HPG"
    price = 26000
    volume = 100
    side = "BUY"
    cost = price * volume
    
    print(f"\n[Action] Simulating BUY {volume} {symbol} @ {price:,.0f} (Total: {cost:,.0f})")
    
    # 3. Check Power
    if account.check_buying_power(cost):
        print(" -> Buying Power: OK")
        
        # 4. Simulate Order Result (Success)
        mock_result = {
            "status": "success",
            "order_id": "test_123456",
            "note": "Unit Test Order"
        }
        
        # 5. Update Components
        tracker.log_order(mock_result, symbol, side, price, volume)
        account.update_after_trade(side, symbol, price, volume)
        
        # 6. Verify Post-State
        print(f"\nFinal: {account.get_balance():,.0f} VND | Pos: {account.get_positions()}")
        
        expected_cash = 5_000_000 - cost
        if account.get_balance() == expected_cash:
            print("SUCCESS: Cash updated correctly.")
        else:
            print(f"FAILURE: Expected {expected_cash}, got {account.get_balance()}")
            
        if account.get_positions().get(symbol) == volume:
             print("SUCCESS: Position updated correctly.")
        else:
             print("FAILURE: Position incorrect.")
             
        # 7. Check Ledger
        print("\n[Ledger Check]")
        df = tracker.get_history()
        print(df.tail(1).to_string())
        if not df.empty and df.iloc[-1]['order_id'] == 'test_123456':
             print("SUCCESS: Trade logged to CSV.")
        else:
             print("FAILURE: Trade not found in ledger.")
             
    else:
        print("FAILURE: Not enough buying power (unexpected).")

if __name__ == "__main__":
    verify()
