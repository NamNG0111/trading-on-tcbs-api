"""In-memory stand-in for the TCBS REST surface used by tests.

The production `StockTradingClient` (`core/stock_api_client.py`) is large and
async-heavy. Phase 0 only needs the slices that the V2 data + reconciler paths
actually call:

- `auth.token` — truthy string so `DataProvider` thinks it can fetch live data.
- `get_realtime_price(symbol)` — returns the configured live print.
- `get_ref_price(symbol)` — the prior-close reference TCBS exposes via
  `tickerCommons`; consumed by `PriceReconciler.ref_price_fetcher`.
- `submit_order(...)` / `cancel_order(...)` — minimal recording stubs so
  Phase 5 tests can be wired against the same fake.

This is deliberately tiny — extend rather than rewrite when more surface is
needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class _RecordedOrder:
    client_order_id: str
    symbol: str
    side: str
    quantity: int
    price: float


class FakeStockApiClient:
    """Test double mirroring the slices of TCBS REST that V2 actually uses."""

    def __init__(
        self,
        *,
        token: str = "fake-token",
        live_prices: Optional[dict[str, float]] = None,
        ref_prices: Optional[dict[str, float]] = None,
    ) -> None:
        self.token = token
        self._live_prices: dict[str, float] = dict(live_prices or {})
        self._ref_prices: dict[str, float] = dict(ref_prices or {})
        self.orders_submitted: list[_RecordedOrder] = []
        self.orders_cancelled: list[str] = []

    # --- DataProvider.auth surface -----------------------------------

    def set_live_price(self, symbol: str, price: float) -> None:
        self._live_prices[symbol] = float(price)

    def set_ref_price(self, symbol: str, price: float) -> None:
        self._ref_prices[symbol] = float(price)

    def get_realtime_price(self, symbol: str) -> Optional[float]:
        return self._live_prices.get(symbol)

    def get_ref_price(self, symbol: str) -> Optional[float]:
        return self._ref_prices.get(symbol)

    # --- ref_price_fetcher signature --------------------------------
    # `PriceReconciler` expects a callable `(auth, symbol) -> Optional[float]`.
    # Bind a method as that callable so tests don't need a free function.

    def as_ref_price_fetcher(self):
        def fetcher(_auth, symbol: str) -> Optional[float]:
            return self.get_ref_price(symbol)
        return fetcher

    # --- Order placement stubs (Phase 5 will exercise these) --------

    def submit_order(
        self,
        *,
        client_order_id: str,
        symbol: str,
        side: str,
        quantity: int,
        price: float,
    ) -> str:
        self.orders_submitted.append(
            _RecordedOrder(
                client_order_id=client_order_id,
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price,
            )
        )
        return client_order_id

    def cancel_order(self, order_id: str) -> bool:
        self.orders_cancelled.append(order_id)
        return True
