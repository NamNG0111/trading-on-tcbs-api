
import asyncio
import json
import requests
import sys
import os

# Ensure path is correct
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from stock_system_v2.auth import StockAuth
from stock_system_v2 import config
from trading_on_tcbs_api.utils.config_manager import get_config_manager
from pathlib import Path

def probe_profile():
    print("--- PROBING PROFILE ENDPOINT (/eros/v2) ---")
    
    # 1. Auth exhaustively
    auth = StockAuth()
    if not auth.validate():
        print("Auth failed.")
        return

    # 2. Get Candidates
    cm = get_config_manager()
    cm.config_dir = Path(os.path.join(config.BASE_DIR, "config"))
    creds = cm.load_credentials()
    
    candidates = [
        creds.custody_code,          # "105C..." matches spec example
        creds.api_key.split('-')[0], # "0001..." usually the username/sub
    ]
    # Remove duplicates
    candidates = list(dict.fromkeys(candidates))
    
    print(f"Candidates to probe: {candidates}")
    
    # 3. Probe loop
    success_data = None
    
    for user_id in candidates:
        print(f"\n>> Trying username/custodyCode: {user_id}")
        
        # Combinations of fields to try. Maybe 'bankSubAccounts' triggers the 403?
        field_combos = [
            "basicInfo,personalInfo,bankSubAccounts,bankAccounts", # Full
            "basicInfo,personalInfo",                              # Public-ish
            "basicInfo",                                           # Minimal
            "bankSubAccounts"                                      # Target
        ]
        
        url = f"{config.BASE_URL}/eros/v2/get-profile/by-username/{user_id}"
        headers = {
            "Authorization": f"Bearer {auth.token}",
            "Content-Type": "application/json"
        }
        
        for fields in field_combos:
            params = {"fields": fields}
            try:
                print(f"   Requesting fields: [{fields[:20]}...]")
                resp = requests.get(url, headers=headers, params=params, timeout=10)
                
                if resp.status_code == 200:
                    print(f"   SUCCESS (200)! Data keys: {list(resp.json().keys())}")
                    success_data = resp.json()
                    break # Found valid data for this user
                else:
                    print(f"   Failed: {resp.status_code} - {resp.text}")
                    
            except Exception as e:
                print(f"   Exception: {e}")
                
        if success_data:
            break
            
    # 4. Save if found
    if success_data:
        file_path = os.path.join(config.BASE_DIR, "config", "profile.json")
        with open(file_path, "w") as f:
            json.dump(success_data, f, indent=4)
        print(f"\n[SUCCESS] Profile saved to {file_path}")
        print(json.dumps(success_data, indent=2))
    else:
        print("\n[FAILURE] Could not retrieve profile with any combo.")

if __name__ == "__main__":
    probe_profile()
