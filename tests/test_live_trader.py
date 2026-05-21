"""Live trader agent tests (Phase 10 chunk 5)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from trading_on_tcbs_api.stock_system_v2.agents.live_trader import (
    LiveTradeReport,
    live_trade_cycle,
)
from trading_on_tcbs_api.stock_system_v2.agents.scanner import ScanGroup, ScannerReport
from trading_on_tcbs_api.stock_system_v2.execution.hitl import (
    HITLCoordinator,
    PendingSignalStore,
)
from trading_on_tcbs_api.stock_system_v2.execution.hitl.channels import (
    ConfirmationResponse,
)
from trading_on_tcbs_api.stock_system_v2.schemas import (
    AccountSnapshot,
    HealthCheck,
    HealthStatus,
    MarketContext,
    OrderResponse,
    PendingSignal,
    RevalCheck,
    RevalidationResult,
    RiskCheckResult,
    ScanResult,
)
from trading_on_tcbs_api.stock_system_v2.tools.handlers.health import HealthCheckOut
from trading_on_tcbs_api.stock_system_v2.tools.response import ToolResponse


# — fakes (mirror those in test_hitl_coordinator) —


class _Channel:
    def __init__(self, decision="yes"):
        self.decision = decision

    async def request(self, pending):
        return ConfirmationResponse(signal_id=pending.id, decision=self.decision)

    async def notify_outcome(self, *_a, **_kw):
        pass

    async def replay_pending(self, *_a, **_kw):
        pass


class _Reval:
    def check(self, pending):
        return RevalidationResult(
            passed=True,
            checks=[RevalCheck(name="freshness", passed=True, detail="stub")],
            fresh_price=pending.ref_price,
        )


class _Val:
    def validate(self, req, *, account, market, daily_stats=None):
        return RiskCheckResult(request_hash="h", passed=True, findings=[])


class _OM:
    def __init__(self):
        self.placed = []

    def place_order(self, *, request, risk_check):
        self.placed.append(request)
        return OrderResponse(
            client_order_id=request.client_order_id,
            broker_order_id="bo_test",
            status="ACCEPTED",
        )


def _build_coord(tmp_path: Path, *, channel=None) -> HITLCoordinator:
    return HITLCoordinator(
        channel=channel or _Channel("yes"),
        revalidator=_Reval(),
        validator=_Val(),
        order_manager=_OM(),
        store=PendingSignalStore(path=tmp_path / "pending.jsonl"),
        account_provider=lambda: AccountSnapshot(cash=100_000_000, buying_power=100_000_000, is_mock=True),
        market_provider=lambda sym: MarketContext(last_close_prices={sym: 27_500.0}, lot_size=100),
    )


def _make_scan_report(*, n_signals: int = 1) -> ScannerReport:
    rows = [
        ScanResult(
            date="2026-05-19",
            symbol=f"SYM{i}",
            strategy="rsi",
            signal="BUY",
            price=27_500.0 + i,
        )
        for i in range(n_signals)
    ]
    groups = [ScanGroup(strategy="rsi", side="BUY", n_signals=n_signals, symbols=[r.symbol for r in rows], rows=rows)]
    return ScannerReport(
        n_symbols=n_signals,
        n_strategies=1,
        n_signals=n_signals,
        groups=groups,
        headline="test scan",
    )


def _health_ok():
    return ToolResponse(
        result=HealthCheckOut(
            status=HealthStatus(
                ok=True,
                auth_valid=True,
                checks=[HealthCheck(name="all", status="ok", note="green")],
            ),
        ),
        correlation_id="test",
    )


def _health_bad():
    return ToolResponse(
        result=HealthCheckOut(
            status=HealthStatus(
                ok=False,
                auth_valid=False,
                checks=[HealthCheck(name="auth", status="fail", note="token expired")],
            ),
        ),
        correlation_id="test",
    )


# — tests —


def test_aborts_when_health_check_fails(tmp_path):
    coord = _build_coord(tmp_path)
    with patch("trading_on_tcbs_api.stock_system_v2.agents.live_trader.invoke", return_value=_health_bad()):
        report = asyncio.run(live_trade_cycle(coord, scan=_make_scan_report()))
    assert isinstance(report, LiveTradeReport)
    assert report.aborted_reason == "health_check_failed"
    assert report.dispatched == []


def test_dispatches_each_signal_through_coordinator(tmp_path):
    coord = _build_coord(tmp_path)
    scan = _make_scan_report(n_signals=2)
    with patch("trading_on_tcbs_api.stock_system_v2.agents.live_trader.invoke", return_value=_health_ok()):
        report = asyncio.run(live_trade_cycle(coord, scan=scan))
    assert len(report.dispatched) == 2
    assert all(isinstance(p, PendingSignal) for p in report.dispatched)
    assert report.n_submitted == 2
    assert report.aborted_reason is None


def test_resumes_open_pending_before_dispatch(tmp_path):
    coord = _build_coord(tmp_path)
    # Pre-seed an open pending signal.
    pre = PendingSignal.from_scan(
        symbol="OLD", side="BUY", strategy_name="rsi",
        ref_price=10_000.0,
        ref_bar_close_ts=datetime(2026, 5, 19, tzinfo=timezone.utc),
        proposed_volume=100, proposed_notional_vnd=1_000_000,
        correlation_id="cycle_old", timeout_seconds=3600,
    )
    coord.store.append(pre)

    replays: list[list] = []

    async def replay_pending(pendings):
        replays.append(list(pendings))

    coord.channel.replay_pending = replay_pending  # type: ignore[assignment]

    with patch("trading_on_tcbs_api.stock_system_v2.agents.live_trader.invoke", return_value=_health_ok()):
        asyncio.run(live_trade_cycle(coord, scan=_make_scan_report(n_signals=0)))

    assert len(replays) == 1
    assert any(p.id == pre.id for p in replays[0])


def test_report_status_counters(tmp_path):
    coord = _build_coord(tmp_path)
    # Build a coordinator whose channel says "no" → all dispatched signals get `rejected`.
    coord.channel = _Channel("no")  # type: ignore[assignment]
    scan = _make_scan_report(n_signals=3)
    with patch("trading_on_tcbs_api.stock_system_v2.agents.live_trader.invoke", return_value=_health_ok()):
        report = asyncio.run(live_trade_cycle(coord, scan=scan))
    assert report.n_rejected == 3
    assert report.n_submitted == 0
