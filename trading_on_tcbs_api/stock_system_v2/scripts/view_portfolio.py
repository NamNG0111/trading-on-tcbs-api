import asyncio
import os
import sys
from tabulate import tabulate


from trading_on_tcbs_api.stock_system_v2.finance.account_manager import AccountManager

async def view_portfolio():
    print("=" * 60)
    print("                TCBS ASSET PORTFOLIO")
    print("=" * 60)
    print(">> Syncing data from TCBS API...")
    
    manager = AccountManager(mock_mode=False)
    await manager.sync_from_api()
    
    if manager.last_sync_status != "Real (Synced)":
        print("\n[!] Failed to sync real data. Used Mock values instead.")
        return

    print("\n--- AGGREGATED ACCOUNT SUMMARY ---")
    summary_data = [
        ["Total Cash Balance (VND)", f"{manager.get_balance():,.0f}"],
        ["Total Purchasing Power (VND)", f"{manager.get_buying_power_amount():,.0f}"]
    ]
    print(tabulate(summary_data, tablefmt="plain", colalign=("left", "right")))
    
    print("\n--- OPEN SECURITY POSITIONS ---")
    positions = manager.get_positions()
    if positions:
        pos_data = [[sym, qty] for sym, qty in positions.items()]
        print(tabulate(pos_data, headers=["Symbol", "Quantity (Shares)"], tablefmt="heavy_grid", colalign=("left", "right")))
    else:
        print("No open positions found.")
    
    print("=" * 60)

if __name__ == "__main__":
    try:
        asyncio.run(view_portfolio())
    except KeyboardInterrupt:
        print("\nOperation cancelled.")
