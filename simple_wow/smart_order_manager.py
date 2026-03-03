import aiohttp
import asyncio
from datetime import datetime
from enum import Enum
from typing import Dict, Callable, Optional

class OrderStatus(Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"

class ManagedOrder:
    def __init__(self, order_id, symbol, side, quantity, price, status, placed_at, timeout_seconds, reverse_on_failure=False):
        self.order_id = order_id
        self.symbol = symbol
        self.side = side
        self.quantity = quantity
        self.price = price
        self.status = status
        self.placed_at = placed_at
        self.timeout_seconds = timeout_seconds
        self.reverse_on_failure = reverse_on_failure
        self.retry_count = 0
        self.max_retries = 3
    def is_expired(self):
        return (datetime.now() - self.placed_at).seconds > self.timeout_seconds
    def can_reverse(self):
        return self.reverse_on_failure and self.status in [OrderStatus.EXPIRED, OrderStatus.CANCELLED]

class SmartOrderManager:
    def __init__(self, api_client):
        self.api_client = api_client  # AsyncTCBSClient instance
        self.managed_orders: Dict[str, ManagedOrder] = {}
        self.order_handlers: Dict[OrderStatus, Callable] = {}
        self.is_monitoring = False
    def add_order_handler(self, status: OrderStatus, handler: Callable):
        self.order_handlers[status] = handler
    async def place_smart_order(self, symbol: str, quantity: int, price: float, side: str, timeout: int = 60, reverse_on_failure: bool = False) -> Optional[str]:
        try:
            order_result = await self.api_client.place_order(symbol, quantity, price, side)
            if "orderId" in order_result:
                order_id = order_result["orderId"]
                managed_order = ManagedOrder(
                    order_id=order_id,
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    price=price,
                    status=OrderStatus.PENDING,
                    placed_at=datetime.now(),
                    timeout_seconds=timeout,
                    reverse_on_failure=reverse_on_failure
                )
                self.managed_orders[order_id] = managed_order
                print(f"✓ Đặt lệnh thông minh: {symbol} {side} {quantity}@{price}")
                return order_id
            else:
                print(f"✗ Lỗi khi đặt lệnh: {order_result}")
                return None
        except Exception as e:
            print(f"Lỗi khi đặt lệnh thông minh: {e}")
            return None
    async def start_monitoring(self):
        self.is_monitoring = True
        print("🔍 Bắt đầu theo dõi lệnh")
        while self.is_monitoring:
            try:
                await self._check_orders_status()
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                print("\n🛑 Dừng theo dõi lệnh")
                break
            except Exception as e:
                print(f"Lỗi khi theo dõi lệnh: {e}")
                await asyncio.sleep(10)
    async def _check_orders_status(self):
        expired_orders = []
        for order_id, managed_order in self.managed_orders.items():
            if managed_order.status == OrderStatus.PENDING:
                if managed_order.is_expired():
                    expired_orders.append(order_id)
                else:
                    await self._update_order_status(order_id, managed_order)
        for order_id in expired_orders:
            await self._handle_expired_order(order_id)
    async def _update_order_status(self, order_id: str, managed_order: ManagedOrder):
        try:
            order_info = await self.api_client.get_order_status(order_id)
            if order_info and "data" in order_info:
                order_data = order_info["data"][0]
                status_code = order_data.get("orStatus")
                new_status = self._map_status_code(status_code)
                if new_status != managed_order.status:
                    old_status = managed_order.status
                    managed_order.status = new_status
                    print(f"📊 Lệnh {order_id} thay đổi trạng thái: {old_status.value} -> {new_status.value}")
                    if new_status in self.order_handlers:
                        await self.order_handlers[new_status](order_id, managed_order)
        except Exception as e:
            print(f"Lỗi khi cập nhật trạng thái lệnh {order_id}: {e}")
    def _map_status_code(self, status_code: str) -> OrderStatus:
        status_map = {
            "2": OrderStatus.PENDING,
            "3": OrderStatus.CANCELLED,
            "4": OrderStatus.FILLED,
            "5": OrderStatus.EXPIRED,
            "0": OrderStatus.REJECTED,
        }
        return status_map.get(status_code, OrderStatus.PENDING)
    async def _handle_expired_order(self, order_id: str):
        managed_order = self.managed_orders[order_id]
        print(f"⏰ Lệnh {order_id} ({managed_order.symbol}) đã hết hạn")
        if managed_order.status == OrderStatus.PENDING:
            await self._cancel_order(order_id)
        if managed_order.can_reverse():
            await self._place_reverse_order(managed_order)
        del self.managed_orders[order_id]
    async def _cancel_order(self, order_id: str):
        try:
            url = f"https://openapi.tcbs.com.vn/akhlys/v1/accounts/{self.api_client.account_no}/orders/cancel"
            headers = {
                "Authorization": f"Bearer {self.api_client.token}",
                "apiKey": self.api_client.api_key,
                "Content-Type": "application/json"
            }
            cancel_data = {"ordersList": [{"orderID": order_id}]}
            async with self.api_client.session.post(url, headers=headers, json=cancel_data) as resp:
                result = await resp.json()
                print(f"✅ Đã hủy lệnh {order_id}: {result}")
        except Exception as e:
            print(f"Lỗi khi hủy lệnh {order_id}: {e}")
    async def _place_reverse_order(self, managed_order: ManagedOrder):
        try:
            reverse_side = "NS" if managed_order.side == "NB" else "NB"
            current_price = await self.api_client.get_realtime_price(managed_order.symbol)
            print(f"🔄 Đặt lệnh đảo ngược: {managed_order.symbol} {reverse_side} {managed_order.quantity}@{current_price}")
            await self.place_smart_order(
                symbol=managed_order.symbol,
                quantity=managed_order.quantity,
                price=current_price,
                side=reverse_side,
                timeout=30,
                reverse_on_failure=False
            )
        except Exception as e:
            print(f"Lỗi khi đặt lệnh đảo ngược: {e}")
