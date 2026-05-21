"""HITL tools smoke tests (Phase 10 chunk 6).

Exercises every tool through `tools.invoke()` only — no internal imports
inside the workflow body — so this doubles as a contract test for the
MCP server path.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from trading_on_tcbs_api.stock_system_v2.execution.hitl import (
    HITLCoordinator,
    PendingSignalStore,
)
from trading_on_tcbs_api.stock_system_v2.execution.hitl.channels import (
    ConfirmationResponse,
)
from trading_on_tcbs_api.stock_system_v2.schemas import (
    AccountSnapshot,
    MarketContext,
    OrderResponse,
    PendingSignal,
    RevalCheck,
    RevalidationResult,
    RiskCheckResult,
)
from trading_on_tcbs_api.stock_system_v2.tools import ToolError, invoke
from trading_on_tcbs_api.stock_system_v2.tools.context import (
    ToolContext,
    clear_context,
    set_context,
)


# — fakes (mirror coordinator suite) —


class _Channel:
    async def request(self, p):
        return ConfirmationResponse(signal_id=p.id, decision="yes")

    async def notify_outcome(self, *a, **kw):
        pass

    async def replay_pending(self, *a, **kw):
        pass


class _Reval:
    def check(self, p):
        return RevalidationResult(
            passed=True,
            checks=[RevalCheck(name="freshness", passed=True, detail="stub")],
            fresh_price=p.ref_price,
        )


class _Val:
    def validate(self, req, *, account, market, daily_stats=None):
        return RiskCheckResult(request_hash="h", passed=True)


class _OM:
    def place_order(self, *, request, risk_check):
        return OrderResponse(
            client_order_id=request.client_order_id,
            broker_order_id="bo_test",
            status="ACCEPTED",
        )


@pytest.fixture
def wired_context(tmp_path: Path):
    """Build a ToolContext with a real HITL coordinator + fakes for everything else."""
    store = PendingSignalStore(path=tmp_path / "pending.jsonl")
    coord = HITLCoordinator(
        channel=_Channel(),
        revalidator=_Reval(),
        validator=_Val(),
        order_manager=_OM(),
        store=store,
        account_provider=lambda: AccountSnapshot(cash=100_000_000, buying_power=100_000_000, is_mock=True),
        market_provider=lambda s: MarketContext(last_close_prices={s: 27_500.0}, lot_size=100),
    )
    ctx = ToolContext(
        settings=None,  # not needed for these tools
        data_provider=None,  # type: ignore[arg-type]
        indicator_engine=None,  # type: ignore[arg-type]
        account=None,  # type: ignore[arg-type]
        order_manager=None,  # type: ignore[arg-type]
        order_tracker=None,  # type: ignore[arg-type]
        validator=None,  # type: ignore[arg-type]
        hitl_coordinator=coord,
        pending_signal_store=store,
    )
    set_context(ctx)
    yield coord, store
    clear_context()


def _seed_pending(store: PendingSignalStore, *, symbol="HPG", signal_id=None) -> PendingSignal:
    sig = PendingSignal.from_scan(
        symbol=symbol, side="BUY", strategy_name="rsi",
        ref_price=27_500.0,
        ref_bar_close_ts=datetime(2026, 5, 19, tzinfo=timezone.utc),
        proposed_volume=100, proposed_notional_vnd=2_750_000,
        correlation_id="cycle_seed", timeout_seconds=3600,
    )
    if signal_id is not None:
        sig = sig.model_copy(update={"id": signal_id})
    store.append(sig)
    return sig


# — list_pending_signals —


def test_list_pending_signals_returns_only_open_by_default(wired_context):
    _, store = wired_context
    a = _seed_pending(store, symbol="HPG", signal_id="ps_open")
    b = _seed_pending(store, symbol="TCB", signal_id="ps_done")
    store.update_status(b.id, "submitted")

    resp = invoke("list_pending_signals", {})
    ids = [s.id for s in resp.result.signals]
    assert ids == ["ps_open"]
    assert resp.result.open_count == 1


def test_list_pending_signals_include_terminal(wired_context):
    _, store = wired_context
    _seed_pending(store, symbol="HPG", signal_id="ps_a")
    b = _seed_pending(store, symbol="TCB", signal_id="ps_b")
    store.update_status(b.id, "submitted")

    resp = invoke("list_pending_signals", {"include_terminal": True})
    ids = sorted(s.id for s in resp.result.signals)
    assert ids == ["ps_a", "ps_b"]


def test_list_pending_signals_respects_limit(wired_context):
    _, store = wired_context
    for i in range(5):
        _seed_pending(store, signal_id=f"ps_{i}")

    resp = invoke("list_pending_signals", {"limit": 2})
    assert len(resp.result.signals) == 2


# — confirm_signal —


def test_confirm_signal_drives_full_pipeline(wired_context):
    _, store = wired_context
    sig = _seed_pending(store, signal_id="ps_confirm")

    resp = invoke("confirm_signal", {"signal_id": sig.id})
    out = resp.result.signal
    assert out.id == sig.id
    assert out.status == "submitted"


def test_confirm_signal_unknown_id_raises_invalid_params(wired_context):
    with pytest.raises(ToolError) as excinfo:
        invoke("confirm_signal", {"signal_id": "ps_does_not_exist"})
    assert excinfo.value.code == "INVALID_PARAMS"


def test_confirm_signal_idempotent_on_terminal(wired_context):
    _, store = wired_context
    sig = _seed_pending(store, signal_id="ps_done")
    store.update_status(sig.id, "rejected")

    resp = invoke("confirm_signal", {"signal_id": sig.id})
    # Already terminal — confirm returns the row unchanged.
    assert resp.result.signal.status == "rejected"


# — reject_signal —


def test_reject_signal_marks_rejected(wired_context):
    _, store = wired_context
    sig = _seed_pending(store, signal_id="ps_reject")
    resp = invoke("reject_signal", {"signal_id": sig.id, "reason": "not now"})
    assert resp.result.signal.status == "rejected"


def test_reject_signal_unknown_id_raises(wired_context):
    with pytest.raises(ToolError) as excinfo:
        invoke("reject_signal", {"signal_id": "ps_nope"})
    assert excinfo.value.code == "INVALID_PARAMS"


# — set_trading_mode —


def test_set_trading_mode_requires_confirm_flag(wired_context):
    coord, _ = wired_context
    assert coord.trading_mode == "hitl"
    resp = invoke("set_trading_mode", {"mode": "auto"})  # confirm omitted
    assert resp.result.applied is False
    assert resp.result.current == "hitl"
    # Coord unchanged.
    assert coord.trading_mode == "hitl"


def test_set_trading_mode_applies_when_confirmed(wired_context):
    coord, _ = wired_context
    resp = invoke("set_trading_mode", {"mode": "auto", "confirm": True})
    assert resp.result.applied is True
    assert resp.result.previous == "hitl"
    assert resp.result.current == "auto"
    assert coord.trading_mode == "auto"


# — registration —


def test_hitl_tools_are_registered():
    """`tools/__init__.py` imports `handlers/hitl` so the registry sees them."""
    from trading_on_tcbs_api.stock_system_v2.tools import TOOLS
    for name in ("list_pending_signals", "confirm_signal", "reject_signal", "set_trading_mode"):
        assert name in TOOLS, f"missing tool: {name}"
    # Only read-only one:
    assert TOOLS["list_pending_signals"].side_effecting is False
    assert TOOLS["confirm_signal"].side_effecting is True
    assert TOOLS["reject_signal"].side_effecting is True
    assert TOOLS["set_trading_mode"].side_effecting is True
