"""OrderManager safety + token gating tests (Phase 5)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trading_on_tcbs_api.stock_system_v2.exceptions import (
    DuplicateOrderError,
    OrderRejectedError,
    RiskLimitViolatedError,
)
from trading_on_tcbs_api.stock_system_v2.execution.order_manager import OrderManager
from trading_on_tcbs_api.stock_system_v2.execution.order_tracker import OrderTracker
from trading_on_tcbs_api.stock_system_v2.execution.pre_trade_validator import (
    request_hash,
)
from trading_on_tcbs_api.stock_system_v2.schemas import (
    OrderRequest,
    RiskCheckResult,
)


def _tracker(tmp_path: Path) -> OrderTracker:
    return OrderTracker(str(tmp_path / "ledger.csv"))


class _FakeBroker:
    """Async fake mirroring `StockTradingClient.place_stock_order`."""

    def __init__(self, order_id="bo_999", raises=None):
        self._order_id = order_id
        self._raises = raises
        self.calls: list[dict] = []

    async def place_stock_order(self, *, symbol, side, quantity, price, order_type):
        self.calls.append(dict(symbol=symbol, side=side, quantity=quantity, price=price, order_type=order_type))
        if self._raises is not None:
            raise self._raises
        return self._order_id

    async def cancel_stock_order(self, order_id):
        return True


def _fresh_token(req: OrderRequest, *, passed=True) -> RiskCheckResult:
    return RiskCheckResult(passed=passed, request_hash=request_hash(req), findings=[])


def test_safe_mode_fills_and_persists(tmp_path):
    om = OrderManager(auth=None, safe_mode=True, tracker=_tracker(tmp_path))
    req = OrderRequest(symbol="HPG", side="BUY", price=28000, volume=100)
    resp = om.place_order(request=req)
    assert resp.status == "FILLED"
    assert resp.broker_order_id and resp.broker_order_id.startswith("mock_")
    assert resp.filled_volume == 100


def test_kill_switch_blocks_every_order(tmp_path):
    om = OrderManager(auth=None, safe_mode=True, execution_disabled=True, tracker=_tracker(tmp_path))
    req = OrderRequest(symbol="HPG", side="BUY", price=28000, volume=100)
    resp = om.place_order(request=req)
    assert resp.status == "REJECTED"
    assert "EXECUTION_DISABLED" in (resp.note or "")


def test_live_mode_requires_token(tmp_path):
    om = OrderManager(auth="fake", safe_mode=False, tracker=_tracker(tmp_path), broker_client=_FakeBroker())
    req = OrderRequest(symbol="HPG", side="BUY", price=28000, volume=100)
    with pytest.raises(RiskLimitViolatedError):
        om.place_order(request=req)


def test_live_mode_rejects_failed_token(tmp_path):
    om = OrderManager(auth="fake", safe_mode=False, tracker=_tracker(tmp_path), broker_client=_FakeBroker())
    req = OrderRequest(symbol="HPG", side="BUY", price=28000, volume=100)
    bad = _fresh_token(req, passed=False)
    with pytest.raises(RiskLimitViolatedError):
        om.place_order(request=req, risk_check=bad)


def test_live_mode_rejects_stale_token(tmp_path):
    om = OrderManager(auth="fake", safe_mode=False, tracker=_tracker(tmp_path), broker_client=_FakeBroker())
    req = OrderRequest(symbol="HPG", side="BUY", price=28000, volume=100)
    stale = RiskCheckResult(
        passed=True,
        request_hash=request_hash(req),
        issued_at=datetime.now(timezone.utc) - timedelta(seconds=120),
        ttl_seconds=60,
    )
    with pytest.raises(RiskLimitViolatedError):
        om.place_order(request=req, risk_check=stale)


def test_live_mode_rejects_hash_mismatch(tmp_path):
    om = OrderManager(auth="fake", safe_mode=False, tracker=_tracker(tmp_path), broker_client=_FakeBroker())
    req = OrderRequest(symbol="HPG", side="BUY", price=28000, volume=100)
    other = OrderRequest(symbol="HPG", side="BUY", price=29000, volume=100)
    token = _fresh_token(other)
    with pytest.raises(RiskLimitViolatedError):
        om.place_order(request=req, risk_check=token)


def test_live_mode_happy_path(tmp_path):
    broker = _FakeBroker(order_id="bo_777")
    tr = _tracker(tmp_path)
    om = OrderManager(auth="fake", safe_mode=False, tracker=tr, broker_client=broker)
    req = OrderRequest(symbol="HPG", side="BUY", price=28000, volume=100)
    resp = om.place_order(request=req, risk_check=_fresh_token(req))
    assert resp.status == "ACCEPTED"
    assert resp.broker_order_id == "bo_777"
    assert len(broker.calls) == 1
    # Tracker should have a PENDING + ACCEPTED row.
    statuses = set(tr.get_history()["status"].astype(str))
    assert {"PENDING", "ACCEPTED"} <= statuses


def test_live_broker_failure_wrapped_as_rejected(tmp_path):
    broker = _FakeBroker(raises=RuntimeError("network down"))
    om = OrderManager(auth="fake", safe_mode=False, tracker=_tracker(tmp_path), broker_client=broker)
    req = OrderRequest(symbol="HPG", side="BUY", price=28000, volume=100)
    with pytest.raises(OrderRejectedError):
        om.place_order(request=req, risk_check=_fresh_token(req))


def test_duplicate_client_order_id_rejected(tmp_path):
    tr = _tracker(tmp_path)
    om = OrderManager(auth=None, safe_mode=True, tracker=tr)
    req = OrderRequest(symbol="HPG", side="BUY", price=28000, volume=100)
    om.place_order(request=req)
    with pytest.raises(DuplicateOrderError):
        om.place_order(request=req)
