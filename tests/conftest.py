"""Shared pytest fixtures for V2 tests.

Phase 1 needs only synthetic OHLCV builders. Phase 0 will expand this with
`FakeStockApiClient` / `FakeDataProvider` for full network-free runs.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest


def make_ohlcv(
    n: int = 250,
    *,
    start: datetime | None = None,
    seed: int = 0,
    base_price: float = 30000.0,
    with_partial: bool = False,
) -> pd.DataFrame:
    """Build a synthetic OHLCV frame conforming to the V2 contract."""
    rng = np.random.default_rng(seed)
    start = start or (datetime(2024, 1, 1))
    times = pd.date_range(start=start, periods=n, freq="B")  # business days
    rets = rng.normal(loc=0.0, scale=0.015, size=n)
    closes = base_price * np.exp(np.cumsum(rets))
    highs = closes * (1 + np.abs(rng.normal(0, 0.005, n)))
    lows = closes * (1 - np.abs(rng.normal(0, 0.005, n)))
    opens = closes * (1 + rng.normal(0, 0.003, n))
    volumes = rng.integers(low=10_000, high=1_000_000, size=n).astype(float)

    df = pd.DataFrame(
        {
            "time": times,
            "open": opens,
            "high": np.maximum.reduce([opens, highs, lows, closes]),
            "low": np.minimum.reduce([opens, highs, lows, closes]),
            "close": closes,
            "volume": volumes,
            "is_partial": False,
        }
    )

    if with_partial:
        live_price = float(closes[-1] * 1.002)
        partial = pd.DataFrame(
            [
                {
                    "time": pd.Timestamp(times[-1]) + timedelta(days=1),
                    "open": live_price,
                    "high": live_price,
                    "low": live_price,
                    "close": live_price,
                    "volume": np.nan,
                    "is_partial": True,
                }
            ]
        )
        df = pd.concat([df, partial], ignore_index=True)

    return df


@pytest.fixture
def ohlcv_factory():
    return make_ohlcv
