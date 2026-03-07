"""
Base WebSocket client with unified connection and ping functionality
"""
import asyncio
import websockets
import base64
import json
from typing import Optional, Callable


class BaseWebSocketClient:
    """Base class for WebSocket connections with common functionality"""
    
    def __init__(self, url: str, ping_interval: int = 5):
        self.url = url
        self.websocket: Optional[websockets.WebSocketServerProtocol] = None
        self.ping_interval = ping_interval
        self.message: Optional[str] = None
        self.is_connected = False
        
    async def send_ping(self) -> None:
        """
        Send ping messages to maintain WebSocket connection
        """
        while self.websocket and self.is_connected:
            try:
                await self.websocket.send('ping|1')
                await asyncio.sleep(self.ping_interval)
            except websockets.exceptions.ConnectionClosed:
                print("WebSocket connection lost during ping")
                self.is_connected = False
                break
            except Exception as e:
                print(f"Error sending ping: {e}")
                break
    
    async def receive_messages(self) -> str:
        """
        Receive messages from WebSocket
        
        Returns:
            Received message string
        """
        try:
            self.message = await self.websocket.recv()
            return self.message
        except websockets.exceptions.ConnectionClosed:
            print("WebSocket connection closed during receive")
            self.is_connected = False
            raise
        except Exception as e:
            print(f"Error receiving message: {e}")
            raise
    
    async def receive_loop(self, message_handler: Optional[Callable] = None) -> None:
        """
        Continuous loop for receiving messages
        
        Args:
            message_handler: Optional callback function to handle received messages
        """
        while self.websocket and self.is_connected:
            try:
                await self.receive_messages()
                if message_handler:
                    await message_handler(self.message)
            except websockets.exceptions.ConnectionClosed:
                print("⚠️ WebSocket connection closed during receive loop")
                self.is_connected = False
                break
            except Exception as e:
                print(f"⚠️ Error in receive loop: {e}")
                break
    
    async def authenticate(self, token: str) -> bool:
        """
        Base authentication method (to be overridden by subclasses)
        
        Args:
            token: Authentication token
            
        Returns:
            True if authentication successful
        """
        raise NotImplementedError("Subclasses must implement authenticate method")
    
    async def connect_with_retry(self, token: str, max_retries: int = 5, retry_delay: int = 2) -> bool:
        """
        Connect to WebSocket with retry logic
        
        Args:
            token: Authentication token
            max_retries: Maximum number of retry attempts
            retry_delay: Delay between retries in seconds
            
        Returns:
            True if connection successful
        """
        for attempt in range(max_retries):
            try:
                async with websockets.connect(self.url, ping_interval=None) as websocket:
                    self.websocket = websocket
                    self.is_connected = True
                    print(f"WebSocket connection established to {self.url}")
                    
                    # Authenticate
                    if await self.authenticate(token):
                        return True
                    else:
                        print("Authentication failed")
                        self.is_connected = False
                        return False
                        
            except Exception as e:
                print(f"Connection attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    print(f"Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                else:
                    print("Max retries reached, connection failed")
                    return False
        
        return False
    
    async def disconnect(self) -> None:
        """
        Gracefully disconnect WebSocket
        """
        self.is_connected = False
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
            print("WebSocket disconnected")


class DerivativeStreamingClient(BaseWebSocketClient):
    """WebSocket client for derivative market data streaming"""
    
    def __init__(self, tickers: list):
        from ..utils.config_manager import get_futures_value
        endpoint = get_futures_value('websocket_config.endpoints.derivative_stream', 
                                   'wss://openapi.tcbs.com.vn/ws/thesis/v1/stream/derivative')
        super().__init__(endpoint)
        self.tickers = tickers
    
    async def authenticate(self, token: str) -> bool:
        """
        Authenticate with derivative streaming service
        
        Args:
            token: JWT token
            
        Returns:
            True if authentication successful
        """
        try:
            # Send authentication
            encoded_auth = base64.b64encode(token.encode('utf-8')).decode('utf-8')
            auth_payload = f"d|a|||{encoded_auth}"
            await self.websocket.send(auth_payload)
            
            # Wait for authentication response
            auth_response = await self.websocket.recv()
            if auth_response.startswith("d|0|"):
                print("✅ Derivative streaming authentication successful!")
                
                # Subscribe to tickers
                ticker_list = ','.join(self.tickers)
                await self.websocket.send(f"d|s|tk|bp+bi+tm+op|{ticker_list}")
                print(f"📡 Subscribed to derivative data: {ticker_list}")
                return True
            else:
                print(f"Authentication failed: {auth_response}")
                return False
                
        except Exception as e:
            print(f"Authentication error: {e}")
            return False


class OrderChangeStreamingClient(BaseWebSocketClient):
    """WebSocket client for order change notifications"""
    
    def __init__(self):
        from ..utils.config_manager import get_futures_value
        endpoint = get_futures_value('websocket_config.endpoints.order_changes', 
                                   'wss://openapi.tcbs.com.vn/ws/nesoi')
        super().__init__(endpoint)
    
    async def authenticate(self, token: str) -> bool:
        """
        Authenticate with order change service
        
        Args:
            token: JWT token
            
        Returns:
            True if authentication successful
        """
        try:
            # Send authentication
            auth_payload = {"jwt": token}
            encoded_auth = base64.b64encode(json.dumps(auth_payload, separators=(",", ":")).encode()).decode()
            await self.websocket.send(f'authenticate|{encoded_auth}')
            
            # Subscribe to order changes
            topic = {"topic": "DE_ORDER"}
            encoded_topic = base64.b64encode(json.dumps(topic, separators=(",", ":")).encode()).decode()
            await self.websocket.send(f'subscribe|{encoded_topic}')
            
            print("✅ Order change streaming authentication successful!")
            return True
            
        except Exception as e:
            print(f"Order change authentication error: {e}")
            return False


class StockStreamingClient(BaseWebSocketClient):
    """WebSocket client for stock market data streaming"""
    
    def __init__(self, tickers: list):
        from ..utils.config_manager import get_futures_value
        endpoint = get_futures_value('websocket_config.endpoints.stock_stream', 
                                   'wss://openapi.tcbs.com.vn/ws/thesis/v1/stream/normal')
        super().__init__(endpoint)
        self.tickers = tickers
    
    async def authenticate(self, token: str) -> bool:
        """
        Authenticate with stock streaming service
        
        Args:
            token: JWT token
            
        Returns:
            True if authentication successful
        """
        try:
            # Send authentication
            encoded_auth = base64.b64encode(token.encode('utf-8')).decode('utf-8')
            auth_payload = f"d|a|||{encoded_auth}"
            await self.websocket.send(auth_payload)
            
            # Wait for authentication response
            auth_response = await self.websocket.recv()
            if auth_response.startswith("d|0|"):
                print("✅ Stock streaming authentication successful!")
                
                # Subscribe to tickers
                ticker_list = ','.join(self.tickers)
                await self.websocket.send(f"d|s|tk|bp+bi+tm+op|{ticker_list}")
                print(f"📡 Subscribed to stock data: {ticker_list}")
                return True
            else:
                print(f"Stock authentication failed: {auth_response}")
                return False
                
        except Exception as e:
            print(f"Stock authentication error: {e}")
            return False
