import asyncio
from trading_on_tcbs_api.stock_system_v2.finance.account_manager import AccountManager

async def test_live_sync():
    print("--- Testing Live Sync ---")
    manager = AccountManager(mock_mode=False)
    await manager.sync_from_api()
    
    print("\n[Final Account State]")
    print(f"Cash Balance:   {manager.get_balance():,.0f} VND")
    print(f"Buying Power:   {manager.get_buying_power_amount():,.0f} VND")
    print(f"Open Positions: {manager.get_positions()}")
    print(f"Sync Status:    {manager.last_sync_status}")

if __name__ == "__main__":
    asyncio.run(test_live_sync())
