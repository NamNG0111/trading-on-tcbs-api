"""Live Trader Agent — HITL-by-default real-money loop (Phase 10).

Replaces the Phase-8 `NotImplementedError` stub. The contract:

  - Every scanner signal is dispatched through a `HITLCoordinator`. In
    `trading_mode="hitl"` (the default) the operator must explicitly
    confirm via the configured channel; in `trading_mode="auto"` the
    coordinator auto-approves but the strict re-validator still runs.
  - Three hard caps (`max_position_size_vnd`, `max_daily_loss_vnd`,
    `max_trades_per_day`) are enforced inside `PreTradeValidator` so
    every path — HITL, auto, paper, future channels — inherits them.
  - `EXECUTION_DISABLED=true` is a global kill-switch consulted by the
    `OrderManager` on every order. A `health_check.ok=False` aborts
    the entire cycle before the first dispatch.

This module owns wiring + orchestration only; the safety primitives all
live in `execution/hitl/`. Caller responsibility:

  - construct the coordinator (channel, revalidator, validator,
    order_manager, store, providers) yourself or via the upcoming
    composition root (`main.py` rework, separate PR).
  - call `await resume_open_pending(coord)` once on process start to
    replay any signal left over from a prior run.
  - call `await live_trade_cycle(coord, scan)` per scanner pass.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from trading_on_tcbs_api.stock_system_v2.execution.hitl import HITLCoordinator
from trading_on_tcbs_api.stock_system_v2.obs import get_logger, log_event, new_correlation_id
from trading_on_tcbs_api.stock_system_v2.schemas import PendingSignal
from trading_on_tcbs_api.stock_system_v2.tools import invoke

from .scanner import ScannerReport, daily_scan

_logger = get_logger("agents.live_trader")


class LiveTradeReport(BaseModel):
    """Aggregate outcome of one live-trade cycle."""

    model_config = ConfigDict(frozen=True)

    captured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    scan: ScannerReport | None = None
    aborted_reason: str | None = Field(None, description="When set, no signals were dispatched.")
    dispatched: list[PendingSignal] = Field(default_factory=list)

    @property
    def n_submitted(self) -> int:
        return sum(1 for p in self.dispatched if p.status == "submitted")

    @property
    def n_failed(self) -> int:
        return sum(1 for p in self.dispatched if p.status in ("failed", "stale"))

    @property
    def n_rejected(self) -> int:
        return sum(1 for p in self.dispatched if p.status == "rejected")

    @property
    def n_expired(self) -> int:
        return sum(1 for p in self.dispatched if p.status == "expired")


async def live_trade_cycle(
    coordinator: HITLCoordinator,
    *,
    scan: ScannerReport | None = None,
    default_volume: int = 100,
    strategies: list[dict] | None = None,
    symbols: list[str] | None = None,
    history_days: int = 365,
) -> LiveTradeReport:
    """Run one live-trade cycle through the supplied coordinator.

    Args:
        coordinator: Pre-wired `HITLCoordinator`. Determines HITL vs auto.
        scan: Optional pre-computed `ScannerReport`. When None the cycle
            runs `daily_scan` itself.
        default_volume: Lot size for every dispatched signal. The Phase-5
            position sizer is expected to replace this in a follow-up.
        strategies / symbols / history_days: Forwarded to `daily_scan`
            when `scan` is None.

    Returns:
        `LiveTradeReport` summarising each dispatched signal's final
        status. Hard caps and re-validation failures show up as `failed`
        or `stale` rows, not exceptions — the audit trail is the source
        of truth.
    """
    # Pre-flight: health must be sane before we dispatch anything.
    health = invoke("health_check").result.status
    if not health.ok:
        log_event(
            _logger, "live_trader.aborted",
            reason="health_check_failed", ok=False,
        )
        return LiveTradeReport(scan=scan, aborted_reason="health_check_failed")

    # Resume any open signals from a prior run BEFORE issuing new ones.
    await coordinator.resume_open_pending()

    if scan is None:
        scan = daily_scan(strategies=strategies, symbols=symbols, history_days=history_days)

    dispatched: list[PendingSignal] = []
    for group in scan.groups:
        for signal in group.rows:
            correlation_id = new_correlation_id(prefix="livecycle")
            try:
                ref_ts = datetime.fromisoformat(signal.date)
            except ValueError:
                # `date` is a date-only string in scan results; coerce to UTC midnight.
                ref_ts = datetime.strptime(signal.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if ref_ts.tzinfo is None:
                ref_ts = ref_ts.replace(tzinfo=timezone.utc)

            result = await coordinator.handle_signal(
                symbol=signal.symbol,
                side=signal.signal,  # type: ignore[arg-type]
                strategy_name=signal.strategy,
                ref_price=signal.price,
                ref_bar_close_ts=ref_ts,
                proposed_volume=default_volume,
                proposed_notional_vnd=int(signal.price * default_volume),
                correlation_id=correlation_id,
            )
            dispatched.append(result)

    log_event(
        _logger, "live_trader.cycle.complete",
        n_dispatched=len(dispatched),
        n_submitted=sum(1 for p in dispatched if p.status == "submitted"),
        n_rejected=sum(1 for p in dispatched if p.status == "rejected"),
        n_failed=sum(1 for p in dispatched if p.status in ("failed", "stale")),
        n_expired=sum(1 for p in dispatched if p.status == "expired"),
    )
    return LiveTradeReport(scan=scan, dispatched=dispatched)
