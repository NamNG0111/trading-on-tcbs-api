"""
Extended TCBS API client for stock trading operations
"""
import requests
import json
from typing import Dict, List, Optional, Union, Any
from datetime import datetime
import asyncio

from trading_on_tcbs_api.core.api_client import TCBSClient
from trading_on_tcbs_api.logger_utils.fast_logger import get_logger


class StockTradingClient(TCBSClient):
    """Extended TCBS client specifically for stock trading operations"""
    
    def __init__(self, token_file: str = 'config/token.json'):
        super().__init__(token_file=token_file)
        self.logger = get_logger('stock_trading', 'Stock Trading')
        self.account_no = None  # Will be set after login
        
    async def initialize_stock_trading(self, account_no: str = None):
        """Initialize stock trading with account information"""
        await super().initialize_token()
        
        if account_no:
            self.account_no = account_no
        else:
            # Get account information
            accounts = await self.get_account_info()
            if accounts:
                self.account_no = accounts[0].get('accountNo')
        
        await self.logger.log(f"Initialized stock trading for account: {self.account_no}")
    
    async def get_account_info(self) -> List[Dict[str, Any]]:
        """Get account information"""
        try:
            response = await asyncio.to_thread(
                requests.get,
                f"{self.base_url}/akhlys/v1/accounts",
                headers=self.headers
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get('data', [])
            else:
                await self.logger.log_error(f"Failed to get account info: {response.status_code}")
                return []
                
        except Exception as e:
            await self.logger.log_error(f"Error getting account info: {e}")
            return []
    
    async def place_stock_order(self, symbol: str, side: str, quantity: int, 
                               price: float, order_type: str = "LO") -> Optional[str]:
        """
        Place stock order
        
        Args:
            symbol: Stock symbol
            side: 'BUY' or 'SELL'
            quantity: Order quantity
            price: Order price
            order_type: Order type ('LO' for limit, 'MP' for market)
            
        Returns:
            Order ID if successful
        """
        if not self.account_no:
            await self.logger.log_error("Account number not set")
            return None
            
        try:
            order_data = {
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "price": price,
                "orderType": order_type,
                "timeInForce": "DAY"  # Day order
            }
            
            response = await asyncio.to_thread(
                requests.post,
                f"{self.base_url}/akhlys/v1/accounts/{self.account_no}/orders",
                headers=self.headers,
                json=order_data
            )
            
            if response.status_code == 200:
                result = response.json()
                order_id = result.get('data', {}).get('orderId')
                await self.logger.log(f"Stock order placed: {order_id} - {side} {quantity} {symbol} @ {price}")
                return order_id
            else:
                await self.logger.log_error(f"Failed to place stock order: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            await self.logger.log_error(f"Error placing stock order: {e}")
            return None
    
    async def modify_stock_order(self, order_id: str, new_price: float = None, 
                                new_quantity: int = None) -> bool:
        """
        Modify existing stock order
        
        Args:
            order_id: Order ID to modify
            new_price: New price (optional)
            new_quantity: New quantity (optional)
            
        Returns:
            True if successful
        """
        if not self.account_no:
            await self.logger.log_error("Account number not set")
            return False
            
        try:
            modify_data = {}
            if new_price is not None:
                modify_data["price"] = new_price
            if new_quantity is not None:
                modify_data["quantity"] = new_quantity
            
            if not modify_data:
                await self.logger.log_error("No modification parameters provided")
                return False
            
            response = await asyncio.to_thread(
                requests.put,
                f"{self.base_url}/akhlys/v1/accounts/{self.account_no}/orders/{order_id}",
                headers=self.headers,
                json=modify_data
            )
            
            if response.status_code == 200:
                await self.logger.log(f"Stock order modified: {order_id}")
                return True
            else:
                await self.logger.log_error(f"Failed to modify stock order: {response.status_code}")
                return False
                
        except Exception as e:
            await self.logger.log_error(f"Error modifying stock order: {e}")
            return False
    
    async def cancel_stock_order(self, order_id: str) -> bool:
        """
        Cancel stock order
        
        Args:
            order_id: Order ID to cancel
            
        Returns:
            True if successful
        """
        if not self.account_no:
            await self.logger.log_error("Account number not set")
            return False
            
        try:
            cancel_data = {"orderIds": [order_id]}
            
            response = await asyncio.to_thread(
                requests.put,
                f"{self.base_url}/akhlys/v1/accounts/{self.account_no}/cancel-orders",
                headers=self.headers,
                json=cancel_data
            )
            
            if response.status_code == 200:
                await self.logger.log(f"Stock order cancelled: {order_id}")
                return True
            else:
                await self.logger.log_error(f"Failed to cancel stock order: {response.status_code}")
                return False
                
        except Exception as e:
            await self.logger.log_error(f"Error cancelling stock order: {e}")
            return False
    
    async def get_stock_orders(self, status: str = None, 
                              from_date: str = None, to_date: str = None) -> List[Dict[str, Any]]:
        """
        Get stock orders
        
        Args:
            status: Order status filter
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
            
        Returns:
            List of orders
        """
        if not self.account_no:
            await self.logger.log_error("Account number not set")
            return []
            
        try:
            params = {}
            if status:
                params["status"] = status
            if from_date:
                params["fromDate"] = from_date
            if to_date:
                params["toDate"] = to_date
            
            response = await asyncio.to_thread(
                requests.get,
                f"{self.base_url}/akhlys/v1/accounts/{self.account_no}/orders",
                headers=self.headers,
                params=params
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get('data', [])
            else:
                await self.logger.log_error(f"Failed to get stock orders: {response.status_code}")
                return []
                
        except Exception as e:
            await self.logger.log_error(f"Error getting stock orders: {e}")
            return []
    
    async def get_stock_positions(self) -> List[Dict[str, Any]]:
        """Get current stock positions"""
        if not self.account_no:
            await self.logger.log_error("Account number not set")
            return []
            
        try:
            response = await asyncio.to_thread(
                requests.get,
                f"{self.base_url}/akhlys/v1/accounts/{self.account_no}/assets/stocks",
                headers=self.headers
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get('data', [])
            else:
                await self.logger.log_error(f"Failed to get stock positions: {response.status_code}")
                return []
                
        except Exception as e:
            await self.logger.log_error(f"Error getting stock positions: {e}")
            return []
    
    async def get_cash_balance(self) -> Dict[str, float]:
        """Get cash balance information"""
        if not self.account_no:
            await self.logger.log_error("Account number not set")
            return {}
            
        try:
            response = await asyncio.to_thread(
                requests.get,
                f"{self.base_url}/akhlys/v1/accounts/{self.account_no}/assets/cash",
                headers=self.headers
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get('data', {})
            else:
                await self.logger.log_error(f"Failed to get cash balance: {response.status_code}")
                return {}
                
        except Exception as e:
            await self.logger.log_error(f"Error getting cash balance: {e}")
            return {}
    
    async def get_buying_power(self, symbol: str = None, price: float = None) -> Dict[str, float]:
        """
        Get buying power information
        
        Args:
            symbol: Stock symbol (optional)
            price: Price for calculation (optional)
            
        Returns:
            Buying power information
        """
        if not self.account_no:
            await self.logger.log_error("Account number not set")
            return {}
            
        try:
            url = f"{self.base_url}/akhlys/v1/accounts/{self.account_no}/purchasing-power"
            params = {}
            
            if symbol:
                params["symbol"] = symbol
            if price:
                params["price"] = price
            
            response = await asyncio.to_thread(
                requests.get,
                url,
                headers=self.headers,
                params=params
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get('data', {})
            else:
                await self.logger.log_error(f"Failed to get buying power: {response.status_code}")
                return {}
                
        except Exception as e:
            await self.logger.log_error(f"Error getting buying power: {e}")
            return {}
    
    async def get_order_matches(self, order_id: str = None) -> List[Dict[str, Any]]:
        """
        Get order execution details
        
        Args:
            order_id: Specific order ID (optional)
            
        Returns:
            List of order matches
        """
        if not self.account_no:
            await self.logger.log_error("Account number not set")
            return []
            
        try:
            if order_id:
                url = f"{self.base_url}/akhlys/v1/accounts/{self.account_no}/orders/{order_id}/matches"
            else:
                url = f"{self.base_url}/akhlys/v1/accounts/{self.account_no}/orders/matches"
            
            response = await asyncio.to_thread(
                requests.get,
                url,
                headers=self.headers
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get('data', [])
            else:
                await self.logger.log_error(f"Failed to get order matches: {response.status_code}")
                return []
                
        except Exception as e:
            await self.logger.log_error(f"Error getting order matches: {e}")
            return []
    
    async def validate_order(self, symbol: str, side: str, quantity: int, 
                           price: float) -> Dict[str, Any]:
        """
        Validate order before placing
        
        Args:
            symbol: Stock symbol
            side: 'BUY' or 'SELL'
            quantity: Order quantity
            price: Order price
            
        Returns:
            Validation result
        """
        try:
            # Check buying power for buy orders
            if side.upper() == "BUY":
                buying_power = await self.get_buying_power(symbol, price)
                required_amount = quantity * price
                available_power = buying_power.get('buyingPower', 0)
                
                if required_amount > available_power:
                    return {
                        'valid': False,
                        'reason': f'Insufficient buying power. Required: {required_amount:,.0f}, Available: {available_power:,.0f}'
                    }
            
            # Check position for sell orders
            elif side.upper() == "SELL":
                positions = await self.get_stock_positions()
                position = next((p for p in positions if p.get('symbol') == symbol), None)
                
                if not position or position.get('quantity', 0) < quantity:
                    available_qty = position.get('quantity', 0) if position else 0
                    return {
                        'valid': False,
                        'reason': f'Insufficient position. Required: {quantity}, Available: {available_qty}'
                    }
            
            return {'valid': True, 'reason': 'Order validation passed'}
            
        except Exception as e:
            await self.logger.log_error(f"Error validating order: {e}")
            return {'valid': False, 'reason': f'Validation error: {e}'}
    
    async def get_portfolio_summary(self) -> Dict[str, Any]:
        """Get comprehensive portfolio summary"""
        try:
            # Get all data concurrently
            cash_task = self.get_cash_balance()
            positions_task = self.get_stock_positions()
            buying_power_task = self.get_buying_power()
            
            cash_balance, positions, buying_power = await asyncio.gather(
                cash_task, positions_task, buying_power_task
            )
            
            # Calculate portfolio value
            total_stock_value = sum(
                pos.get('marketValue', 0) for pos in positions
            )
            
            total_cash = cash_balance.get('totalCash', 0)
            total_portfolio_value = total_stock_value + total_cash
            
            return {
                'total_portfolio_value': total_portfolio_value,
                'total_cash': total_cash,
                'total_stock_value': total_stock_value,
                'positions_count': len(positions),
                'buying_power': buying_power.get('buyingPower', 0),
                'positions': positions,
                'cash_details': cash_balance
            }
            
        except Exception as e:
            await self.logger.log_error(f"Error getting portfolio summary: {e}")
            return {}
