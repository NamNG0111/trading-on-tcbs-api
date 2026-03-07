"""
Historical data management for technical indicator calculations
"""
import json
import asyncio
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Union, Tuple
from collections import deque, defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import aiofiles
import os

from trading_on_tcbs_api.core.api_client import TCBSClient
from trading_on_tcbs_api.logger_utils.fast_logger import get_logger


@dataclass
class PriceData:
    """Price data structure"""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int = 0
    
    def to_dict(self) -> dict:
        return {
            'timestamp': self.timestamp.isoformat(),
            'open': self.open,
            'high': self.high,
            'low': self.low,
            'close': self.close,
            'volume': self.volume
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'PriceData':
        return cls(
            timestamp=datetime.fromisoformat(data['timestamp']),
            open=data['open'],
            high=data['high'],
            low=data['low'],
            close=data['close'],
            volume=data.get('volume', 0)
        )


class HistoricalDataManager:
    """Manages historical price data for technical indicators"""
    
    def __init__(self, data_dir: str = "data/historical", max_cache_size: int = 1000):
        self.data_dir = data_dir
        self.max_cache_size = max_cache_size
        self.cache: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_cache_size))
        self.last_update: Dict[str, datetime] = {}
        self.logger = get_logger('historical_data', 'Historical Data')
        
        # Ensure data directory exists
        os.makedirs(data_dir, exist_ok=True)
        
    async def get_historical_data(self, symbol: str, periods: int, 
                                 interval: str = "1D") -> List[PriceData]:
        """
        Get historical data for a symbol
        
        Args:
            symbol: Stock symbol
            periods: Number of periods to retrieve
            interval: Data interval (1D, 1H, etc.)
            
        Returns:
            List of PriceData objects
        """
        cache_key = f"{symbol}_{interval}"
        
        # Check if we have enough cached data
        if len(self.cache[cache_key]) >= periods:
            return list(self.cache[cache_key])[-periods:]
        
        # Load from file if available
        await self._load_from_file(symbol, interval)
        
        # If still not enough data, fetch from API
        if len(self.cache[cache_key]) < periods:
            await self._fetch_from_api(symbol, periods, interval)
        
        return list(self.cache[cache_key])[-periods:]
    
    async def update_latest_price(self, symbol: str, price_data: PriceData, 
                                 interval: str = "1D"):
        """
        Update the latest price data
        
        Args:
            symbol: Stock symbol
            price_data: Latest price data
            interval: Data interval
        """
        cache_key = f"{symbol}_{interval}"
        
        # Add to cache
        if len(self.cache[cache_key]) > 0:
            # Check if this is an update to the latest candle or a new candle
            latest = self.cache[cache_key][-1]
            if self._is_same_period(latest.timestamp, price_data.timestamp, interval):
                # Update existing candle
                self.cache[cache_key][-1] = price_data
            else:
                # New candle
                self.cache[cache_key].append(price_data)
        else:
            self.cache[cache_key].append(price_data)
        
        self.last_update[cache_key] = datetime.now()
        
        # Periodically save to file
        if len(self.cache[cache_key]) % 10 == 0:
            await self._save_to_file(symbol, interval)
    
    async def get_close_prices(self, symbol: str, periods: int, 
                              interval: str = "1D") -> np.ndarray:
        """Get array of close prices for indicator calculations"""
        data = await self.get_historical_data(symbol, periods, interval)
        return np.array([d.close for d in data])
    
    async def get_ohlc_data(self, symbol: str, periods: int, 
                           interval: str = "1D") -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Get OHLC arrays for indicator calculations"""
        data = await self.get_historical_data(symbol, periods, interval)
        opens = np.array([d.open for d in data])
        highs = np.array([d.high for d in data])
        lows = np.array([d.low for d in data])
        closes = np.array([d.close for d in data])
        return opens, highs, lows, closes
    
    async def get_volume_data(self, symbol: str, periods: int, 
                             interval: str = "1D") -> np.ndarray:
        """Get volume array for indicator calculations"""
        data = await self.get_historical_data(symbol, periods, interval)
        return np.array([d.volume for d in data])
    
    def _is_same_period(self, timestamp1: datetime, timestamp2: datetime, 
                       interval: str) -> bool:
        """Check if two timestamps belong to the same period"""
        if interval == "1D":
            return timestamp1.date() == timestamp2.date()
        elif interval == "1H":
            return (timestamp1.date() == timestamp2.date() and 
                   timestamp1.hour == timestamp2.hour)
        elif interval == "5M":
            return (timestamp1.date() == timestamp2.date() and 
                   timestamp1.hour == timestamp2.hour and
                   timestamp1.minute // 5 == timestamp2.minute // 5)
        else:
            # Default to minute comparison
            return (timestamp1.date() == timestamp2.date() and 
                   timestamp1.hour == timestamp2.hour and
                   timestamp1.minute == timestamp2.minute)
    
    async def _load_from_file(self, symbol: str, interval: str):
        """Load historical data from file"""
        cache_key = f"{symbol}_{interval}"
        file_path = os.path.join(self.data_dir, f"{cache_key}.json")
        
        try:
            if os.path.exists(file_path):
                async with aiofiles.open(file_path, 'r') as f:
                    content = await f.read()
                    data_list = json.loads(content)
                    
                    # Convert to PriceData objects
                    price_data = [PriceData.from_dict(d) for d in data_list]
                    
                    # Update cache
                    self.cache[cache_key].clear()
                    self.cache[cache_key].extend(price_data)
                    
                    await self.logger.log(f"Loaded {len(price_data)} records for {symbol} from file")
        except Exception as e:
            await self.logger.log_error(f"Error loading data from file for {symbol}: {e}")
    
    async def _save_to_file(self, symbol: str, interval: str):
        """Save historical data to file"""
        cache_key = f"{symbol}_{interval}"
        file_path = os.path.join(self.data_dir, f"{cache_key}.json")
        
        try:
            if cache_key in self.cache and len(self.cache[cache_key]) > 0:
                # Convert to serializable format
                data_list = [price_data.to_dict() for price_data in self.cache[cache_key]]
                
                async with aiofiles.open(file_path, 'w') as f:
                    await f.write(json.dumps(data_list, indent=2))
                    
                await self.logger.log(f"Saved {len(data_list)} records for {symbol} to file")
        except Exception as e:
            await self.logger.log_error(f"Error saving data to file for {symbol}: {e}")
    
    async def _fetch_from_api(self, symbol: str, periods: int, interval: str):
        """Fetch historical data from TCBS API"""
        try:
            # This is a placeholder - you'll need to implement based on TCBS API
            # For now, we'll generate sample data
            await self._generate_sample_data(symbol, periods, interval)
            
        except Exception as e:
            await self.logger.log_error(f"Error fetching data from API for {symbol}: {e}")
    
    async def _generate_sample_data(self, symbol: str, periods: int, interval: str):
        """Generate sample historical data for testing"""
        cache_key = f"{symbol}_{interval}"
        
        # Generate sample price data
        base_price = 100.0
        current_time = datetime.now()
        
        if interval == "1D":
            time_delta = timedelta(days=1)
        elif interval == "1H":
            time_delta = timedelta(hours=1)
        else:
            time_delta = timedelta(minutes=5)
        
        sample_data = []
        for i in range(periods):
            timestamp = current_time - time_delta * (periods - i)
            
            # Simple random walk for sample data
            price_change = np.random.normal(0, 0.02) * base_price
            base_price = max(base_price + price_change, 1.0)
            
            # Generate OHLC
            high = base_price * (1 + abs(np.random.normal(0, 0.01)))
            low = base_price * (1 - abs(np.random.normal(0, 0.01)))
            open_price = base_price + np.random.normal(0, 0.005) * base_price
            close_price = base_price
            volume = int(np.random.uniform(1000, 10000))
            
            price_data = PriceData(
                timestamp=timestamp,
                open=round(open_price, 2),
                high=round(high, 2),
                low=round(low, 2),
                close=round(close_price, 2),
                volume=volume
            )
            
            sample_data.append(price_data)
        
        # Update cache
        self.cache[cache_key].extend(sample_data)
        
        await self.logger.log(f"Generated {len(sample_data)} sample records for {symbol}")
    
    def get_cache_info(self) -> Dict[str, int]:
        """Get information about cached data"""
        return {key: len(data) for key, data in self.cache.items()}
    
    async def clear_cache(self, symbol: str = None, interval: str = None):
        """Clear cache for specific symbol/interval or all"""
        if symbol and interval:
            cache_key = f"{symbol}_{interval}"
            if cache_key in self.cache:
                self.cache[cache_key].clear()
                await self.logger.log(f"Cleared cache for {cache_key}")
        else:
            self.cache.clear()
            self.last_update.clear()
            await self.logger.log("Cleared all cache")
    
    async def preload_data(self, symbols: List[str], periods: int = 100, 
                          interval: str = "1D"):
        """Preload data for multiple symbols"""
        tasks = []
        for symbol in symbols:
            task = self.get_historical_data(symbol, periods, interval)
            tasks.append(task)
        
        await asyncio.gather(*tasks, return_exceptions=True)
        await self.logger.log(f"Preloaded data for {len(symbols)} symbols")


class RealTimeDataIntegrator:
    """Integrates real-time streaming data with historical data"""
    
    def __init__(self, historical_manager: HistoricalDataManager):
        self.historical_manager = historical_manager
        self.current_prices: Dict[str, float] = {}
        self.logger = get_logger('realtime_data', 'Real-time Data')
    
    async def update_current_price(self, symbol: str, price: float, 
                                  volume: int = 0, timestamp: datetime = None):
        """
        Update current price from streaming data
        
        Args:
            symbol: Stock symbol
            price: Current price
            volume: Current volume
            timestamp: Price timestamp
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        self.current_prices[symbol] = price
        
        # Create price data for the current period
        # For simplicity, using price as OHLC (in real implementation, you'd track intraday OHLC)
        price_data = PriceData(
            timestamp=timestamp,
            open=price,  # In real implementation, track actual open
            high=price,  # In real implementation, track actual high
            low=price,   # In real implementation, track actual low
            close=price,
            volume=volume
        )
        
        # Update historical data manager
        await self.historical_manager.update_latest_price(symbol, price_data)
        
        await self.logger.log(f"Updated price for {symbol}: {price}")
    
    async def get_indicator_data(self, symbol: str, periods: int, 
                               include_current: bool = True) -> np.ndarray:
        """
        Get data for indicator calculation including current price
        
        Args:
            symbol: Stock symbol
            periods: Number of historical periods needed
            include_current: Whether to include current streaming price
            
        Returns:
            Array of prices for indicator calculation
        """
        # Get historical close prices
        historical_data = await self.historical_manager.get_close_prices(
            symbol, periods - (1 if include_current else 0)
        )
        
        if include_current and symbol in self.current_prices:
            # Append current price
            current_price = self.current_prices[symbol]
            return np.append(historical_data, current_price)
        
        return historical_data
    
    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current streaming price"""
        return self.current_prices.get(symbol)
    
    async def get_multi_symbol_data(self, symbols: List[str], periods: int, 
                                   include_current: bool = True) -> Dict[str, np.ndarray]:
        """Get data for multiple symbols"""
        tasks = {}
        for symbol in symbols:
            tasks[symbol] = self.get_indicator_data(symbol, periods, include_current)
        
        results = {}
        for symbol, task in tasks.items():
            try:
                results[symbol] = await task
            except Exception as e:
                await self.logger.log_error(f"Error getting data for {symbol}: {e}")
                results[symbol] = np.array([])
        
        return results
