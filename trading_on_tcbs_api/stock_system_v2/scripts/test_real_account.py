
import asyncio
import sys
import os

# Ensure path is correct
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from trading_on_tcbs_api.stock_system_v2.finance.account_manager import AccountManager

async def test_account_sync():
    print("--- TESTING ACCOUNT MANAGER SYNC ---")
    
    # 1. Init in Mock Mode
    am = AccountManager(initial_cash=100_000_000)
    print(f"Initial State: Cash={am.get_balance()}, Power={am.get_buying_power_amount()}, Pos={am.get_positions()}")
    
    # 2. Sync from API
    await am.sync_from_api()
    
    # 3. Check State
    print(f"\nPost-Sync State: ({am.last_sync_status})")
    print(f"Cash: {am.cash:,.0f}")
    print(f"Power: {am.get_buying_power_amount():,.0f}")
    print(f"Positions: {am.get_positions()}")
    
    if am.last_sync_status.startswith("Mock"):
        print("\n[INFO] System correctly fell back to Mock because API returned empty/failed (Expected result for current token).")
    else:
        print("\n[SUCCESS] System synced with Real Data!")

if __name__ == "__main__":
    asyncio.run(test_account_sync())
