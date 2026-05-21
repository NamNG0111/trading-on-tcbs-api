"""HITLCoordinator tests (Phase 10 chunk 4).

Covers:
  - hitl path: yes / no / timeout
  - auto path: skips channel, still revalidates
  - revalidation fails → stale (no order placed)
  - validator BLOCK → failed
  - broker REJECTED → failed
  - restart: open signals replayed via channel
  - happy-path metrics + decision audit

The coordinator's deps are all swappable; tests inject fakes for the
channel, revalidator, validator, order_manager, and providers so we
never hit network / disk-heavy paths.
"""

from __future__ import annotations

import asyncio
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
from trading_on_tcbs_api.stock_system_v2.exceptions import OrderRejectedError
from trading_on_tcbs_api.stock_system_v2.schemas import (
    AccountSnapshot,
    MarketContext,
    OrderResponse,
    PendingSignal,
    RevalCheck,
    RevalidationResult,
    RiskCheckFinding,
    RiskCheckResult,
)


# — fakes —


class FakeChannel:
    def __init__(self, decision: str = "yes", *, raise_on_request: Exception | None = None):
        self.decision = decision
        self.raise_on_request = raise_on_request
        self.requests: list[PendingSignal] = []
        self.outcomes: list[tuple[str, str, str | None]] = []  # (id, outcome, details)
        self.replays: list[list[PendingSignal]] = []

    async def request(self, pending: PendingSignal) -> ConfirmationResponse:
        self.requests.append(pending)
        if self.raise_on_request is not None:
            raise self.raise_on_request
        return ConfirmationResponse(signal_id=pending.id, decision=self.decision)

    async def notify_outcome(self, pending, outcome, details=None):
        self.outcomes.append((pending.id, outcome, details))

    async def replay_pending(self, pendings):
        self.replays.append(list(pendings))


class FakeRevalidator:
    def __init__(self, passed: bool = True, *, fresh_price: float = 27_500.0, reason: str | None = None):
        self.passed = passed
        self.fresh_price = fresh_price
        self.reason = reason
        self.calls: list[PendingSignal] = []

    def check(self, pending: PendingSignal) -> RevalidationResult:
        self.calls.append(pending)
        return RevalidationResult(
            passed=self.passed,
            checks=[RevalCheck(name="freshness", passed=self.passed, detail="stub")],
            fresh_price=self.fresh_price if self.passed else None,
            reason=self.reason if not self.passed else None,
        )


class FakeValidator:
    def __init__(self, passed: bool = True):
        self.passed = passed
        self.calls = []

    def validate(self, req, *, account, market, daily_stats=None) -> RiskCheckResult:
        self.calls.append(req)
        findings = (
            []
            if self.passed
            else [RiskCheckFinding(rule="universe_membership", severity="BLOCK", message="blocked")]
        )
        return RiskCheckResult(
            request_hash="hash",  # validator/order_manager wiring is not under test here
            passed=self.passed,
            findings=findings,
        )


class FakeOrderManager:
    def __init__(self, response: OrderResponse | None = None, *, raise_exc: Exception | None = None):
        self.response = response
        self.raise_exc = raise_exc
        self.calls = []

    def place_order(self, *, request, risk_check):
        self.calls.append((request, risk_check))
        if self.raise_exc is not None:
            raise self.raise_exc
        if self.response is not None:
            return self.response
        return OrderResponse(
            client_order_id=request.client_order_id,
            broker_order_id="bo_test",
            status="ACCEPTED",
            filled_volume=0,
        )


def _account() -> AccountSnapshot:
    return AccountSnapshot(cash=100_000_000, buying_power=100_000_000, is_mock=True)


def _market(symbol: str) -> MarketContext:
    return MarketContext(last_close_prices={symbol: 27_500.0}, lot_size=100)


def _make_store(tmp_path: Path) -> PendingSignalStore:
    return PendingSignalStore(path=tmp_path / "pending.jsonl")


def _build(
    *,
    tmp_path,
    channel=None,
    revalidator=None,
    validator=None,
    order_manager=None,
    trading_mode="hitl",
    timeout=3600,
):
    return HITLCoordinator(
        channel=channel or FakeChannel(),
        revalidator=revalidator or FakeRevalidator(),
        validator=validator or FakeValidator(),
        order_manager=order_manager or FakeOrderManager(),
        store=_make_store(tmp_path),
        account_provider=_account,
        market_provider=_market,
        trading_mode=trading_mode,
        confirmation_timeout_sec=timeout,
    )


def _dispatch(coord: HITLCoordinator, symbol="HPG") -> PendingSignal:
    return asyncio.run(
        coord.handle_signal(
            symbol=symbol,
            side="BUY",
            strategy_name="rsi",
            strategy_params={"period": 14},
            ref_price=27_500.0,
            ref_bar_close_ts=datetime(2026, 5, 19, 7, 30, tzinfo=timezone.utc),
            proposed_volume=100,
            proposed_notional_vnd=2_750_000,
            correlation_id="cycle_test",
        )
    )


# — construction —


def test_invalid_trading_mode_rejected(tmp_path):
    with pytest.raises(ValueError):
        _build(tmp_path=tmp_path, trading_mode="weird")  # type: ignore[arg-type]


def test_invalid_timeout_rejected(tmp_path):
    with pytest.raises(ValueError):
        _build(tmp_path=tmp_path, timeout=0)


# — HITL happy path —


def test_hitl_yes_revalidation_passes_order_submitted(tmp_path):
    chan = FakeChannel(decision="yes")
    om = FakeOrderManager()
    coord = _build(tmp_path=tmp_path, channel=chan, order_manager=om)

    final = _dispatch(coord)

    assert final.status == "submitted"
    assert len(om.calls) == 1
    placed_req, _ = om.calls[0]
    # Revalidator's fresh_price is used as the order price (drift-adjusted intent).
    assert placed_req.price == 27_500.0
    # Channel saw the prompt + the submitted outcome.
    assert len(chan.requests) == 1
    outcomes = [o for o in chan.outcomes if o[1] == "submitted"]
    assert len(outcomes) == 1


def test_hitl_no_terminates_without_placement(tmp_path):
    chan = FakeChannel(decision="no")
    om = FakeOrderManager()
    coord = _build(tmp_path=tmp_path, channel=chan, order_manager=om)

    final = _dispatch(coord)

    assert final.status == "rejected"
    assert om.calls == []
    assert any(o[1] == "rejected" for o in chan.outcomes)


def test_hitl_timeout_marks_expired(tmp_path):
    chan = FakeChannel(decision="timeout")
    coord = _build(tmp_path=tmp_path, channel=chan)
    final = _dispatch(coord)
    assert final.status == "expired"
    assert any(o[1] == "expired" for o in chan.outcomes)


def test_channel_exception_treated_as_no(tmp_path):
    """Unrecoverable channel failure must NOT silently approve."""
    chan = FakeChannel(raise_on_request=RuntimeError("telegram down"))
    om = FakeOrderManager()
    coord = _build(tmp_path=tmp_path, channel=chan, order_manager=om)
    final = _dispatch(coord)
    assert final.status == "rejected"
    assert om.calls == []


# — Auto mode —


def test_auto_mode_skips_channel_request(tmp_path):
    chan = FakeChannel(decision="no")  # would reject if asked
    coord = _build(tmp_path=tmp_path, channel=chan, trading_mode="auto")
    final = _dispatch(coord)
    # Channel.request was NOT called.
    assert chan.requests == []
    # Order placed anyway.
    assert final.status == "submitted"


def test_auto_mode_still_revalidates(tmp_path):
    rev = FakeRevalidator(passed=False, reason="signal vanished")
    coord = _build(tmp_path=tmp_path, revalidator=rev, trading_mode="auto")
    final = _dispatch(coord)
    assert final.status == "stale"
    assert len(rev.calls) == 1


# — Stale / failed branches —


def test_revalidation_fail_marks_stale_no_order_placed(tmp_path):
    rev = FakeRevalidator(passed=False, reason="price drift 3.4%")
    om = FakeOrderManager()
    coord = _build(tmp_path=tmp_path, revalidator=rev, order_manager=om)
    final = _dispatch(coord)
    assert final.status == "stale"
    assert om.calls == []
    assert final.revalidation_result is not None
    assert "price drift" in (final.notes or "")


def test_validator_block_marks_failed(tmp_path):
    val = FakeValidator(passed=False)
    om = FakeOrderManager()
    coord = _build(tmp_path=tmp_path, validator=val, order_manager=om)
    final = _dispatch(coord)
    assert final.status == "failed"
    assert om.calls == []


def test_broker_rejected_status_marks_failed(tmp_path):
    rejected = OrderResponse(
        client_order_id="dummy",
        status="REJECTED",
        note="broker said no",
    )
    om = FakeOrderManager(response=rejected)
    coord = _build(tmp_path=tmp_path, order_manager=om)
    final = _dispatch(coord)
    assert final.status == "failed"
    assert "broker said no" in (final.notes or "")


def test_order_manager_exception_marks_failed(tmp_path):
    om = FakeOrderManager(raise_exc=OrderRejectedError("kill switch on"))
    coord = _build(tmp_path=tmp_path, order_manager=om)
    final = _dispatch(coord)
    assert final.status == "failed"


# — Persistence + restart —


def test_handle_signal_persists_to_store_for_restart(tmp_path):
    chan = FakeChannel(decision="yes")
    coord = _build(tmp_path=tmp_path, channel=chan)
    final = _dispatch(coord)
    # Same file → fresh store sees the final state.
    other = PendingSignalStore(path=coord.store.path)
    loaded = other.get(final.id)
    assert loaded is not None
    assert loaded.status == "submitted"


def test_resume_open_pending_replays_via_channel(tmp_path):
    # Seed two open signals on disk, then build a fresh coordinator.
    seed_store = _make_store(tmp_path)
    a = PendingSignal.from_scan(
        symbol="HPG", side="BUY", strategy_name="rsi",
        ref_price=27_500.0,
        ref_bar_close_ts=datetime(2026, 5, 19, 7, 30, tzinfo=timezone.utc),
        proposed_volume=100, proposed_notional_vnd=2_750_000,
        correlation_id="cycle_a", timeout_seconds=3600,
    )
    b = PendingSignal.from_scan(
        symbol="TCB", side="BUY", strategy_name="rsi",
        ref_price=24_000.0,
        ref_bar_close_ts=datetime(2026, 5, 19, 7, 30, tzinfo=timezone.utc),
        proposed_volume=100, proposed_notional_vnd=2_400_000,
        correlation_id="cycle_b", timeout_seconds=3600,
    )
    seed_store.append(a)
    seed_store.append(b)

    chan = FakeChannel()
    coord = HITLCoordinator(
        channel=chan,
        revalidator=FakeRevalidator(),
        validator=FakeValidator(),
        order_manager=FakeOrderManager(),
        store=seed_store,
        account_provider=_account,
        market_provider=_market,
    )
    resumed = asyncio.run(coord.resume_open_pending())
    assert {s.id for s in resumed} == {a.id, b.id}
    assert len(chan.replays) == 1
    assert {s.id for s in chan.replays[0]} == {a.id, b.id}


def test_resume_expires_overdue_first(tmp_path):
    seed_store = _make_store(tmp_path)
    stale_sig = PendingSignal.from_scan(
        symbol="HPG", side="BUY", strategy_name="rsi",
        ref_price=27_500.0,
        ref_bar_close_ts=datetime(2026, 5, 19, 7, 30, tzinfo=timezone.utc),
        proposed_volume=100, proposed_notional_vnd=2_750_000,
        correlation_id="cycle_old", timeout_seconds=1,
    )
    seed_store.append(stale_sig)
    # Force-expire by mutating in place via update with past expires_at.
    expired_copy = stale_sig.model_copy(
        update={"expires_at": datetime.now(timezone.utc).replace(year=2020)}
    )
    seed_store.append(expired_copy)  # add the past-expiry version

    chan = FakeChannel()
    coord = HITLCoordinator(
        channel=chan,
        revalidator=FakeRevalidator(),
        validator=FakeValidator(),
        order_manager=FakeOrderManager(),
        store=seed_store,
        account_provider=_account,
        market_provider=_market,
    )
    resumed = asyncio.run(coord.resume_open_pending())
    # Stale signal was swept; nothing left open.
    assert resumed == []
    assert seed_store.get(stale_sig.id).status == "expired"
