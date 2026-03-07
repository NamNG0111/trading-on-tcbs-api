"""
Unified utility functions for the trading system
"""
import datetime
import json
import asyncio
from typing import Dict, List, Tuple, Optional


def is_within_time_range(
    morning_session: Tuple[datetime.time, datetime.time] = (datetime.time(9, 0), datetime.time(11, 29, 30)),
    afternoon_session: Tuple[datetime.time, datetime.time] = (datetime.time(13, 0), datetime.time(14, 29, 30))
) -> bool:
    """
    Unified time range checking function
    
    Args:
        morning_session: Tuple of (start_time, end_time) for morning session
        afternoon_session: Tuple of (start_time, end_time) for afternoon session
        
    Returns:
        bool: True if current time is within trading hours
    """
    now = datetime.datetime.now().time()
    return any(start <= now <= end for start, end in [morning_session, afternoon_session])


def parse_positions(position_data: List[Dict], tickers: List[str]) -> Dict[str, int]:
    """
    Unified position parsing function
    
    Args:
        position_data: Raw position data from API
        tickers: List of ticker symbols to filter
        
    Returns:
        Dict mapping ticker symbols to net positions
    """
    return {
        item['symbol']: int(item['net']) 
        for item in position_data 
        if item['symbol'] in tickers
    }


async def save_json_async(data: any, file_path: str) -> None:
    """
    Asynchronously save data to JSON file
    
    Args:
        data: Data to save
        file_path: Path to save file
    """
    def write_json():
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    
    await asyncio.to_thread(write_json)


def load_json_config(file_path: str, default: any = None) -> any:
    """
    Load JSON configuration file with error handling
    
    Args:
        file_path: Path to JSON file
        default: Default value if file doesn't exist or is invalid
        
    Returns:
        Loaded data or default value
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Warning: Could not load {file_path}: {e}")
        return default if default is not None else {}


def calculate_required_margin(side: str, max_position: int, ceil_price: float, floor_price: float) -> float:
    """
    Calculate required cash to prevent forced liquidation
    
    Args:
        side: Trading side ('S' for short, 'B' for long)
        max_position: Maximum position size
        ceil_price: Ceiling price
        floor_price: Floor price
        
    Returns:
        Required cash amount
    """
    if side == "S":
        margin_short_f2m = max_position * floor_price * 100000 * 0.17
        min_asset_short_f2m = margin_short_f2m / 0.9
        cash_anti_force_sell_short_f2m = min_asset_short_f2m + (ceil_price - floor_price) * max_position * 100000
        
        margin_long_f1m = max_position * ceil_price * 100000 * 0.17
        min_asset_long_f1m = margin_long_f1m / 0.9
        cash_anti_force_sell_long_f1m = min_asset_long_f1m + (ceil_price - floor_price) * max_position * 100000
        
        return cash_anti_force_sell_long_f1m + cash_anti_force_sell_short_f2m
    else:
        margin_long_f2m = max_position * ceil_price * 100000 * 0.17
        min_asset_long_f2m = margin_long_f2m / 0.9
        cash_anti_force_sell_long_f2m = min_asset_long_f2m + (ceil_price - floor_price) * max_position * 100000
        
        margin_short_f1m = max_position * floor_price * 100000 * 0.17
        min_asset_short_f1m = margin_short_f1m / 0.9
        cash_anti_force_sell_short_f1m = min_asset_short_f1m + (ceil_price - floor_price) * max_position * 100000
        
        return cash_anti_force_sell_short_f1m + cash_anti_force_sell_long_f2m
