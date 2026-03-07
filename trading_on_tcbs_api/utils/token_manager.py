"""
Unified token management for TCBS API authentication
"""
import json
import datetime
from typing import Optional


class TokenManager:
    """Manages TCBS API token authentication and renewal"""
    
    def __init__(self, token_file: str = 'config/token.json'):
        self.token_file = token_file
        self.token: Optional[str] = None
        
    def load_token(self) -> Optional[str]:
        """
        Load and validate token from file
        
        Returns:
            Valid token string or None if expired/invalid
        """
        try:
            with open(self.token_file, 'r') as f:
                data = json.load(f)
                token_expire_date = datetime.datetime.strptime(data['expire'], "%Y-%m-%d").date()
                today = datetime.datetime.today().date()
                
                if today <= token_expire_date:
                    self.token = data["token"]
                    return self.token
                else:
                    print("Token expired, renewal required")
                    return None
        except (FileNotFoundError, KeyError, ValueError) as e:
            print(f"Error loading token: {e}")
            return None
    
    def save_token(self, token: str, expire_date: Optional[datetime.date] = None) -> bool:
        """
        Save token to file
        
        Args:
            token: JWT token string
            expire_date: Token expiration date (defaults to today)
            
        Returns:
            True if saved successfully
        """
        try:
            if expire_date is None:
                expire_date = datetime.datetime.today().date()
                
            token_data = {
                "token": token,
                "expire": expire_date.strftime("%Y-%m-%d")
            }
            
            with open(self.token_file, "w") as f:
                json.dump(token_data, f, indent=4)
                
            self.token = token
            return True
        except Exception as e:
            print(f"Error saving token: {e}")
            return False
    
    def renew_token(self, client, otp: str) -> bool:
        """
        Renew token using OTP
        
        Args:
            client: TCBS client instance
            otp: One-time password
            
        Returns:
            True if renewal successful
        """
        try:
            new_token = client.get_token(otp)
            if new_token:
                return self.save_token(new_token)
            return False
        except Exception as e:
            print(f"Error renewing token: {e}")
            return False
    
    def get_valid_token(self, client, prompt_otp: bool = True) -> Optional[str]:
        """
        Get a valid token, renewing if necessary
        
        Args:
            client: TCBS client instance
            prompt_otp: Whether to prompt for OTP if token is expired
            
        Returns:
            Valid token or None
        """
        token = self.load_token()
        
        if token is None and prompt_otp:
            otp = input("Token expired. Enter OTP: ")
            if self.renew_token(client, otp):
                return self.token
            else:
                print("Failed to renew token with provided OTP")
                return None
        
        return token
    
    def is_token_valid(self) -> bool:
        """
        Check if current token is valid (not expired)
        
        Returns:
            True if token is valid
        """
        return self.load_token() is not None
