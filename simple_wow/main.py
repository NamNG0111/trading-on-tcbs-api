# main.py
import asyncio
import sys
import os
from pathlib import Path

# Add the current directory to Python path
sys.path.append(str(Path(__file__).parent))

from config_manager import ConfigManager
from trading_asyncio_module import AsyncTCBSClient, AsyncOrderManager
from signal_generator import SignalGenerator

async def main():
    # Load configuration
    config = ConfigManager()
    creds = config.load_credentials()
    
    # Initialize API client
    async with AsyncTCBSClient(api_key=creds.api_key) as client:
        # Get authentication token
        await client._get_token()
        if not client.token:
            print('❌ Không lấy được token, kiểm tra lại API Key hoặc OTP.')
            return
        
        client.account_no = creds.account_id
        client.api_key = creds.api_key
        
        # Initialize order manager and signal generator
        order_manager = AsyncOrderManager(client)
        signal_generator = SignalGenerator(api_client=client)
        
        print("🚀 Khởi động hệ thống giao dịch tự động...")
        print("📊 Đang theo dõi các mã: " + ", ".join(signal_generator.symbols))
        
        try:
            while True:
                print("\n" + "="*50)
                print(f"🔄 Đang tạo tín hiệu giao dịch...")
                
                # Generate signals using all configured strategies
                try:
                    signals = await signal_generator.generate_signals()
                    
                    if not signals:
                        print("ℹ️ Không có tín hiệu giao dịch nào được tạo ra")
                    else:
                        for signal in signals:
                            print(f"\n📈 Tín hiệu: {signal.symbol} | "
                                 f"Loại: {signal.signal_type.name} | "
                                 f"Giá: {signal.price:,.0f} | "
                                 f"KL: {signal.quantity} | "
                                 f"Độ tin cậy: {signal.confidence*100:.0f}%")
                            
                            # Execute trade if confidence is high enough
                            if signal.confidence >= 0.7:
                                order_type = "NB" if signal.signal_type.name == "BUY" else "NS"
                                print(f"⚡ Đang đặt lệnh {order_type} {signal.quantity} {signal.symbol} @ {signal.price:,.0f}...")
                                
                                # Place and monitor the order
                                await order_manager.place_and_monitor_order(
                                    client.account_no, 
                                    signal.symbol, 
                                    signal.quantity, 
                                    signal.price, 
                                    order_type
                                )
                
                except Exception as e:
                    print(f"❌ Lỗi khi tạo tín hiệu: {str(e)}")
                    import traceback
                    traceback.print_exc()
                
                # Wait before next signal generation
                print(f"\n⏳ Đợi 30 giây trước khi kiểm tra lại...")
                await asyncio.sleep(30)
                
        except KeyboardInterrupt:
            print("\n👋 Dừng hệ thống giao dịch...")
        
        except Exception as e:
            print(f"❌ Lỗi không xác định: {str(e)}")
            import traceback
            traceback.print_exc()
        
        finally:
            # Cleanup
            if 'order_manager' in locals():
                await order_manager.stop_monitoring()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Đã dừng chương trình")
    except Exception as e:
        print(f"\n❌ Lỗi nghiêm trọng: {str(e)}")
        import traceback
        traceback.print_exc()