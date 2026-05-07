"""Entry point for the V2 standalone live loop.

Composition root: builds every dependency explicitly and hands them to
`AutoTrader`. No class in `core/`, `execution/`, or `finance/` should
instantiate its peers — that wiring belongs here.
"""

from __future__ import annotations

import asyncio
import time

from trading_on_tcbs_api.stock_system_v2.auth.auth import StockAuth
from trading_on_tcbs_api.stock_system_v2.core.auto_trader import AutoTrader
from trading_on_tcbs_api.stock_system_v2.core.indicator_engine import IndicatorEngine
from trading_on_tcbs_api.stock_system_v2.core.market_scanner import MarketScanner
from trading_on_tcbs_api.stock_system_v2.data_ingest.data_provider import DataProvider
from trading_on_tcbs_api.stock_system_v2.execution.order_manager import OrderManager
from trading_on_tcbs_api.stock_system_v2.execution.order_tracker import OrderTracker
from trading_on_tcbs_api.stock_system_v2.finance.account_manager import AccountManager
from trading_on_tcbs_api.stock_system_v2.settings import Settings
from trading_on_tcbs_api.stock_system_v2.strategies import (
    CombinedStrategy,
    RSIStrategy,
    SimpleMAStrategy,
    VolumeBoomStrategy,
)


def _build_default_strategy() -> CombinedStrategy:
    ma = SimpleMAStrategy(short_window=20, long_window=50)
    vol = VolumeBoomStrategy(window=20, threshold_pct=10)
    rsi = RSIStrategy(period=14)
    return CombinedStrategy(
        strategies=[],
        buy_strategies=[ma, vol],
        sell_strategies=[rsi],
        buy_mode="AND",
        sell_mode="OR",
    )


def main() -> None:
    print("==========================================")
    print("   Stock System V2 - Standalone           ")
    print("==========================================")

    settings = Settings.load()

    auth = StockAuth()
    print("Initializing Authentication...")
    if not auth.validate():
        print("Authentication failed. Exiting.")
        return

    print(f"Authenticated. Monitoring {len(settings.symbols)} symbols: {list(settings.symbols)}")

    strategy = _build_default_strategy()
    scanner = MarketScanner(
        data_provider=DataProvider(auth=auth),
        indicator_engine=IndicatorEngine(),
        strategies={"Default": strategy},
    )
    order_tracker = OrderTracker()
    order_manager = OrderManager(
        auth=auth,
        safe_mode=True,
        execution_disabled=settings.execution_disabled,
        tracker=order_tracker,
    )
    account = AccountManager(initial_cash=100_000_000)

    trader = AutoTrader(
        settings=settings,
        auth=auth,
        scanner=scanner,
        order_manager=order_manager,
        order_tracker=order_tracker,
        account=account,
    )

    print("\nStarting Main Loop (Press Ctrl+C to stop)...")
    try:
        while True:
            print(f"[{time.strftime('%H:%M:%S')}] Cycle starting...")
            asyncio.run(trader.run())
            time.sleep(10)
    except KeyboardInterrupt:
        print("\nSystem stopped by user.")


if __name__ == "__main__":
    main()
