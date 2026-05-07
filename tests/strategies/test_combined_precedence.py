"""CombinedStrategy precedence rules (Phase 4).

Codifies and locks the three rules:
  1. Sell wins on conflict.
  2. AND mode = unanimous.
  3. OR mode = any.
"""

from __future__ import annotations

import pandas as pd
import pytest
from pydantic import Field

from trading_on_tcbs_api.stock_system_v2.schemas.strategy_meta import StrategyParams
from trading_on_tcbs_api.stock_system_v2.strategies import (
    CombinedStrategy,
    SignalStrategy,
)


class _Stub(SignalStrategy):
    """Test stub that emits a fixed signal series passed at construction."""

    name = "Stub"
    min_bars_required = 0

    class Params(StrategyParams):
        tag: str = Field("stub")

    def __init__(self, signals: list[int]) -> None:
        super().__init__()
        self._signals = signals

    def get_required_indicators(self) -> list[str]:
        return []

    def _compute_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        out = data.copy()
        out["signal"] = self._signals[: len(out)] + [0] * max(0, len(out) - len(self._signals))
        return out


def _frame(n: int = 5) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "time": pd.date_range("2024-01-01", periods=n, freq="B"),
            "open": [1.0] * n,
            "high": [1.0] * n,
            "low": [1.0] * n,
            "close": [1.0] * n,
            "volume": [1.0] * n,
            "is_partial": [False] * n,
        }
    )


def test_sell_wins_on_conflict():
    df = _frame(3)
    buy_only = _Stub([1, 1, 1])
    sell_only = _Stub([-1, -1, -1])
    combined = CombinedStrategy(buy_strategies=[buy_only], sell_strategies=[sell_only])
    out = combined.generate_signals(df)
    assert out["signal"].tolist() == [-1, -1, -1]


def test_and_mode_requires_unanimous():
    df = _frame(3)
    a = _Stub([1, 1, 0])  # buy on bar 0,1
    b = _Stub([1, 0, 1])  # buy on bar 0,2
    combined = CombinedStrategy(buy_strategies=[a, b], buy_mode="AND")
    out = combined.generate_signals(df)
    # Only bar 0 has both saying BUY.
    assert out["signal"].tolist() == [1, 0, 0]


def test_or_mode_fires_on_any():
    df = _frame(3)
    a = _Stub([1, 0, 0])
    b = _Stub([0, 1, 0])
    combined = CombinedStrategy(buy_strategies=[a, b], buy_mode="OR")
    out = combined.generate_signals(df)
    assert out["signal"].tolist() == [1, 1, 0]


def test_sell_pool_and_mode():
    df = _frame(3)
    a = _Stub([0, -1, -1])
    b = _Stub([0, -1, 0])
    combined = CombinedStrategy(sell_strategies=[a, b], sell_mode="AND")
    out = combined.generate_signals(df)
    # Both must say SELL → bar 1 only.
    assert out["signal"].tolist() == [0, -1, 0]


def test_invalid_mode_rejected():
    with pytest.raises(Exception):
        CombinedStrategy(buy_mode="XOR")


def test_min_bars_required_propagates_from_subs():
    a = _Stub([0])
    a.min_bars_required = 30
    b = _Stub([0])
    b.min_bars_required = 50
    combined = CombinedStrategy(strategies=[a, b])
    assert combined.min_bars_required == 50
