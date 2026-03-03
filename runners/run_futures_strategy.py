"""
Main entry point for the refactored trading system
"""
import asyncio
import numpy as np
import json
{{ ... }}
import datetime
import time
from multiprocessing import Process, shared_memory, Manager

from core.api_client import TCBSClient
from logger_utils.fast_logger import LoggerManager
from utils.position_manager import PositionManager
from utils.config_manager import get_futures_value
from data.defaults import create_default_files


def run_writer(ticker_f1m, ticker_f2m, name, lock, token):
    """
    Process for streaming market data and storing in shared memory
    """
    from futures_strategy.streaming_data_handler import StreamingDataHandler
    
    shm = shared_memory.SharedMemory(name=name)
    arr = np.ndarray((10,), dtype=np.float32, buffer=shm.buf)
    streaming_data_handler = None
    
    try:
        streaming_data_handler = StreamingDataHandler(ticker_f1m, ticker_f2m, arr, lock)
        streaming_data_handler.token = token
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(asyncio.gather(
            streaming_data_handler.connect(),
            streaming_data_handler.process_s21_messages()
        ))
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Error in data writer process: {e}")
    finally:
        if streaming_data_handler:
            print("Saving tick data...")
            with open("data/tick_data.json", "w", encoding="utf-8") as f:
                json.dump(list(streaming_data_handler.tick_data), f)


def run_reader(ticker_f1m, ticker_f2m, name, lock, token, max_position, avg_price_config):
    """
    Process for trading strategy execution
    """
    from futures_strategy.processing_strategy import ProcessingStrategy
    from utils.config_manager import get_futures_value
    import datetime
    
    async def async_process_orders():
        shm = shared_memory.SharedMemory(name=name)
        arr = np.ndarray((10,), dtype=np.float32, buffer=shm.buf)
        process_orders = None
        
        # Check if today is expiry date
        expiry_date = get_futures_value('expiry_date', '2025-09-18')
        is_expiry = datetime.datetime.today().date() == datetime.datetime.strptime(expiry_date, "%Y-%m-%d").date()
        if is_expiry:
            print("Today is VN30F1M expiry date")
            # Override afternoon session for expiry day
            afternoon_session = (datetime.time(13, 0), datetime.time(14, 14, 30))
        else:
            # Load normal sessions from config
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
        
        tasks = []
        try:
            while True:
                # Load previous spread data
                with open("config/spread_dca.json", "r", encoding="utf-8") as f:
                    data_loaded = json.load(f)
                    prev_spread_long = data_loaded["prev_spread_long"]
                    prev_spread_short = data_loaded["prev_spread_short"]
                    print(f"Previous spreads - long: {prev_spread_long}, short: {prev_spread_short}")
                    
                process_orders = ProcessingStrategy(ticker_f1m, ticker_f2m, max_position, avg_price_config, arr, lock)
                process_orders.token = token
                process_orders.get_positions(prev_spread_long, prev_spread_short, pos_f1m=None, pos_f2m=None)
                
                # Run concurrent tasks
                tasks = [
                    asyncio.create_task(process_orders.order_monitor_f1m.alert_monitor(timeout=2.5)),
                    asyncio.create_task(process_orders.order_monitor_f2m.alert_monitor(timeout=2.5)),
                    asyncio.create_task(process_orders.connect_order_change()),
                    asyncio.create_task(process_orders.order_change_f1m()),
                    asyncio.create_task(process_orders.order_change_f2m()),
                    asyncio.create_task(process_orders.cut_loss_monitor()),
                    asyncio.create_task(process_orders.process_order_f1m()),
                    asyncio.create_task(process_orders.process_order_f2m()),
                ]
    
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                
                try:
                    await process_orders.handle_after_stop_process(is_expiry=is_expiry)
                except Exception as e:
                    print(f"⛔ Error handling after stop process: {e}")
                    
                now = datetime.datetime.now().time()
                if (now > afternoon_session[1]) or (morning_session[1] < now < afternoon_session[0]):
                    print("⏰ Trading session ended.")
                    break
                
                print("⏳ Restarting tasks...")
                await asyncio.sleep(10)
        
        except KeyboardInterrupt:
            print("Received stop signal...")
        except Exception as e:
            print(f"Error in order processing: {e}")
        finally:
            if tasks:
                print("Cancelling tasks...")
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                
            if process_orders:
                print("Performing final cleanup...")
                await process_orders.handle_after_stop_process(is_expiry=False)

    asyncio.run(async_process_orders())


async def main():
    """Main function to orchestrate the trading system"""
    # Create default files if they don't exist
    create_default_files()
    
    # Load configuration
    ticker_f1m = get_futures_value('contracts.f1m', 'VN30F2509')
    ticker_f2m = get_futures_value('contracts.f2m', '41I1FA000')
    max_position = get_futures_value('position_management.max_position', 10)
    avg_price_config = get_futures_value('position_management.avg_price_config', {4: 1.0, 6: 1.8, 8: 3.5, 9: 5.0})
    
    # Initialize token
    client = TCBSClient()
    if not client.initialize_token():
        print("Failed to initialize token")
        return
    
    # Initialize position manager
    position_manager = PositionManager(max_position, avg_price_config)
    position_manager.load_positions()

    try:
        # Clean up any existing shared memory
        old_shm = shared_memory.SharedMemory(name="market_data")
        old_shm.close()
        old_shm.unlink()
    except FileNotFoundError:
        pass  # No existing shared memory to clean up

    # Create shared memory for inter-process communication
    shm = shared_memory.SharedMemory(name="market_data", create=True, size=10 * np.float32().nbytes)
    shared_array = np.ndarray((10,), dtype=np.float32, buffer=shm.buf)
    shared_array[:] = np.full(10, np.nan, dtype=np.float32)
    
    token = client.token
    print("✅ Token initialized successfully")
    
    # Create and start processes
    try:
        with Manager() as manager:
            lock = manager.Lock()
    
            # Create processes
            p1 = Process(target=run_writer, args=(ticker_f1m, ticker_f2m, "market_data", lock, token))
            p2 = Process(target=run_process_orders, args=(ticker_f1m, ticker_f2m, max_position, avg_price_config, "market_data", lock, token))
            
            print("🚀 Starting trading system...")
            p2.start()
            time.sleep(2)
            p1.start()
    
            p1.join()
            p2.join()
    
    except KeyboardInterrupt:
        print("🛑 System shutdown requested")
    except Exception as e:
        print(f"⛔ System error: {e}")
    
    finally:
        print("🧹 Cleaning up shared memory...")
        shm.close()
        shm.unlink()
        print("✅ System shutdown complete")
