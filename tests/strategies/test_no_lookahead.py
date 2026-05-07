"""No-lookahead seal for every V2 strategy.

Each (strategy, symbol) pair runs through `assert_no_lookahead`, which
spot-checks that truncating the input frame produces the same signal at
the truncation point as the full-frame run. Catches accidental use of
future bars in any strategy or its indicator dependencies.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from tests.utils import assert_no_lookahead
from trading_on_tcbs_api.stock_system_v2.strategies import (
    CumulativeDropStrategy,
    DipBuyStrategy,
    IntradayDipStrategy,
    RSIDivergenceStrategy,
    RSIStrategy,
    SimpleMAStrategy,
    VolumeBoomStrategy,
)

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"
SYMBOLS = ["HPG", "TCB", "FPT"]

STRATEGY_FACTORIES = {
    "simple_ma": lambda: SimpleMAStrategy(short_window=20, long_window=50),
    "rsi_basic": lambda: RSIStrategy(period=14, is_reversal=False),
    "rsi_reversal": lambda: RSIStrategy(period=14, is_reversal=True),
    "rsi_divergence": lambda: RSIDivergenceStrategy(rsi_period=14, lookback=5, max_bars_between=30),
    "volume_boom": lambda: VolumeBoomStrategy(window=20, threshold_pct=50.0),
    "dip_buy": lambda: DipBuyStrategy(sma_window=20, drop_pct=10.0),
    "cumulative_drop": lambda: CumulativeDropStrategy(days=3, drop_pct=10.0),
    "intraday_dip": lambda: IntradayDipStrategy(lookback_days=60, percentile=75.0),
}


def _load_fixture(symbol: str) -> pd.DataFrame:
    df = pd.read_csv(FIXTURES_DIR / f"{symbol}.csv")
    df["time"] = pd.to_datetime(df["time"])
    df["is_partial"] = df["is_partial"].astype(bool)
    return df


@pytest.mark.parametrize(
    "label,symbol",
    [(label, sym) for label in STRATEGY_FACTORIES for sym in SYMBOLS],
)
def test_strategy_is_causal(label: str, symbol: str):
    df = _load_fixture(symbol)
    strat = STRATEGY_FACTORIES[label]()
    assert_no_lookahead(strat, df)
