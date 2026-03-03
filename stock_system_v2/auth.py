import json
import datetime
import os
import requests
import yaml
from typing import Optional

from . import config

class StockAuth:
    """
    Independent authentication handler for the stock system.
    Supports loading shared token and renewing it via OTP if expired.
    """
    
    def __init__(self):
        self.token_file = config.TOKEN_FILE
        self.credentials_file = config.CREDENTIALS_FILE
        self.token: Optional[str] = None
        self.api_key: Optional[str] = None
        
        self._load_credentials()
        
    def _load_credentials(self):
        """Load API Key from credentials.yaml"""
        if os.path.exists(self.credentials_file):
            try:
                with open(self.credentials_file, 'r') as f:
                    creds = yaml.safe_load(f)
                    self.api_key = creds.get('tcbs_api', {}).get('api_key')
            except Exception as e:
                print(f"[Auth] Error loading credentials: {e}")
        else:
            print(f"[Auth] Credentials file not found at {self.credentials_file}")

    def load_token(self) -> Optional[str]:
        """
        Load token from the configured file.
        Returns the token if valid (not expired), else None.
        """
        if not os.path.exists(self.token_file):
            return None
            
        try:
            with open(self.token_file, 'r') as f:
                data = json.load(f)
                
            # Check expiration
            expire_str = data.get('expire')
            if not expire_str:
                return None
            
            # Helper to parse date
            expire_date = datetime.datetime.strptime(expire_str, "%Y-%m-%d").date()
            # Stricter check: If today == expire_date, we consider it expired (or expiring today)
            # requiring a fresh token for the new trading day.
            if datetime.datetime.today().date() < expire_date:
                self.token = data.get('token')
                return self.token
            else:
                print(f"[Auth] Token expired on {expire_date} (Today: {datetime.datetime.today().date()})")
                return None
                
        except Exception as e:
            print(f"[Auth] Error loading token: {e}")
            return None

    def save_token(self, token: str) -> bool:
        """
        Save the token to file.
        """
        try:
            # We assume the token is valid for 1 day if freshly retrieved, 
            # OR we should parse the JWT to find exp, but for now 1 day is adding safely.
            # Ideally, the API response might give expiry or we set it.
            # The old system hardcodes it or just saves passed date.
            
            expire_date = (datetime.datetime.today() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
            
            data = {
                "token": token,
                "expire": expire_date
            }
            
            with open(self.token_file, 'w') as f:
                json.dump(data, f, indent=4)
                
            self.token = token
            print(f"[Auth] New token saved to {self.token_file}")
            return True
        except Exception as e:
            print(f"[Auth] Error saving token: {e}")
            return False

    def renew_token(self, otp: str) -> bool:
        """
        Renew token using OTP and API Key.
        """
        if not self.api_key:
            print("[Auth] Cannot renew token: API Key missing.")
            return False
            
        url = f"{config.BASE_URL}/gaia/v1/oauth2/openapi/token"
        payload = {
            "otp": otp,
            "apiKey": self.api_key
        }
        headers = {
            "Content-Type": "application/json"
        }
        
        try:
            print(f"[Auth] Requesting new token...")
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                new_token = data.get('token')
                if new_token:
                    return self.save_token(new_token)
                else:
                    print(f"[Auth] Token response missing 'token' field: {data}")
                    return False
            else:
                print(f"[Auth] Token renewal failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"[Auth] Exception during token renewal: {e}")
            return False

    def _check_api_validity(self, token: str) -> bool:
        """
        Actively probe the API to see if the token is accepted.
        File expiration date is not enough because the server might kill sessions.
        """
        try:
            # Use a lightweight public endpoint that requires auth, or a low-cost one.
            # Tartarus tickerCommons is good because it needs 'stock' scope which we have.
            url = f"{config.BASE_URL}/tartarus/v1/tickerCommons"
            params = {'tickers': "TCB"} # Check a random symbol
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            # Timeout fast for this check
            response = requests.get(url, headers=headers, params=params, timeout=5)
            
            if response.status_code == 200:
                return True
            elif response.status_code in [401, 403]:
                print(f"[Auth] Token rejected by API (Status: {response.status_code})")
                return False
            else:
                # Other errors (500, 404) might be API issues, not auth. 
                # Assume valid to avoid spamming OTP on backend errors.
                return True 
                
        except Exception as e:
            # Network error? Assume valid to be safe, don't block offline mode if logic allows
            print(f"[Auth] Warning: Could not verify token with API: {e}")
            return True

    def validate(self) -> bool:
        """
        Check if we have a valid token. If not, prompt user for OTP to renew.
        Now includes ACTIVE API check.
        """
        token = self.load_token()
        is_valid = False
        
        if token:
             # Basic date check passed (in load_token), now check API
             if self._check_api_validity(token):
                 print("[Auth] Valid token loaded & verified with API.")
                 return True
             else:
                 print("[Auth] Token file is fresh but API rejected it. Forcing renewal.")
        else:
             print("[Auth] Token is invalid or expired (Date Check).")

        if not self.api_key:
             print("❌ API Key not found in config/credentials.yaml. Cannot auto-renew.")
             return False

        # Prompt for OTP
        otp_input = input(f"Please enter OTP to renew token (using API Key ending in ...{self.api_key[-4:] if self.api_key else '????'}): ").strip()
        if otp_input:
            if self.renew_token(otp_input):
                 return True
        
        return False
