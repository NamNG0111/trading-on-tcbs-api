"""AutoTrader — composes a full scan-execute loop with explicit dependencies.

Phase-3 DI contract: every collaborator (auth, scanner, order manager,
order tracker, account manager, settings) is injected. The CLI entry
point (`main.py`) does the wiring; this class never instantiates anything
internally beyond pure value objects.
"""

from __future__ import annotations

from datetime import datetime

from trading_on_tcbs_api.stock_system_v2.auth.auth import StockAuth
from trading_on_tcbs_api.stock_system_v2.core.market_scanner import MarketScanner
from trading_on_tcbs_api.stock_system_v2.execution.order_manager import OrderManager
from trading_on_tcbs_api.stock_system_v2.execution.order_tracker import OrderTracker
from trading_on_tcbs_api.stock_system_v2.finance.account_manager import AccountManager
from trading_on_tcbs_api.stock_system_v2.obs import (
    get_logger,
    log_event,
    record_metric,
    with_correlation,
)
from trading_on_tcbs_api.stock_system_v2.settings import Settings

_logger = get_logger("auto_trader")


class AutoTrader:
    """Orchestrates one scan-and-trade cycle.

    Args:
        settings: Frozen `Settings` value object. Defines the universe and
            risk caps; per-call overrides are made by the caller via
            `Settings.model_copy(update=…)` before constructing the trader.
        auth: Authenticated `StockAuth` (validate before passing in).
        scanner: Pre-configured `MarketScanner` with strategies attached.
        order_manager: Live or safe-mode order placer.
        order_tracker: Persists the audit trail of placed orders.
        account: Cash + position bookkeeper (mock or real-synced).

    Example:
        >>> settings = Settings.load()
        >>> auth = StockAuth(); auth.validate()
        >>> trader = AutoTrader(
        ...     settings=settings, auth=auth,
        ...     scanner=MarketScanner(...),
        ...     order_manager=OrderManager(auth=auth, safe_mode=True),
        ...     order_tracker=OrderTracker(),
        ...     account=AccountManager(initial_cash=100_000_000),
        ... )
        >>> import asyncio; asyncio.run(trader.run())
    """

    def __init__(
        self,
        *,
        settings: Settings,
        auth: StockAuth,
        scanner: MarketScanner,
        order_manager: OrderManager,
        order_tracker: OrderTracker,
        account: AccountManager,
    ) -> None:
        self.settings = settings
        self.auth = auth
        self.scanner = scanner
        self.order_manager = order_manager
        self.tracker = order_tracker
        self.account = account
        self.symbols = list(settings.symbols)
        recovered = self.tracker.recover_open_orders()
        log_event(
            _logger, "auto_trader.init",
            safe_mode=self.order_manager.safe_mode,
            execution_disabled=self.order_manager.execution_disabled,
            n_symbols=len(self.symbols),
            recovered_open_orders=len(recovered),
        )

    async def run(self) -> None:
        """Execute one scan → trade cycle on the configured universe.

        Wraps the whole cycle in a single correlation id so every log
        line — scanner, order manager, tracker — can be grouped by it.
        """
        with with_correlation(prefix="cycle"):
            await self._run_inner()

    async def _run_inner(self) -> None:
        log_event(_logger, "cycle.start", n_symbols=len(self.symbols))
        record_metric("autotrader.cycles", 1.0)

        target_account = None
        if not self.order_manager.safe_mode:
            print("\n" + "=" * 50)
            print("WARNING: LIVE TRADING MODE IS ACTIVE")
            print("=" * 50)
            print("Please select the sub-account to trade on:")
            print("  1. Normal Account (0001262203)")
            print("  2. Margin Account (0001262204)")
            print("  (Or type specific sub-account ID e.g. 0001262203)")
            choice = input("Select Account [1/2/ID] (Press Enter for Default): ").strip()
            if choice == "1":
                target_account = "0001262203"
            elif choice == "2":
                target_account = "0001262204"
            elif choice:
                target_account = choice
            print(f"[Set Target Account] {target_account or 'Default aggregated view'}")

        await self.account.sync_from_api(target_account=target_account)
        log_event(
            _logger, "cycle.wallet_synced",
            balance=self.account.get_balance(),
            positions=dict(self.account.get_positions()),
        )

        results = self.scanner.scan(self.symbols)
        if not results:
            log_event(_logger, "cycle.no_signals")
            return

        log_event(_logger, "cycle.signals_found", n_signals=len(results))

        for sig in results:
            symbol = sig.symbol
            action = sig.signal
            price = sig.price
            volume = 100  # Phase-5 will replace this with the position sizer.

            if action == "BUY":
                cost = price * volume
                if not self.account.check_buying_power(cost):
                    log_event(
                        _logger, "cycle.skip_buy.insufficient_cash",
                        symbol=symbol, volume=volume, cost=cost,
                    )
                    record_metric("cycle.skipped", 1.0, reason="cash", symbol=symbol)
                    continue
            elif action == "SELL":
                current_qty = self.account.get_positions().get(symbol, 0)
                if current_qty < volume:
                    log_event(
                        _logger, "cycle.warn.undersized_sell",
                        level=30, symbol=symbol, requested=volume, held=current_qty,
                    )

            result = self.order_manager.place_order(
                symbol=symbol, side=action, price=price, volume=volume
            )

            if result.status in ("FILLED", "ACCEPTED", "PARTIALLY_FILLED"):
                # Tracker is already written by OrderManager (PENDING +
                # final state). Just keep the mock book in sync.
                self.account.update_after_trade(action, symbol, price, volume)
