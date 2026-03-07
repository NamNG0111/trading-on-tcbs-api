"""
Refactored streaming data handler with unified WebSocket base
"""
import numpy as np
import json
import asyncio
import time
import datetime
from collections import deque
from typing import Optional

from ..ws_clients.base_websocket import DerivativeStreamingClient
from ..utils.common import is_within_time_range, save_json_async
from ..utils.config_manager import get_futures_value


class StreamingDataHandler(DerivativeStreamingClient):
    """Handles streaming market data and spread calculations"""
    
    def __init__(self, ticker_f1m: str, ticker_f2m: str, shared_array: np.ndarray, lock):
        super().__init__([ticker_f1m, ticker_f2m])
        self.ticker_f1m = ticker_f1m
        self.ticker_f2m = ticker_f2m
        self.shared_array = shared_array
        
        # Load configuration values
        self.windows = get_futures_value('spread_params.windows', 100)
        self.z_scores = get_futures_value('spread_params.z_scores', 0.5)
        self.min_adj_std = get_futures_value('spread_params.min_adj_std', 0.9)
        self.lock = lock
        
        self.queue_s21 = asyncio.Queue()
        self.queue_matched_price_f2m = asyncio.Queue()
        
        # Load historical tick data
        max_history = get_futures_value('data_config.tick_data.max_history', 300)
        try:
            with open("data/tick_data.json", "r") as f:
                self.tick_data = deque(json.load(f), maxlen=max_history)
        except (FileNotFoundError, json.JSONDecodeError):
            self.tick_data = deque(maxlen=max_history)
            
        self.spread_long, self.spread_short = np.nan, np.nan
        self._setting_long_short_spread()
        self.shared_array[8] = self.spread_long
        self.shared_array[9] = self.spread_short
        
    @staticmethod
    async def write_to_file(text: str) -> None:
        """Write real-time price data to file"""
        def write_sync():
            with open("Price watching/f1m_realtime.txt", "w", encoding='utf-8') as f:
                f.write(text)
        await asyncio.to_thread(write_sync)

    async def connect(self) -> None:
        """Connect to WebSocket and start data streaming"""
        if await self.connect_with_retry(self.token):
            # Start ping and receive tasks
            tasks = [
                asyncio.create_task(self.send_ping()),
                asyncio.create_task(self.receive_loop(self.process_message))
            ]
            
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

    async def process_message(self, message: str) -> None:
        """
        Process incoming market data messages
        
        Args:
            message: Raw WebSocket message
        """
        try:
            await asyncio.wait_for(self._handle_message(message), timeout=3)
        except asyncio.TimeoutError:
            timestamp = time.strftime('%H:%M:%S')
            print(f"⚠️ {timestamp} No new messages in 3 seconds!")
            return

    async def _handle_message(self, message: str) -> None:
        """Handle specific message types"""
        if message.startswith("s|23"):  # Bid prices
            data = json.loads(message.split('|')[2])
            if data['symbol'] == self.ticker_f1m:
                self.shared_array[0] = data.get('bidPrice01', self.shared_array[2])
                self.shared_array[1] = data.get('bidPrice02', self.shared_array[2])
                await self.write_to_file(f"{round(float(self.shared_array[0]),1)} ---- {round(float(self.shared_array[2]),1)}")
            else:
                self.shared_array[4] = data.get('bidPrice01', self.shared_array[6])
                self.shared_array[5] = data.get('bidPrice02', self.shared_array[6])

        elif message.startswith("s|24"):  # Ask prices
            data = json.loads(message.split('|')[2])
            if data['symbol'] == self.ticker_f1m:
                self.shared_array[2] = data.get('offerPrice01', self.shared_array[0])
                self.shared_array[3] = data.get('offerPrice02', self.shared_array[0])
                await self.write_to_file(f"{round(float(self.shared_array[0]),1)} ---- {round(float(self.shared_array[2]),1)}")
            else:
                self.shared_array[6] = data.get('offerPrice01', self.shared_array[4])
                self.shared_array[7] = data.get('offerPrice02', self.shared_array[4])

        elif message.startswith("s|21"):  # Matched prices
            data = json.loads(message.split('|')[2])
            await self.queue_s21.put(data)

    async def process_s21_messages(self) -> None:
        """
        Process matched price messages and calculate spreads
        """
        while True:
            try:
                data = await self.queue_s21.get()

                if data['symbol'] == self.ticker_f1m:
                    if not self.queue_matched_price_f2m.empty():
                        matched_price_f2m = await self.queue_matched_price_f2m.get()

                        self.tick_data.append({
                            'VN30F1M': data['matchPrice'],
                            'VN30F2M': matched_price_f2m
                        })

                        self._setting_long_short_spread()
                        self.shared_array[8] = self.spread_long
                        self.shared_array[9] = self.spread_short
                        
                        now = datetime.datetime.now().strftime("%H:%M:%S")
                        print(f"{now} Spread long: {self.spread_long}, Spread short: {self.spread_short}, "
                              f"MatchPriceF2M: {matched_price_f2m}, MatchPriceF1M: {data['matchPrice']}")
                else:
                    if is_within_time_range(afternoon_session=(datetime.time(13, 0), datetime.time(14, 30))):
                        await self.queue_matched_price_f2m.put(data['matchPrice'])
                        
            except Exception as e:
                print(f"Error processing S21 message: {e}")

    def _setting_long_short_spread(self) -> None:
        """
        Calculate spread_long and spread_short using statistical methods
        """
        try:
            list_data = list(self.tick_data)[-self.windows:]
            if len(list_data) < 2:
                return
                
            f1 = np.array([d['VN30F1M'] for d in list_data])
            f2 = np.array([d['VN30F2M'] for d in list_data])
            spread = f2 - f1

            weights = np.ones_like(spread)
            mean = np.average(spread, weights=weights)
            std = spread.std()
            adj_std = max(std, self.min_adj_std)

            self.spread_long = round(mean - self.z_scores * adj_std, 1)
            self.spread_short = round(mean + self.z_scores * adj_std, 1)
            
        except Exception as e:
            print(f"Error calculating spreads: {e}")
            self.spread_long, self.spread_short = np.nan, np.nan
