"""Registry + describe() introspection tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from trading_on_tcbs_api.stock_system_v2.schemas import StrategyDescription
from trading_on_tcbs_api.stock_system_v2.strategies import (
    STRATEGIES,
    SignalStrategy,
    get_strategy,
)


def test_registry_lists_every_strategy():
    expected = {
        "simple_ma",
        "rsi",
        "rsi_divergence",
        "volume_boom",
        "dip_buy",
        "cumulative_drop",
        "intraday_dip",
        "combined",
    }
    assert set(STRATEGIES) >= expected


@pytest.mark.parametrize("name", [n for n in STRATEGIES if n != "combined"])
def test_each_strategy_describable(name: str):
    cls = get_strategy(name)
    inst = cls()
    desc = inst.describe()
    assert isinstance(desc, StrategyDescription)
    assert desc.name
    assert desc.params_schema  # non-empty JSON schema
    assert desc.min_bars_required >= 0


def test_unknown_strategy_raises():
    with pytest.raises(KeyError) as exc:
        get_strategy("does_not_exist")
    assert "Available" in str(exc.value)


def test_params_validation_rejects_out_of_range():
    cls = get_strategy("rsi")
    with pytest.raises(ValidationError):
        cls(period=-1)
    with pytest.raises(ValidationError):
        cls(oversold=200)  # outside [1, 50]


def test_params_extra_forbidden():
    cls = get_strategy("simple_ma")
    with pytest.raises(ValidationError):
        # Construct via the typed Params block — extra='forbid' rejects
        # unknown fields. The legacy positional kwargs path on the
        # strategy constructor uses explicit keyword names, so a typo
        # there fails as a TypeError instead.
        cls(params={"short_window": 20, "long_window": 50, "typo_field": True})


def test_warmup_zeros_pre_threshold_signals(ohlcv_factory):
    df = ohlcv_factory(n=120, seed=1)
    from trading_on_tcbs_api.stock_system_v2.core.indicator_engine import IndicatorEngine

    df_ind = IndicatorEngine().append_indicators(df)
    cls: type[SignalStrategy] = get_strategy("simple_ma")
    inst = cls(short_window=20, long_window=50)
    out = inst.generate_signals(df_ind)
    pre = out.iloc[: inst.min_bars_required]
    assert (pre["signal"] == 0).all()
