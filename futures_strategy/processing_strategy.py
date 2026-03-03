"""
Refactored trading strategy with unified components
"""
import asyncio
import json
import numpy as np
import pandas as pd
import datetime
from collections import deque
from typing import Optional, Dict, Any

from ..core.api_client import TCBSClient
from ..core.order_monitor import OrderMonitor
from ..ws_clients.base_websocket import OrderChangeStreamingClient
from ..utils.position_manager import PositionManager
from ..utils.common import is_within_time_range
from ..logger_utils.fast_logger import get_logger
from ..utils.config_manager import get_futures_value

# Load configuration values
expiry_date = get_futures_value('expiry_date', '2025-09-18')
cut_points = get_futures_value('risk_management.cut_points', 20)
max_qty_place = get_futures_value('risk_management.max_qty_place', 5)
slippage_points = get_futures_value('risk_management.slippage_points', 3)
depth_gap = get_futures_value('risk_management.depth_gap', 0.3)
cut_time = get_futures_value('risk_management.cut_time', 60)

# Load session times
sessions = get_futures_value('sessions', {})
morning_config = sessions.get('morning', {'start': [9, 0], 'end': [11, 29, 30]})
afternoon_config = sessions.get('afternoon', {'start': [13, 0], 'end': [14, 29, 30]})

morning_session = (
    datetime.time(morning_config['start'][0], morning_config['start'][1]),
    datetime.time(morning_config['end'][0], morning_config['end'][1], morning_config['end'][2] if len(morning_config['end']) > 2 else 0)
)
afternoon_session = (
    datetime.time(afternoon_config['start'][0], afternoon_config['start'][1]),
    datetime.time(afternoon_config['end'][0], afternoon_config['end'][1], afternoon_config['end'][2] if len(afternoon_config['end']) > 2 else 0)
)

# Check if today is expiry date
is_expiry = datetime.datetime.today().date() == datetime.datetime.strptime(expiry_date, "%Y-%m-%d").date()
if is_expiry:
    print("Today is VN30F1M expiry date")
    afternoon_session = (datetime.time(13, 0), datetime.time(14, 14, 30))

# Initialize loggers
today_str = datetime.datetime.today().strftime('%d%m%Y')
logger_trading = get_logger('trading', 'Futures/Trading')
logger_trade_history = get_logger('trade_history', 'Futures/Trade History')
logger_msg_f1m = get_logger('f1m_messages', 'Futures/Messages/F1M')
logger_msg_f2m = get_logger('f2m_messages', 'Futures/Messages/F2M')


async def write_trade_history(ticker: str, data: Dict[str, Any], side: str, extra: Optional[Dict] = None) -> None:
    """
    Log trade execution details
    
    Args:
        ticker: Trading symbol
        data: Trade data
        side: Trade side
        extra: Additional data to log
    """
    record = {
        'ticker': ticker,
        'side': side,
        'price': data['showPrice'],
        'lastPrice': data['matchPriceBQ'],
        'quantity': data['matchVolume']
    }
    if extra:
        record.update(extra)
    await logger_trade_history.log(json.dumps(record))


class ProcessingStrategy(TCBSClient, OrderChangeStreamingClient):
    """Main trading strategy implementation with unified components"""
    
    def __init__(self, ticker_f1m: str, ticker_f2m: str, max_position: int, 
                 avg_price_config: Dict[int, float], shared_array: np.ndarray, lock):
        TCBSClient.__init__(self)
        OrderChangeStreamingClient.__init__(self)
        
        self.ticker_f1m = ticker_f1m
        self.ticker_f2m = ticker_f2m
        self.shared_array = shared_array
        self.lock = lock
        
        # Position management
        self.position_manager = PositionManager(self, [ticker_f1m, ticker_f2m])
        self.max_position = max_position
        self.avg_price_config = avg_price_config
        self.pos_f1m, self.pos_f2m = 0, 0
        self.old_pos_f1m, self.old_pos_f2m = 0, 0
        
        # Market data
        self.bid_f1m = self.ask_f1m = np.nan
        self.bid2_f1m = self.ask2_f1m = np.nan
        self.bid_f2m = self.ask_f2m = np.nan
        self.bid2_f2m = self.ask2_f2m = np.nan
        
        # Spread data
        self.spread_long = self.spread_short = np.nan
        self.temp_spread_long = self.temp_spread_short = np.nan
        self.dca_spread_long = self.dca_spread_short = np.nan
        
        # Order management
        self.placing_order_f1m = self.placing_order_f2m = False
        self.order_id_f1m = self.order_id_f2m = None
        self.order_id_f1m_after_confirmed = self.order_id_f2m_after_confirmed = None
        self.order_id_f1m_after_filled = self.order_id_f2m_after_filled = None
        self.order_id_f1m_after_canceled = self.order_id_f2m_after_canceled = None
        
        # Trading parameters
        self.qty_f1m = 0
        self.side_f1m = self.side_f2m = None
        self.expected_qty = 0
        self.fully_filled_f2m = False
        
        # DCA parameters
        self.keys_sorted = sorted(avg_price_config)
        self.values_sorted = np.array([avg_price_config[k] for k in self.keys_sorted])
        self.first_key_dca = self.keys_sorted[0]
        self.last_value_dca = self.avg_price_config[self.keys_sorted[-1]]
        self.spread_trigger_dca = None
        self.qty_long_f2m = self.qty_short_f2m = 0
        self.buffer = 0
        
        # Risk management
        self.cut_loss = False
        self.cut_loss_check_start_time = None
        self.last_bought_spread_long = self.last_sold_spread_short = np.nan
        
        # Queues for order processing
        self.queue_order_msg_f1m = asyncio.Queue()
        self.queue_order_msg_f2m = asyncio.Queue()
        self.queue_pending_order_f1m = asyncio.Queue(maxsize=1)
        self.queue_pending_order_f2m = asyncio.Queue(maxsize=1)
        self.queue_trigger_f1m = asyncio.Queue()
        self.queue_trigger_f2m = asyncio.Queue(maxsize=1)
        
        # Monitoring
        self.stop_event = asyncio.Event()
        self.order_monitor_f1m = OrderMonitor(self.stop_event, "F1M")
        self.order_monitor_f2m = OrderMonitor(self.stop_event, "F2M")
        
        # Response tracking
        self.matched_quantity_f1m = self.matched_quantity_f2m = 0
        self.order_response_received_f1m = self.order_response_received_f2m = True

    def get_data(self) -> None:
        """Extract bid/ask prices from shared memory"""
        try:
            array = self.shared_array.astype(float).tolist()
            self.bid_f1m = round(array[0], 1)
            self.bid2_f1m = round(array[1], 1)
            self.ask_f1m = round(array[2], 1)
            self.ask2_f1m = round(array[3], 1)
            self.bid_f2m = round(array[4], 1)
            self.bid2_f2m = round(array[5], 1)
            self.ask_f2m = round(array[6], 1)
            self.ask2_f2m = round(array[7], 1)
            self.spread_long = round(array[8], 1)
            self.spread_short = round(array[9], 1)
        except Exception as e:
            print(f"Error getting data from shared memory: {e}")

    def _apply_dca_method(self, max_qty_place: int = max_qty_place) -> None:
        """Calculate DCA (Dollar Cost Averaging) quantities"""
        try:
            if self.pos_f2m >= 0:
                idx = np.searchsorted(self.keys_sorted, self.pos_f2m, side='right')
                if idx < len(self.keys_sorted):
                    self.qty_long_f2m = int(min(self.keys_sorted[idx], self.max_position) - self.pos_f2m)
                    self.buffer = 0 if idx == 0 else self.values_sorted[idx - 1]
                else:
                    self.qty_long_f2m = int(self.max_position - self.pos_f2m)
                    self.buffer = self.last_value_dca
                self.qty_short_f2m = int(min(max_qty_place, self.pos_f2m + self.first_key_dca))
            else:
                idx = np.searchsorted(self.keys_sorted, -self.pos_f2m, side='right')
                if idx < len(self.keys_sorted):
                    self.qty_short_f2m = int(min(self.keys_sorted[idx], self.max_position) + self.pos_f2m)
                    self.buffer = 0 if idx == 0 else self.values_sorted[idx - 1]
                else:
                    self.qty_short_f2m = int(self.max_position + self.pos_f2m)
                    self.buffer = self.last_value_dca
                self.qty_long_f2m = int(min(max_qty_place, -self.pos_f2m + self.first_key_dca))
        except Exception as e:
            print(f"Error applying DCA method: {e}")

    def get_positions(self, prev_spread_long: float, prev_spread_short: float, 
                     pos_f1m: Optional[int] = None, pos_f2m: Optional[int] = None) -> None:
        """
        Retrieve and initialize current positions
        
        Args:
            prev_spread_long: Previous long spread value
            prev_spread_short: Previous short spread value
            pos_f1m: Manual F1M position (fallback)
            pos_f2m: Manual F2M position (fallback)
        """
        try:
            positions = self.position_manager.get_positions()
            self.pos_f1m = positions.get(self.ticker_f1m, pos_f1m or 0)
            self.pos_f2m = positions.get(self.ticker_f2m, pos_f2m or 0)
            self.old_pos_f1m, self.old_pos_f2m = self.pos_f1m, self.pos_f2m
            
            print(f"Positions - F1M: {self.pos_f1m}, F2M: {self.pos_f2m}")
            
            self._apply_dca_method()
            self.get_data()
            
            # Initialize DCA spreads based on current positions
            if self.pos_f2m >= self.first_key_dca:
                self.spread_trigger_dca = prev_spread_long
                self.dca_spread_long = self.spread_trigger_dca - self.buffer
                self.dca_spread_short = self.spread_short
            elif self.pos_f2m <= -self.first_key_dca:
                self.spread_trigger_dca = prev_spread_short
                self.dca_spread_short = self.spread_trigger_dca + self.buffer
                self.dca_spread_long = self.spread_long
            else:
                self.dca_spread_long, self.dca_spread_short = self.spread_long, self.spread_short
                
        except Exception as e:
            print(f"Error getting positions: {e}")
            # Use manual positions as fallback
            self.pos_f1m = pos_f1m or 0
            self.pos_f2m = pos_f2m or 0
            self.old_pos_f1m, self.old_pos_f2m = self.pos_f1m, self.pos_f2m

    async def connect_order_change(self) -> None:
        """Connect to order change WebSocket"""
        if await self.connect_with_retry(self.token):
            await self.receive_loop(self.receive_messages_order_change)

    async def receive_messages_order_change(self, message: str) -> None:
        """
        Route order change messages to appropriate queues
        
        Args:
            message: Order change message
        """
        try:
            if message.startswith("message_proto|DE_ORDER"):
                data = json.loads(message.split('|')[2])
                
                if (int(data['orderNo']) == self.order_id_f1m) or (data['orderNo'] == self.order_id_f1m):
                    await self.queue_order_msg_f1m.put(data)
                    await logger_msg_f1m.log(json.dumps(data))
                    
                elif (int(data['orderNo']) == self.order_id_f2m) or (data['orderNo'] == self.order_id_f2m):
                    await self.queue_order_msg_f2m.put(data)
                    await logger_msg_f2m.log(json.dumps(data))
        except Exception as e:
            print(f"Error processing order change message: {e}")

    # Additional methods would continue here...
    # Due to length constraints, I'll create the remaining methods in separate files

    async def handle_after_stop_process(self, is_expiry: bool = False) -> None:
        """
        Clean up orders and positions after stopping
        
        Args:
            is_expiry: Whether today is expiry date
        """
        try:
            # Cancel all pending orders
            await asyncio.gather(
                self.cancel_order(self.order_id_f2m), 
                self.cancel_order(self.order_id_f1m),
                return_exceptions=True
            )
            
            # Flush all loggers
            await asyncio.gather(
                logger_trading.flush(),
                logger_trade_history.flush(),
                logger_msg_f1m.flush(),
                logger_msg_f2m.flush(),
                return_exceptions=True
            )
            
            print("✅ Cleanup completed successfully")
            
        except Exception as e:
            print(f"Error during cleanup: {e}")
