"""Smoke + invariant tests for Phase-3 schemas."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from trading_on_tcbs_api.stock_system_v2.schemas import (
    AccountSnapshot,
    MarketContext,
    OrderRequest,
    OrderResponse,
    Position,
    RiskCheckFinding,
    RiskCheckResult,
    ScanResult,
    Signal,
)


def test_signal_from_code_round_trip():
    assert Signal.from_code(1).action == "BUY"
    assert Signal.from_code(-1).action == "SELL"
    assert Signal.from_code(0).action == "HOLD"


def test_order_request_generates_unique_client_id():
    a = OrderRequest(symbol="HPG", side="BUY", price=28000, volume=100)
    b = OrderRequest(symbol="HPG", side="BUY", price=28000, volume=100)
    assert a.client_order_id != b.client_order_id
    assert a.client_order_id.startswith("co_")


def test_order_request_rejects_bad_input():
    with pytest.raises(ValidationError):
        OrderRequest(symbol="HPG", side="BUY", price=-1, volume=100)
    with pytest.raises(ValidationError):
        OrderRequest(symbol="HPG", side="BUY", price=28000, volume=0)
    with pytest.raises(ValidationError):
        OrderRequest(symbol="", side="BUY", price=28000, volume=100)


def test_position_marks_to_market():
    p = Position(symbol="HPG", quantity=100, avg_cost=28000, market_price=29000)
    assert p.market_value == 100 * 29000
    assert p.unrealized_pnl == (29000 - 28000) * 100


def test_position_handles_missing_mark():
    p = Position(symbol="HPG", quantity=100, avg_cost=28000, market_price=None)
    assert p.market_value == 0.0
    assert p.unrealized_pnl == 0.0


def test_account_snapshot_equity():
    snap = AccountSnapshot(
        cash=10_000_000,
        buying_power=10_000_000,
        positions=[Position(symbol="HPG", quantity=100, avg_cost=28000, market_price=29000)],
        is_mock=True,
    )
    assert snap.equity == 10_000_000 + 100 * 29000


def test_risk_check_freshness_and_violations():
    finding = RiskCheckFinding(rule="price_band", severity="BLOCK", message="too far from last close")
    chk = RiskCheckResult(passed=False, request_hash="abc123", findings=[finding])
    assert chk.is_fresh()
    assert chk.violations == ["price_band"]

    expired = RiskCheckResult(
        passed=True,
        request_hash="x",
        issued_at=datetime.now(timezone.utc) - timedelta(seconds=120),
        ttl_seconds=60,
    )
    assert not expired.is_fresh()


def test_market_context_defaults():
    ctx = MarketContext()
    assert ctx.lot_size == 100
    assert ctx.last_close_prices == {}


def test_scan_result_typed():
    r = ScanResult(
        date="2025-01-15",
        symbol="HPG",
        strategy="SimpleMA",
        signal="BUY",
        price=28000.0,
        live_price=28100.0,
        signal_context={"rsi_14": 35.2},
    )
    assert r.signal_context["rsi_14"] == pytest.approx(35.2)


def test_order_response_default_status():
    resp = OrderResponse(client_order_id="co_x", status="ACCEPTED")
    assert resp.filled_volume == 0
    assert resp.broker_order_id is None
