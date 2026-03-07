
import asyncio
import json
import sys
import os

# Ensure path is correct
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from stock_system_v2.auth import StockAuth
from trading_on_tcbs_api.stock_strategy.stock_api_client import StockTradingClient
from stock_system_v2 import config

async def fetch_real_assets():
    print("--- FETCHING REAL ASSETS (Using StockTradingClient) ---")
    
    # 1. Auth
    auth = StockAuth()
    if not auth.validate():
        print("Auth failed.")
        return

    # 2. Init Client
    # Set up ConfigManager to find credentials correctly from root
    from utils.config_manager import get_config_manager
    from pathlib import Path
    
    cm = get_config_manager()
    cm.config_dir = Path(os.path.join(config.BASE_DIR, "config"))
    
    # We pass the token we just validated
    client = StockTradingClient(token_file=config.TOKEN_FILE)
    # Force reload token in client just in case
    client.token = auth.token
    
    print("\n[1] Getting Account Info...")
    try:
        # This calls /akhlys/v1/accounts
        accounts = await client.get_account_info()
        print(f"Accounts Found: {len(accounts)}")
        print(json.dumps(accounts, indent=2))
        
        if not accounts:
            print("No accounts returned from API. Using config IDs...")
            
        # Get Credentials
        creds = cm.load_credentials()
        
        # Define accounts to probe
        target_accounts = []
        
        # 1. Normal + Margin (Stock)
        stock_accounts = []
        if creds.normal_sub_account_id:
            stock_accounts.append({"id": creds.normal_sub_account_id, "type": "Normal"})
        if creds.margin_sub_account_id:
            stock_accounts.append({"id": creds.margin_sub_account_id, "type": "Margin"})
            
        # Fallback if new keys missing
        if not stock_accounts and creds.sub_account_id:
             stock_accounts.append({"id": creds.sub_account_id, "type": "Default"})

        # 2. Futures
        futures_accounts = []
        if creds.futures_sub_account_id:
            futures_accounts.append({"id": creds.futures_sub_account_id, "type": "Futures"})

        # --- PROCESS STOCK ASSETS (Aggregated) ---
        print("\n=== STOCK PORTFOLIO (Aggregated) ===")
        total_stock_value = 0
        total_cash_stock = 0
        all_positions = []
        
        for acc in stock_accounts:
            acc_id = acc['id']
            acc_type = acc['type']
            print(f"\n>> Probing {acc_type} Account: {acc_id}")
            client.account_no = acc_id
            
            # Cash
            try:
                cash = await client.get_cash_balance()
                # Determine cash value (field verification needed, assuming 'purchasingPower' or 'cashBalance')
                # For now print raw
                print(f"   [Cash] {cash}")
                # total_cash_stock += ... (Need actual field name from successful resp)
            except Exception as e:
                print(f"   [Cash] Error: {e}")

            # Positions
            try:
                positions = await client.get_stock_positions()
                if positions:
                    print(f"   [Positions] Found {len(positions)} items")
                    all_positions.extend(positions)
                else:
                    print("   [Positions] None")
            except Exception as e:
                print(f"   [Positions] Error: {e}")

            # Buying Power
            try:
                pp = await client.get_buying_power()
                print(f"   [Power] {pp}")
            except Exception as e:
                 print(f"   [Power] Error: {e}")

        # --- PROCESS FUTURES ASSETS ---
        if futures_accounts:
            print("\n=== FUTURES PORTFOLIO ===")
            for acc in futures_accounts:
                acc_id = acc['id']
                print(f"\n>> Probing Futures Account: {acc_id}")
                client.account_no = acc_id
                # Use derivative endpoints if available, or standard assets
                # StockTradingClient might not have futures endpoints.
                # Just probing standard assets for now.
                try: 
                    cash = await client.get_cash_balance()
                    print(f"   [Cash] {cash}")
                except: pass

        return # End of new logic
        
        # Old loop removed
        for acc in accounts:
            
            # Update client's active account context
            client.account_no = acc_no
            
            # A. Cash
            print("  Fetching Cash...")
            try:
                cash = await client.get_cash_balance()
                print(f"  Cash Data: {json.dumps(cash, indent=2)}")
            except Exception as e:
                print(f"  Error fetching cash: {e}")

            # B. Stocks
            print("  Fetching Positions...")
            try:
                positions = await client.get_stock_positions()
                print(f"  Positions: {json.dumps(positions, indent=2)}")
            except Exception as e:
                print(f"  Error fetching positions: {e}")

            # C. Purchasing Power
            print("  Fetching Buying Power...")
            try:
                pp = await client.get_buying_power()
                print(f"  Buying Power: {json.dumps(pp, indent=2)}")
            except Exception as e:
                print(f"  Error fetching power: {e}")
                
    except Exception as e:
        print(f"Critical Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(fetch_real_assets())
