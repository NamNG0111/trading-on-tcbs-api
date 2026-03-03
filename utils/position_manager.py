"""
Unified position management for trading system
"""
from typing import Dict, List, Optional
from .common import parse_positions


class PositionManager:
    """Manages position retrieval and tracking"""
    
    def __init__(self, client, tickers: List[str]):
        self.client = client
        self.tickers = tickers
        self.cached_positions: Dict[str, int] = {}
        
    def get_positions(self) -> Dict[str, int]:
        """
        Get current positions for tracked tickers
        
        Returns:
            Dictionary mapping ticker symbols to net positions
        """
        try:
            position_data = self.client.get_open_positions_derivative().get('detailData', [])
            positions = parse_positions(position_data, self.tickers)
            self.cached_positions = positions
            return positions
        except Exception as e:
            print(f"Error retrieving positions: {e}")
            return self.cached_positions  # Return cached positions on error
    
    def get_position(self, ticker: str) -> int:
        """
        Get position for specific ticker
        
        Args:
            ticker: Ticker symbol
            
        Returns:
            Net position for ticker (0 if not found)
        """
        positions = self.get_positions()
        return positions.get(ticker, 0)
    
    def get_total_position(self) -> int:
        """
        Get total net position across all tickers
        
        Returns:
            Sum of all positions
        """
        positions = self.get_positions()
        return sum(positions.values())
    
    def update_cached_position(self, ticker: str, new_position: int) -> None:
        """
        Update cached position for a ticker (for immediate updates)
        
        Args:
            ticker: Ticker symbol
            new_position: New position value
        """
        self.cached_positions[ticker] = new_position
    
    def get_position_summary(self) -> str:
        """
        Get formatted position summary
        
        Returns:
            Formatted string with position information
        """
        positions = self.get_positions()
        summary_lines = [f"{ticker}: {pos}" for ticker, pos in positions.items()]
        total = sum(positions.values())
        summary_lines.append(f"Total: {total}")
        return ", ".join(summary_lines)
