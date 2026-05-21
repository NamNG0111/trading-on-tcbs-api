"""HITLCoordinator — orchestrates scan → confirmation → revalidation → order (Phase 10).

This is the central safety object for live trading. The scanner hands a
fresh signal to `handle_signal`; the coordinator persists it as a
`PendingSignal`, asks the operator via the configured channel (or
auto-approves in `auto` mode), re-validates strictly against fresh data,
runs the pre-trade validator, and then places the order through the
existing `OrderManager`. Every transition appends a new row to the
durable store so a `kill -9` recovers cleanly.

Mode toggle (`trading_mode`):
  - `hitl`  → must ask the channel and receive an explicit `yes` before
              advancing. `no` / `timeout` are terminal.
  - `auto`  → skip the channel call. Re-validation still runs; the auto
              path is "skip the human", not "skip safety".

`EXECUTION_DISABLED=true` (in `Settings`) takes precedence over both
modes — the `OrderManager` rejects every order regardless, so the worst
auto-mode can do during the kill-switch is mark signals `failed` for
audit and move on.
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable, Literal

from trading_on_tcbs_api.stock_system_v2.exceptions import (
    DuplicateOrderError,
    OrderRejectedError,
    RiskLimitViolatedError,
    StockSystemError,
)
from trading_on_tcbs_api.stock_system_v2.execution.hitl.channels import ConfirmationChannel
from trading_on_tcbs_api.stock_system_v2.execution.hitl.pending_signal_store import (
    PendingSignalStore,
)
from trading_on_tcbs_api.stock_system_v2.execution.hitl.revalidator import (
    StrictRevalidator,
)
from trading_on_tcbs_api.stock_system_v2.execution.order_manager import OrderManager
from trading_on_tcbs_api.stock_system_v2.execution.pre_trade_validator import (
    DailyTradeStats,
    PreTradeValidator,
)
from trading_on_tcbs_api.stock_system_v2.obs import (
    get_logger,
    log_event,
    record_metric,
    with_correlation,
)
from trading_on_tcbs_api.stock_system_v2.schemas import (
    AccountSnapshot,
    MarketContext,
    OrderRequest,
    PendingSignal,
)

_logger = get_logger("hitl.coordinator")

TradingMode = Literal["hitl", "auto"]

AccountProvider = Callable[[], AccountSnapshot]
MarketProvider = Callable[[str], MarketContext]
DailyStatsProvider = Callable[[], DailyTradeStats]


class HITLCoordinator:
    """Single-process orchestrator for HITL + auto-mode order placement.

    Args:
        channel: ConfirmationChannel impl (Terminal, Telegram, …).
        revalidator: `StrictRevalidator` configured with the same data
            provider the scanner uses.
        validator: `PreTradeValidator` instance.
        order_manager: `OrderManager` instance. Safe-mode vs live is
            controlled at the OrderManager level, not here.
        store: `PendingSignalStore` for durable state.
        account_provider: Zero-arg callable returning the latest
            `AccountSnapshot`. Called once per confirmation.
        market_provider: Callable from symbol → `MarketContext`. Called
            once per confirmation.
        trading_mode: `hitl` (default) or `auto`.
        confirmation_timeout_sec: Per-signal TTL.

    Lifecycle:
        1. On process start: `await resume_open_pending()` to replay
           anything left over from the previous run.
        2. Per scanner cycle: `await handle_signal(...)` per signal the
           scanner emits. The coordinator handles each signal end-to-end;
           the scanner can immediately move on to the next symbol.
    """

    def __init__(
        self,
        *,
        channel: ConfirmationChannel,
        revalidator: StrictRevalidator,
        validator: PreTradeValidator,
        order_manager: OrderManager,
        store: PendingSignalStore,
        account_provider: AccountProvider,
        market_provider: MarketProvider,
        daily_stats_provider: DailyStatsProvider | None = None,
        trading_mode: TradingMode = "hitl",
        confirmation_timeout_sec: int = 3600,
    ) -> None:
        if trading_mode not in ("hitl", "auto"):
            raise ValueError(f"unknown trading_mode: {trading_mode!r}")
        if confirmation_timeout_sec <= 0:
            raise ValueError("confirmation_timeout_sec must be > 0")
        self.channel = channel
        self.revalidator = revalidator
        self.validator = validator
        self.order_manager = order_manager
        self.store = store
        self.account_provider = account_provider
        self.market_provider = market_provider
        self.daily_stats_provider = daily_stats_provider
        self.trading_mode = trading_mode
        self.confirmation_timeout_sec = confirmation_timeout_sec

    # — public —

    async def handle_signal(
        self,
        *,
        symbol: str,
        side: Literal["BUY", "SELL"],
        strategy_name: str,
        ref_price: float,
        ref_bar_close_ts: datetime,
        proposed_volume: int,
        proposed_notional_vnd: int,
        correlation_id: str,
        strategy_params: dict | None = None,
    ) -> PendingSignal:
        """End-to-end handling of one scanner signal.

        Returns the final `PendingSignal` after status is terminal
        (submitted, rejected, expired, stale, failed). The caller may
        inspect `result.status` to drive a UI or log summary.
        """
        pending = PendingSignal.from_scan(
            symbol=symbol,
            side=side,
            strategy_name=strategy_name,
            strategy_params=strategy_params or {},
            ref_price=ref_price,
            ref_bar_close_ts=ref_bar_close_ts,
            proposed_volume=proposed_volume,
            proposed_notional_vnd=proposed_notional_vnd,
            correlation_id=correlation_id,
            timeout_seconds=self.confirmation_timeout_sec,
        )
        self.store.append(pending)
        record_metric("hitl.signal.dispatched", 1.0, side=side, mode=self.trading_mode)

        with with_correlation(cid=correlation_id):
            return await self._process(pending)

    async def confirm_pending(self, signal_id: str) -> PendingSignal:
        """Confirm an `awaiting` signal out-of-band (via MCP tool / web UI).

        Runs the same revalidation + validation + placement path that a
        channel-driven `yes` would. Idempotent: re-confirming a signal in
        a terminal state returns its current row without side effects.

        Raises:
            KeyError: when `signal_id` is unknown.
        """
        pending = self.store.get(signal_id)
        if pending is None:
            raise KeyError(f"unknown pending signal id: {signal_id}")
        if pending.status != "awaiting":
            return pending  # idempotent
        confirmed = self.store.update_status(
            signal_id, "confirmed", notes="confirmed via tool",
        )
        record_metric("hitl.signal.confirmed", 1.0, mode=self.trading_mode, source="tool")
        with with_correlation(cid=confirmed.correlation_id):
            return await self._post_confirm(confirmed)

    async def reject_pending(self, signal_id: str) -> PendingSignal:
        """Reject an `awaiting` signal out-of-band. Idempotent.

        Raises:
            KeyError: when `signal_id` is unknown.
        """
        pending = self.store.get(signal_id)
        if pending is None:
            raise KeyError(f"unknown pending signal id: {signal_id}")
        if pending.status != "awaiting":
            return pending
        updated = self.store.update_status(
            signal_id, "rejected", notes="rejected via tool",
        )
        record_metric("hitl.signal.rejected", 1.0, mode=self.trading_mode, source="tool")
        await self._safe_notify(updated, "rejected")
        return updated

    def set_trading_mode(self, mode: TradingMode) -> TradingMode:
        """Switch HITL ↔ auto at runtime. Returns the new mode.

        Persistence: this only mutates the live coordinator instance.
        To survive a restart, the operator must also flip
        `Settings.trading_mode` in config — by design, so a sudden
        switch to `auto` cannot quietly outlive the session.
        """
        if mode not in ("hitl", "auto"):
            raise ValueError(f"unknown trading_mode: {mode!r}")
        prev = self.trading_mode
        self.trading_mode = mode
        log_event(
            _logger, "hitl.coordinator.mode_change",
            previous=prev, current=mode,
        )
        return mode

    async def resume_open_pending(self) -> list[PendingSignal]:
        """Replay open signals after a restart.

        Expires anything past its deadline, then re-displays the still-open
        rows on the channel. Returns the open list (post-expiry) so callers
        can show a summary.
        """
        self.store.expire_overdue()
        open_signals = self.store.load_open()
        await self.channel.replay_pending(open_signals)
        log_event(_logger, "hitl.coordinator.resume", count=len(open_signals))
        return open_signals

    # — internals —

    async def _process(self, pending: PendingSignal) -> PendingSignal:
        decision = await self._ask(pending)

        if decision == "no":
            updated = self.store.update_status(pending.id, "rejected", notes="operator declined")
            record_metric("hitl.signal.rejected", 1.0, mode=self.trading_mode)
            await self._safe_notify(updated, "rejected")
            return updated

        if decision == "timeout":
            updated = self.store.update_status(pending.id, "expired", notes="confirmation timed out")
            record_metric("hitl.signal.expired", 1.0, mode=self.trading_mode)
            await self._safe_notify(updated, "expired")
            return updated

        # decision == "yes" (HITL confirmed or auto-approved)
        pending = self.store.update_status(pending.id, "confirmed", notes="confirmed; re-validating")
        record_metric("hitl.signal.confirmed", 1.0, mode=self.trading_mode)
        return await self._post_confirm(pending)

    async def _post_confirm(self, pending: PendingSignal) -> PendingSignal:
        """Run revalidator → validator → order placement. Shared between
        the channel-driven `_process` and the out-of-band `confirm_pending`.
        """
        reval = self.revalidator.check(pending)
        if not reval.passed:
            updated = self.store.update_status(
                pending.id,
                "stale",
                revalidation_result=reval,
                notes=reval.reason or "revalidation failed",
            )
            record_metric("hitl.signal.stale", 1.0, mode=self.trading_mode)
            log_event(
                _logger, "hitl.signal.stale",
                signal_id=pending.id, symbol=pending.symbol, reason=reval.reason,
            )
            await self._safe_notify(updated, "stale", reval.reason)
            return updated

        return await self._place(pending, reval_fresh_price=reval.fresh_price)

    async def _ask(self, pending: PendingSignal) -> str:
        if self.trading_mode == "auto":
            log_event(
                _logger, "hitl.coordinator.auto_approve",
                signal_id=pending.id, symbol=pending.symbol,
            )
            return "yes"

        try:
            resp = await self.channel.request(pending)
        except Exception as exc:  # channel-level failure (e.g. Telegram down)
            log_event(
                _logger, "hitl.coordinator.channel_error",
                signal_id=pending.id, error=str(exc), error_type=type(exc).__name__,
            )
            # Treat unrecoverable channel failures as `no` — never silently approve.
            return "no"
        return resp.decision

    async def _place(self, pending: PendingSignal, *, reval_fresh_price: float | None) -> PendingSignal:
        # Build an OrderRequest at the freshest price (drift-adjusted) so
        # the validator's price-band check operates on the real intent,
        # not the stale ref_price.
        price = reval_fresh_price if reval_fresh_price is not None else pending.ref_price
        req = OrderRequest(
            symbol=pending.symbol,
            side=pending.side,
            price=price,
            volume=pending.proposed_volume,
        )

        try:
            account = self.account_provider()
            market = self.market_provider(pending.symbol)
            daily_stats = self.daily_stats_provider() if self.daily_stats_provider else None
        except StockSystemError as exc:
            return await self._fail(pending, f"context fetch raised: {exc}")

        risk_check = self.validator.validate(
            req, account=account, market=market, daily_stats=daily_stats,
        )
        if not risk_check.passed:
            updated = self.store.update_status(
                pending.id,
                "failed",
                notes=f"validator blocked: {', '.join(risk_check.violations) or 'see findings'}",
            )
            record_metric("hitl.signal.failed", 1.0, reason="validator")
            await self._safe_notify(updated, "failed", "validator blocked")
            return updated

        try:
            resp = self.order_manager.place_order(request=req, risk_check=risk_check)
        except (RiskLimitViolatedError, OrderRejectedError, DuplicateOrderError) as exc:
            return await self._fail(pending, f"{type(exc).__name__}: {exc}")

        if resp.status == "REJECTED":
            updated = self.store.update_status(
                pending.id, "failed", notes=resp.note or "broker rejected",
            )
            record_metric("hitl.signal.failed", 1.0, reason="broker_reject")
            await self._safe_notify(updated, "failed", resp.note)
            return updated

        updated = self.store.update_status(
            pending.id,
            "submitted",
            notes=f"broker_order_id={resp.broker_order_id or 'n/a'} status={resp.status}",
        )
        record_metric("hitl.signal.submitted", 1.0, mode=self.trading_mode)
        await self._safe_notify(
            updated,
            "submitted",
            f"broker_order_id={resp.broker_order_id} status={resp.status}",
        )
        return updated

    async def _fail(self, pending: PendingSignal, note: str) -> PendingSignal:
        updated = self.store.update_status(pending.id, "failed", notes=note)
        record_metric("hitl.signal.failed", 1.0, reason="exception")
        log_event(_logger, "hitl.signal.failed", signal_id=pending.id, note=note)
        await self._safe_notify(updated, "failed", note)
        return updated

    async def _safe_notify(
        self,
        pending: PendingSignal,
        outcome: str,
        details: str | None = None,
    ) -> None:
        """notify_outcome but swallowing channel errors so notifications
        never re-fail an already-recorded transition."""
        try:
            await self.channel.notify_outcome(pending, outcome, details)
        except Exception as exc:  # channel transient — already recorded on disk
            log_event(
                _logger, "hitl.coordinator.notify_failed",
                signal_id=pending.id, outcome=outcome, error=str(exc),
            )
