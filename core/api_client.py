"""
Refactored TCBS API client with unified structure
"""
import requests
import aiohttp
import asyncio
from typing import Dict, List, Optional, Any
from trading_on_tcbs_api.utils.token_manager import TokenManager


class TCBSClient:
    """Unified TCBS API client with improved error handling and structure"""
    
    def __init__(self, token_file: str = 'config/token.json'):
        # Load credentials from secure configuration
        from trading_on_tcbs_api.utils.config_manager import load_credentials
        credentials = load_credentials()
        
        self.apiKey = credentials.api_key
        self.custody_code = credentials.custody_code
        self.accountId = credentials.account_id
        self.subAccountId = credentials.sub_account_id
        self.base_url = credentials.base_url
        
        self.token_manager = TokenManager(token_file)
        self.token: Optional[str] = None
        
    def initialize_token(self, prompt_otp: bool = True) -> bool:
        """
        Initialize and validate token
        
        Args:
            prompt_otp: Whether to prompt for OTP if token is expired
            
        Returns:
            True if token is valid and ready to use
        """
        self.token = self.token_manager.get_valid_token(self, prompt_otp)
        return self.token is not None
    
    def get_token(self, otp: str) -> Optional[str]:
        """
        Get new token using OTP
        
        Args:
            otp: One-time password
            
        Returns:
            JWT token if successful, None otherwise
        """
        url = f"{self.base_url}/gaia/v1/oauth2/openapi/token"
        payload = {
            "otp": otp,
            "apiKey": self.apiKey
        }
        headers = {
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers)
            if response.status_code == 200:
                jwt_token = response.json()['token']
                self.token = jwt_token
                return jwt_token
            else:
                print(f"Error getting JWT Token: {response.status_code}, {response.text}")
                return None
        except Exception as e:
            print(f"Exception getting token: {e}")
            return None

    def account(self, field: str = "basicInfo,personalInfo,bankSubAccounts,bankAccounts") -> Optional[Dict]:
        """
        Get account information
        
        Args:
            field: Fields to retrieve
            
        Returns:
            Account data or None if error
        """
        url = f"{self.base_url}/gaia/v1/derivative/info/file/by-username/{self.custody_code}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        params = {"field": field}
        
        try:
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Error getting account info: {response.status_code}, {response.text}")
                return None
        except Exception as e:
            print(f"Exception getting account info: {e}")
            return None

    async def place_order(self, symbol: str, side: str, volume: int, price: float, orderType: str = "L0") -> Optional[Dict]:
        """
        Place derivative order asynchronously
        
        Args:
            symbol: Trading symbol
            side: 'B' for buy, 'S' for sell
            volume: Order quantity
            price: Order price
            orderType: Order type
            
        Returns:
            Order response data or None if error
        """
        url = f"{self.base_url}/khronos/v1/order/place"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        payload = {
            'accountId': self.accountId,
            'subAccountId': self.subAccountId,
            'side': side,
            'symbol': symbol,
            'price': price,
            'volume': volume,
            'advance': "",
            'refId': "H.OWsC4418qYN5142cvGtD3z",
            'orderType': orderType,
            'pin': "H"
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    data = await resp.json()
                    if resp.status == 200:
                        return data.get("data", [{}])[0]
                    else:
                        print(f"Order placement error: {data}")
                        resp.raise_for_status()
        except Exception as e:
            print(f"Exception placing order: {e}")
            return None

    async def change_order(self, orderNo: str, nvol: int, nprice: float) -> Optional[Dict]:
        """
        Modify existing order
        
        Args:
            orderNo: Order number to modify
            nvol: New volume
            nprice: New price
            
        Returns:
            Modification response or None if error
        """
        url = f"{self.base_url}/khronos/v1/order/change"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        payload = {
            'accountId': self.accountId,
            'subAccountId': self.subAccountId,
            'orderNo': orderNo,
            'refId': "000123.H.HH2104062128",
            'nvol': nvol,
            'nprice': nprice
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    data = await resp.json()
                    if resp.status == 200:
                        return data.get("data", [{}])[0]
                    else:
                        print(f"Order change error: {data}")
                        return None
        except Exception as e:
            print(f"Exception changing order: {e}")
            return None

    async def cancel_order(self, orderNo: str) -> Optional[Dict]:
        """
        Cancel existing order
        
        Args:
            orderNo: Order number to cancel
            
        Returns:
            Cancellation response or None if error
        """
        url = f"{self.base_url}/khronos/v1/order/cancel"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        payload = {
            'accountId': self.accountId,
            'orderNo': orderNo,
            'cmd': "Web.cancelOrder"
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    data = await resp.json()
                    if resp.status == 200:
                        print(f"Order cancelling...")
                        return data.get("data", [{}])[0]
                    else:
                        print(f"Order cancel error: {data}")
                        return None
        except Exception as e:
            print(f"Exception cancelling order: {e}")
            return None

    def order_list(self, symbol: str = "ALL", side: str = 'ALL', orderType: int = 6, 
                   pageNo: int = 1, pageSize: int = 20, status: int = 0) -> Optional[List[Dict]]:
        """
        Get order list with filters
        
        Args:
            symbol: Symbol filter
            side: Side filter
            orderType: Order type filter
            pageNo: Page number
            pageSize: Page size
            status: Status filter
            
        Returns:
            List of orders or None if error
        """
        url = f"{self.base_url}/khronos/v1/order/modify"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        params = {
            'pageNo': pageNo,
            'pageSize': pageSize,
            'accountId': self.accountId,
            'symbol': f"{symbol},{side}",
            'orderType': orderType,
            'status': status
        }

        try:
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 200:
                return response.json()["data"]
            else:
                print(f"Order list error: {response.status_code}")
                response.raise_for_status()
        except Exception as e:
            print(f"Exception getting order list: {e}")
            return None

    def get_open_positions_derivative(self) -> Optional[Dict]:
        """
        Get current derivative positions
        
        Returns:
            Position data or None if error
        """
        url = f"{self.base_url}/khronos/v1/account/portfolio/status"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        params = {
            'accountId': self.accountId,
            'subAccountId': self.subAccountId
        }

        try:
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 200:
                return response.json()["data"]
            else:
                print(f"Position error: {response.status_code}")
                return None
        except Exception as e:
            print(f"Exception getting positions: {e}")
            return None

    def get_derivative_info(self, tickers: List[str]) -> Optional[List[Dict]]:
        """
        Get derivative instrument information
        
        Args:
            tickers: List of ticker symbols
            
        Returns:
            Derivative info or None if error
        """
        url = f"{self.base_url}/gaia/v1/oauth2/openapi/refresh"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        params = {'tickers': ','.join(tickers)}
        
        try:
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 200:
                return response.json()["data"]
            else:
                print(f"Derivative info error: {response.status_code}")
                return None
        except Exception as e:
            print(f"Exception getting derivative info: {e}")
            return None

    def get_stock_info(self, tickers: List[str]) -> Optional[List[Dict]]:
        """
        Get stock information
        
        Args:
            tickers: List of ticker symbols
            
        Returns:
            Stock info or None if error
        """
        url = f"{self.base_url}/tartarus/v1/tickerCommons"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        params = {'tickers': ','.join(tickers)}
        
        try:
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 200:
                return response.json()["data"]
            else:
                print(f"Stock info error: {response.status_code}")
                return None
        except Exception as e:
            print(f"Exception getting stock info: {e}")
            return None
