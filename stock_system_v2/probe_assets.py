
import requests
import json
from trading_on_tcbs_api.stock_system_v2.auth import StockAuth
from trading_on_tcbs_api.stock_system_v2 import config

def probe_assets():
    print("--- Probing TCBS Asset APIs ---")
    
    auth = StockAuth()
    if not auth.validate():
        print("Auth failed.")
        return

    headers = {
        "Authorization": f"Bearer {auth.token}",
        "Content-Type": "application/json"
    }
    
    # 1. Get User Info / Accounts
    # Endpoint often: /v1/account or similar. 
    # Let's try to find account info from the User Info endpoint if known, 
    # or just try the common integration endpoints.
    
    # TCBS Open API docs usually suggest:
    # /rm/v1/account (Relationship Management)
    # /equity/v1/account (Equity Account)
    
    endpoints = [
        # Common TCBS Endpoints to try
        "/rm/v1/account/info", 
        "/equity/v1/account/iica", # Recurring account info
        "/equity/v1/account/data",
        "/wealth/v1/account/assets",
        "/integration/v1/account/balance" 
    ]
    
    # Note: TCBS API structure is complex. 
    # Let's try a known one for assets if possible, or search for 'assets' in known docs.
    # Ref: `probe_vnstock.py` or similar might have clues.
    # For now, I will try a very standard one for TCBS which is often related to 'rm' or 'equity'.
    
    # Let's try getting the sub-account list first
    print("\n[1] Fetching Account List...")
    url_accounts = f"{config.BASE_URL}/rm/v1/customer/accounts" # Guessing standard path
    
    # Actually, let's look at the JWT token, it often contains the account number!
    # I'll print the token payload (decoded) to see if it lists account IDs.
    print("\n[0] Inspecting Token Claims...")
    try:
        # Simple decode without verification just to read payload
        import base64
        parts = auth.token.split(".")
        if len(parts) > 1:
            padding = '=' * (4 - len(parts[1]) % 4)
            payload = json.loads(base64.b64decode(parts[1] + padding).decode('utf-8'))
            print(f"Token Payload Keys: {list(payload.keys())}")
            if 'custodyID' in payload:
                print(f"Custody ID: {payload['custodyID']}")
            if 'sub' in payload:
                 print(f"Sub: {payload['sub']}")
    except Exception as e:
        print(f"Error decoding token: {e}")

    # 2. Try to fetch Assets using API Key
    # We might need to use the Wealth or Equity API. 
    
    # Let's try: /api/v1/account/assets (Generic)
    print("\n[2] Probing potential Asset endpoints...")
    
    # 2. Direct Asset Fetching using Configured Account
    print("\n[2] Fetching Portfolio Data (Direct Mode)...")
    
    # Try getting account from config or token
    # From credentials.yaml, let's use the custody code as base or try the known sub-account format
    # The spec examples use "0001..." format which matches the 'sub' claim in the token!
    
    target_accounts = []
    
    # 1. Try Token 'sub' (e.g. 0001514946)
    try:
        import base64
        parts = auth.token.split(".")
        if len(parts) > 1:
            padding = '=' * (4 - len(parts[1]) % 4)
            payload = json.loads(base64.b64decode(parts[1] + padding).decode('utf-8'))
            if 'sub' in payload:
                target_accounts.append(payload['sub'])
                print(f"    Found Account from Token: {payload['sub']}")
    except:
        pass
        
    # 3. Try Config Value from YAML (Most reliable)
    try:
        import yaml
        with open(config.CREDENTIALS_FILE, 'r') as f:
            creds = yaml.safe_load(f)
            # Try sub_account_id first (e.g. 105C...A)
            sub_acc = creds.get('tcbs_api', {}).get('sub_account_id')
            if sub_acc:
                target_accounts.append(sub_acc)
                print(f"    Found Account from Config (Sub): {sub_acc}")
            
            # Also try account_id
            acc_id = creds.get('tcbs_api', {}).get('account_id')
            if acc_id:
                target_accounts.append(acc_id)
                print(f"    Found Account from Config (Main): {acc_id}")
    except Exception as e:
        print(f"    Error reading credentials.yaml: {e}")
        
    # Remove duplicates
    target_accounts = list(set(target_accounts))

    for account_no in target_accounts:
        print(f"\n--- Testing Account: {account_no} ---")
        
        # A. Cash Balance
        url_cash = f"{config.BASE_URL}/aion/v1/accounts/{account_no}/cashInvestments"
        print(f"--> GET {url_cash}")
        resp_cash = requests.get(url_cash, headers=headers, timeout=10)
        if resp_cash.status_code == 200:
             print(f"    SUCCESS! Cash Data:")
             print(json.dumps(resp_cash.json(), indent=2))
        else:
             print(f"    Failed ({resp_cash.status_code})")

        # B. Positions (Stocks)
        url_pos = f"{config.BASE_URL}/aion/v1/accounts/{account_no}/se"
        print(f"--> GET {url_pos}")
        resp_pos = requests.get(url_pos, headers=headers, timeout=10)
        if resp_pos.status_code == 200:
             print(f"    SUCCESS! Positions Data:")
             print(json.dumps(resp_pos.json(), indent=2))
        else:
             print(f"    Failed ({resp_pos.status_code})")
             
        # C. Purchasing Power
        url_power = f"{config.BASE_URL}/aion/v1/accounts/{account_no}/ppse"
        print(f"--> GET {url_power}")
        resp_power = requests.get(url_power, headers=headers, timeout=10)
        if resp_power.status_code == 200:
             print(f"    SUCCESS! Purchasing Power:")
             print(json.dumps(resp_power.json(), indent=2))
        else:
             print(f"    Failed ({resp_power.status_code})")

    # 4. Try Customer Level Endpoints (to find valid accounts)
    print("\n[4] Probing Customer API...")
    custody_id = "105C514946" # From credentials/token
    
    url_cust = f"{config.BASE_URL}/aion/v1/customers/{custody_id}/accounts"
    print(f"--> GET {url_cust}")
    try:
        resp = requests.get(url_cust, headers=headers, timeout=10)
        if resp.status_code == 200:
             print(f"    SUCCESS! Account List:")
             print(json.dumps(resp.json(), indent=2))
        else:
             print(f"    Failed ({resp.status_code}) - {resp.text}")
    except Exception as e:
        print(f"    Exception: {e}")

    # 5. The "Guide" Approach: Profile First
    print("\n[5] Fetching Profile (Eros API)...")
    
    candidates_custody = ["105C514946", "0001514946"]
    
    for custody_id in candidates_custody:
        print(f"\n--- Profile for {custody_id} ---")
        url_profile = f"{config.BASE_URL}/eros/v2/get-profile/by-username/{custody_id}"
        params = {"fields": "basicInfo,personalInfo,bankSubAccounts,bankAccounts"}
        
        print(f"--> GET {url_profile}")
        try:
            resp = requests.get(url_profile, headers=headers, params=params, timeout=10)
            
            if resp.status_code == 200:
                 data = resp.json()
                 print(f"    SUCCESS! Profile Data (Keys): {list(data.keys())}")
                 if 'bankSubAccounts' in data:
                     subs = data['bankSubAccounts']
                     print(f"    Sub Accounts: {subs}")
            else:
                 print(f"    Failed ({resp.status_code}) - {resp.text}")
                 
        except Exception as e:
            print(f"    Exception: {e}")

if __name__ == "__main__":
    probe_assets()
