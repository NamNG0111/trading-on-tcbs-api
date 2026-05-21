"""PendingSignalStore + PendingSignal schema tests (Phase 10 chunk 1)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trading_on_tcbs_api.stock_system_v2.execution.hitl import PendingSignalStore
from trading_on_tcbs_api.stock_system_v2.schemas import (
    OPEN_STATUSES,
    TERMINAL_STATUSES,
    PendingSignal,
    RevalCheck,
    RevalidationResult,
)


# — fixtures —


def _make_signal(
    *,
    symbol: str = "HPG",
    side: str = "BUY",
    timeout: int = 3600,
    strategy: str = "RSIStrategy",
    correlation_id: str = "cycle_test_001",
) -> PendingSignal:
    return PendingSignal.from_scan(
        symbol=symbol,
        side=side,
        strategy_name=strategy,
        ref_price=27_500.0,
        ref_bar_close_ts=datetime(2026, 5, 19, 7, 30, tzinfo=timezone.utc),
        proposed_volume=100,
        proposed_notional_vnd=2_750_000,
        correlation_id=correlation_id,
        timeout_seconds=timeout,
        strategy_params={"period": 14},
    )


def _store(tmp_path: Path) -> PendingSignalStore:
    return PendingSignalStore(path=tmp_path / "pending_signals.jsonl")


# — schema —


def test_pending_signal_status_constants_are_disjoint():
    assert OPEN_STATUSES.isdisjoint(TERMINAL_STATUSES)


def test_from_scan_sets_expiry_relative_to_now():
    s = _make_signal(timeout=60)
    assert (s.expires_at - s.created_at) == timedelta(seconds=60)
    assert not s.is_expired()
    assert s.status == "awaiting"
    assert not s.is_terminal()


def test_is_expired_when_past_deadline():
    s = _make_signal(timeout=60)
    future = s.expires_at + timedelta(seconds=1)
    assert s.is_expired(now=future)


def test_with_status_returns_new_object_with_updated_state():
    s = _make_signal()
    reval = RevalidationResult(
        passed=False,
        checks=[RevalCheck(name="price_drift", passed=False, detail="2.4% drift")],
        reason="price moved",
    )
    s2 = s.with_status("stale", revalidation_result=reval, notes="post-confirm")
    assert s.status == "awaiting"
    assert s2.status == "stale"
    assert s2.is_terminal()
    assert s2.revalidation_result is not None
    assert s2.revalidation_result.passed is False
    assert s2.notes == "post-confirm"
    assert s2.id == s.id  # id is preserved across transitions


# — store: write + read —


def test_append_then_get_returns_same_signal(tmp_path):
    store = _store(tmp_path)
    sig = _make_signal()
    store.append(sig)

    loaded = store.get(sig.id)
    assert loaded is not None
    assert loaded.id == sig.id
    assert loaded.symbol == "HPG"
    assert loaded.status == "awaiting"


def test_get_unknown_id_returns_none(tmp_path):
    store = _store(tmp_path)
    assert store.get("ps_does_not_exist") is None


def test_update_status_appends_new_row_keeps_history(tmp_path):
    store = _store(tmp_path)
    sig = _make_signal()
    store.append(sig)

    updated = store.update_status(sig.id, "confirmed", notes="operator approved")
    assert updated.status == "confirmed"
    assert store.get(sig.id).status == "confirmed"

    # History preserved: at least two rows on disk now.
    all_rows = list(store.iter_all())
    assert len(all_rows) == 2
    assert all_rows[0].status == "awaiting"
    assert all_rows[1].status == "confirmed"


def test_update_status_unknown_id_raises(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(KeyError):
        store.update_status("ps_nope", "confirmed")


# — store: restart recovery —


def test_load_open_returns_only_non_terminal_after_restart(tmp_path):
    store = _store(tmp_path)
    a = _make_signal(symbol="HPG")
    b = _make_signal(symbol="TCB")
    c = _make_signal(symbol="FPT")
    store.append(a)
    store.append(b)
    store.append(c)

    # a confirmed (still open), b submitted (terminal), c rejected (terminal)
    store.update_status(a.id, "confirmed")
    store.update_status(b.id, "submitted")
    store.update_status(c.id, "rejected")

    # Fresh store object on the same file = restart.
    restarted = PendingSignalStore(path=store.path)
    open_signals = restarted.load_open()
    open_ids = {s.id for s in open_signals}
    assert open_ids == {a.id}


def test_load_open_handles_empty_file(tmp_path):
    store = _store(tmp_path)
    assert store.load_open() == []


# — store: expiry sweeper —


def test_expire_overdue_transitions_awaiting_to_expired(tmp_path):
    store = _store(tmp_path)
    fresh = _make_signal(symbol="HPG", timeout=3600)
    stale = _make_signal(symbol="TCB", timeout=1)
    store.append(fresh)
    store.append(stale)

    future = datetime.now(timezone.utc) + timedelta(seconds=10)
    expired = store.expire_overdue(now=future)
    assert len(expired) == 1
    assert expired[0].id == stale.id
    assert expired[0].status == "expired"

    # Idempotent: second sweep finds nothing.
    assert store.expire_overdue(now=future) == []

    # Open set after sweep contains only the still-fresh signal.
    open_ids = {s.id for s in store.load_open()}
    assert open_ids == {fresh.id}


def test_expire_overdue_skips_already_confirmed(tmp_path):
    store = _store(tmp_path)
    sig = _make_signal(timeout=1)
    store.append(sig)
    store.update_status(sig.id, "confirmed")

    future = datetime.now(timezone.utc) + timedelta(seconds=10)
    assert store.expire_overdue(now=future) == []
    # Confirmed remains confirmed (not auto-expired).
    assert store.get(sig.id).status == "confirmed"
