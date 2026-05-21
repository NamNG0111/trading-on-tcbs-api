"""PreTradeValidator hard-cap tests (Phase 10 chunk 5)."""

from __future__ import annotations

from trading_on_tcbs_api.stock_system_v2.execution.pre_trade_validator import (
    DailyTradeStats,
    PreTradeValidator,
    ValidatorConfig,
)
from trading_on_tcbs_api.stock_system_v2.schemas import (
    AccountSnapshot,
    MarketContext,
    OrderRequest,
    Position,
)


def _market(symbol: str = "HPG", last_close: float = 27_500.0) -> MarketContext:
    return MarketContext(last_close_prices={symbol: last_close}, lot_size=100)


def _account(*, positions=None, cash: float = 100_000_000) -> AccountSnapshot:
    return AccountSnapshot(
        cash=cash,
        buying_power=cash,
        positions=list(positions or []),
        is_mock=True,
    )


def _req(*, symbol="HPG", side="BUY", price=27_500.0, volume=100) -> OrderRequest:
    return OrderRequest(symbol=symbol, side=side, price=price, volume=volume)


# — max_position_size_vnd —


def test_position_size_cap_blocks_when_projected_exceeds():
    cfg = ValidatorConfig(max_position_size_vnd=2_000_000)
    v = PreTradeValidator(cfg, universe=("HPG",))
    # 100 shares @ 27,500 = 2,750,000 — exceeds 2M cap.
    result = v.validate(_req(), account=_account(), market=_market())
    assert not result.passed
    assert "max_position_size" in result.violations


def test_position_size_cap_blocks_with_existing_holding():
    cfg = ValidatorConfig(max_position_size_vnd=3_000_000)
    v = PreTradeValidator(cfg, universe=("HPG",))
    # Existing 100 shares @ 25,000 = 2,500,000; new BUY adds 2,750,000 → 5,250,000 > 3M.
    existing = Position(symbol="HPG", quantity=100, avg_cost=25_000)
    result = v.validate(
        _req(), account=_account(positions=[existing]), market=_market(),
    )
    assert not result.passed
    assert "max_position_size" in result.violations


def test_position_size_cap_passes_when_under():
    cfg = ValidatorConfig(max_position_size_vnd=10_000_000)
    v = PreTradeValidator(cfg, universe=("HPG",))
    result = v.validate(_req(), account=_account(), market=_market())
    assert result.passed


def test_position_size_cap_disabled_when_zero():
    cfg = ValidatorConfig(max_position_size_vnd=0)  # sentinel: disabled
    v = PreTradeValidator(cfg, universe=("HPG",))
    result = v.validate(_req(volume=1000), account=_account(cash=1_000_000_000), market=_market())
    assert "max_position_size" not in result.violations


def test_position_size_cap_only_applies_to_buy():
    cfg = ValidatorConfig(max_position_size_vnd=100)  # absurdly low
    v = PreTradeValidator(cfg, universe=("HPG",))
    existing = Position(symbol="HPG", quantity=100, avg_cost=27_500)
    result = v.validate(
        _req(side="SELL"),
        account=_account(positions=[existing]),
        market=_market(),
    )
    assert "max_position_size" not in result.violations


# — max_trades_per_day —


def test_trades_per_day_cap_blocks_at_limit():
    cfg = ValidatorConfig(max_trades_per_day=3, max_position_size_vnd=0)
    v = PreTradeValidator(cfg, universe=("HPG",))
    stats = DailyTradeStats(trades_today=3)
    result = v.validate(
        _req(volume=100), account=_account(), market=_market(), daily_stats=stats,
    )
    assert not result.passed
    assert "max_trades_per_day" in result.violations


def test_trades_per_day_cap_passes_below_limit():
    cfg = ValidatorConfig(max_trades_per_day=3)
    v = PreTradeValidator(cfg, universe=("HPG",))
    stats = DailyTradeStats(trades_today=2)
    result = v.validate(
        _req(volume=100), account=_account(), market=_market(), daily_stats=stats,
    )
    assert "max_trades_per_day" not in result.violations


def test_trades_per_day_cap_not_enforced_without_daily_stats():
    """Back-compat: legacy callers without daily_stats see no new BLOCKs."""
    cfg = ValidatorConfig(max_trades_per_day=1)
    v = PreTradeValidator(cfg, universe=("HPG",))
    result = v.validate(_req(volume=100), account=_account(), market=_market())
    assert "max_trades_per_day" not in result.violations


def test_trades_per_day_cap_disabled_when_zero():
    cfg = ValidatorConfig(max_trades_per_day=0)  # sentinel: disabled
    v = PreTradeValidator(cfg, universe=("HPG",))
    stats = DailyTradeStats(trades_today=100)
    result = v.validate(
        _req(volume=100), account=_account(), market=_market(), daily_stats=stats,
    )
    assert "max_trades_per_day" not in result.violations


# — max_daily_loss_vnd —


def test_daily_loss_cap_blocks_when_floor_breached():
    cfg = ValidatorConfig(max_daily_loss_vnd=5_000_000, max_position_size_vnd=0)
    v = PreTradeValidator(cfg, universe=("HPG",))
    stats = DailyTradeStats(realized_pnl_today_vnd=-6_000_000)  # 6M lost > 5M cap
    result = v.validate(
        _req(volume=100), account=_account(), market=_market(), daily_stats=stats,
    )
    assert not result.passed
    assert "max_daily_loss" in result.violations


def test_daily_loss_cap_passes_within_floor():
    cfg = ValidatorConfig(max_daily_loss_vnd=5_000_000)
    v = PreTradeValidator(cfg, universe=("HPG",))
    stats = DailyTradeStats(realized_pnl_today_vnd=-2_000_000)
    result = v.validate(
        _req(volume=100), account=_account(), market=_market(), daily_stats=stats,
    )
    assert "max_daily_loss" not in result.violations


def test_daily_loss_cap_irrelevant_on_profit():
    cfg = ValidatorConfig(max_daily_loss_vnd=5_000_000)
    v = PreTradeValidator(cfg, universe=("HPG",))
    stats = DailyTradeStats(realized_pnl_today_vnd=8_000_000)  # winning day
    result = v.validate(
        _req(volume=100), account=_account(), market=_market(), daily_stats=stats,
    )
    assert "max_daily_loss" not in result.violations


# — settings wiring —


def test_settings_risk_carries_new_cap_fields():
    from trading_on_tcbs_api.stock_system_v2.settings import RiskParams
    p = RiskParams()
    assert p.max_position_size_vnd > 0
    assert p.max_daily_loss_vnd > 0
    assert p.max_trades_per_day > 0
