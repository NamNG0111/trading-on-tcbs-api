"""OrderTracker idempotency + recovery tests (Phase 5)."""

from __future__ import annotations

from pathlib import Path

import pytest

from trading_on_tcbs_api.stock_system_v2.exceptions import DuplicateOrderError
from trading_on_tcbs_api.stock_system_v2.execution.order_tracker import OrderTracker
from trading_on_tcbs_api.stock_system_v2.schemas import OrderRequest, OrderResponse


def _ledger(tmp_path: Path) -> str:
    return str(tmp_path / "ledger.csv")


def test_register_pending_persists_and_blocks_duplicates(tmp_path):
    t = OrderTracker(_ledger(tmp_path))
    req = OrderRequest(symbol="HPG", side="BUY", price=28000, volume=100)
    t.register_pending(req)

    with pytest.raises(DuplicateOrderError):
        t.register_pending(req)

    # A second tracker on the same ledger inherits the seen set.
    t2 = OrderTracker(_ledger(tmp_path))
    with pytest.raises(DuplicateOrderError):
        t2.register_pending(req)


def test_recover_open_orders_returns_pending_only(tmp_path):
    t = OrderTracker(_ledger(tmp_path))

    a = OrderRequest(symbol="HPG", side="BUY", price=28000, volume=100)
    b = OrderRequest(symbol="TCB", side="BUY", price=24000, volume=100)
    c = OrderRequest(symbol="FPT", side="BUY", price=110000, volume=100)

    t.register_pending(a)
    t.register_pending(b)
    t.register_pending(c)

    # `a` filled, `c` rejected; `b` remains pending.
    t.log_order(
        OrderResponse(client_order_id=a.client_order_id, status="FILLED",
                      filled_volume=100, avg_fill_price=28000, broker_order_id="bo_a"),
        "HPG", "BUY", 28000, 100,
    )
    t.log_order(
        OrderResponse(client_order_id=c.client_order_id, status="REJECTED",
                      note="price band"),
        "FPT", "BUY", 110000, 100,
    )

    open_orders = t.recover_open_orders()
    assert len(open_orders) == 1
    assert open_orders[0]["client_order_id"] == b.client_order_id
    assert open_orders[0]["status"] == "PENDING"


def test_recover_after_simulated_crash(tmp_path):
    """Crash between register_pending and log_order → recovery sees the PENDING row."""
    ledger = _ledger(tmp_path)
    t = OrderTracker(ledger)
    req = OrderRequest(symbol="HPG", side="BUY", price=28000, volume=100)
    t.register_pending(req)
    # Simulate a process death here — no log_order call.
    del t

    fresh = OrderTracker(ledger)
    open_orders = fresh.recover_open_orders()
    assert len(open_orders) == 1
    assert open_orders[0]["client_order_id"] == req.client_order_id


def test_log_order_typed_response(tmp_path):
    t = OrderTracker(_ledger(tmp_path))
    req = OrderRequest(symbol="HPG", side="BUY", price=28000, volume=100)
    t.register_pending(req)
    resp = OrderResponse(
        client_order_id=req.client_order_id,
        broker_order_id="bo_123",
        status="FILLED",
        filled_volume=100,
        avg_fill_price=28000,
    )
    t.log_order(resp, "HPG", "BUY", 28000, 100)

    history = t.get_history()
    assert len(history) == 2  # PENDING + FILLED
    assert "FILLED" in set(history["status"].astype(str))


def test_log_order_legacy_dict_still_works(tmp_path):
    t = OrderTracker(_ledger(tmp_path))
    legacy = {"order_id": "x", "status": "FILLED", "note": "ok"}
    # Legacy callers don't necessarily call register_pending — log_order
    # still appends a row.
    t.log_order(legacy, "HPG", "BUY", 28000, 100)
    assert len(t.get_history()) == 1
