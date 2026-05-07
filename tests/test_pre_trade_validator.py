"""Pre-trade validator tests (Phase 5)."""

from __future__ import annotations

import pytest

from trading_on_tcbs_api.stock_system_v2.execution.pre_trade_validator import (
    PreTradeValidator,
    ValidatorConfig,
    request_hash,
)
from trading_on_tcbs_api.stock_system_v2.schemas import (
    AccountSnapshot,
    MarketContext,
    OrderRequest,
    Position,
)


def _account(cash=100_000_000.0, positions=None):
    return AccountSnapshot(
        cash=cash,
        buying_power=cash,
        positions=positions or [],
        is_mock=True,
    )


def _market(symbol="HPG", price=28_000.0):
    return MarketContext(last_close_prices={symbol: price}, lot_size=100)


def _validator(**cfg):
    return PreTradeValidator(
        config=ValidatorConfig(**cfg) if cfg else None,
        universe=("HPG", "TCB", "FPT"),
    )


def test_passes_clean_buy():
    v = _validator()
    req = OrderRequest(symbol="HPG", side="BUY", price=28_000, volume=100)
    res = v.validate(req, account=_account(), market=_market())
    assert res.passed
    assert res.violations == []
    assert res.is_fresh()


def test_request_hash_stable_and_binding():
    req = OrderRequest(symbol="HPG", side="BUY", price=28_000, volume=100)
    h1 = request_hash(req)
    h2 = request_hash(req)
    assert h1 == h2
    # Different volume → different hash; the token can't be reused.
    other = OrderRequest(
        symbol="HPG", side="BUY", price=28_000, volume=200,
        client_order_id=req.client_order_id,
    )
    assert request_hash(other) != h1


def test_blocks_off_universe_symbol():
    v = _validator()
    req = OrderRequest(symbol="ZZZ", side="BUY", price=10_000, volume=100)
    res = v.validate(req, account=_account(), market=MarketContext())
    assert not res.passed
    assert "universe_membership" in res.violations


def test_blocks_bad_lot_size():
    v = _validator()
    req = OrderRequest(symbol="HPG", side="BUY", price=28_000, volume=150)
    res = v.validate(req, account=_account(), market=_market())
    assert "lot_size" in res.violations


def test_blocks_price_band_violation():
    v = _validator(price_band_pct=0.05)
    req = OrderRequest(symbol="HPG", side="BUY", price=35_000, volume=100)
    res = v.validate(req, account=_account(), market=_market(price=28_000))
    assert "price_band" in res.violations


def test_warns_when_no_last_close():
    v = _validator()
    req = OrderRequest(symbol="HPG", side="BUY", price=28_000, volume=100)
    # MarketContext without last_close → WARN, not BLOCK.
    res = v.validate(req, account=_account(), market=MarketContext(lot_size=100))
    assert res.passed
    assert any(f.rule == "price_band" and f.severity == "WARN" for f in res.findings)


def test_blocks_notional_cap():
    v = _validator(max_notional_vnd=1_000_000.0)
    req = OrderRequest(symbol="HPG", side="BUY", price=28_000, volume=100)
    res = v.validate(req, account=_account(cash=10_000_000_000), market=_market())
    assert "notional_limit" in res.violations


def test_blocks_insufficient_cash():
    v = _validator()
    req = OrderRequest(symbol="HPG", side="BUY", price=28_000, volume=100)
    res = v.validate(req, account=_account(cash=1_000_000), market=_market())
    assert "available_cash" in res.violations


def test_blocks_short_sell():
    v = _validator()
    req = OrderRequest(symbol="HPG", side="SELL", price=28_000, volume=100)
    res = v.validate(req, account=_account(), market=_market())
    assert "position_cover" in res.violations


def test_allows_sell_when_held():
    v = _validator()
    req = OrderRequest(symbol="HPG", side="SELL", price=28_000, volume=100)
    holdings = [Position(symbol="HPG", quantity=200, avg_cost=27_000)]
    res = v.validate(req, account=_account(positions=holdings), market=_market())
    assert res.passed


def test_blocks_max_open_positions():
    v = _validator(max_open_positions=2)
    holdings = [
        Position(symbol="TCB", quantity=100, avg_cost=20_000),
        Position(symbol="FPT", quantity=50, avg_cost=110_000),
    ]
    req = OrderRequest(symbol="HPG", side="BUY", price=28_000, volume=100)
    res = v.validate(req, account=_account(positions=holdings), market=_market())
    assert "max_open_positions" in res.violations


def test_allows_topup_of_existing_position():
    v = _validator(max_open_positions=2)
    holdings = [
        Position(symbol="HPG", quantity=100, avg_cost=27_000),
        Position(symbol="TCB", quantity=100, avg_cost=20_000),
    ]
    req = OrderRequest(symbol="HPG", side="BUY", price=28_000, volume=100)
    res = v.validate(req, account=_account(positions=holdings), market=_market())
    # Top-up of an existing position is fine — limit is on *new* names.
    assert res.passed
