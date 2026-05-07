"""Tests for the `OHLCVFrame` schema and helpers.

Covers:
- `validate_ohlcv` accepts well-formed frames (Phase 1, item 1).
- `validate_ohlcv` rejects every contract violation listed in the schema
  (Phase 1, item 1 + property tests).
- Hypothesis property tests over the contract invariants
  (Phase 1, item 6: "no NaN in close after fetch; index strictly monotonic;
  volume >= 0; price > 0").
- `closed_bars` strips the partial row (Phase 1, item 3).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from trading_on_tcbs_api.stock_system_v2.schemas.ohlcv import (
    OHLCVSchemaError,
    closed_bars,
    validate_ohlcv,
)
from tests.conftest import make_ohlcv


def test_validate_ohlcv_happy_path():
    df = make_ohlcv(n=10)
    meta = validate_ohlcv(df, symbol="HPG")
    assert meta.n_bars == 10
    assert meta.n_closed_bars == 10
    assert meta.has_partial_bar is False


def test_validate_ohlcv_partial_bar_metadata():
    df = make_ohlcv(n=10, with_partial=True)
    meta = validate_ohlcv(df, symbol="HPG")
    assert meta.n_bars == 11
    assert meta.n_closed_bars == 10
    assert meta.has_partial_bar is True
    assert meta.last_closed_time == df.iloc[-2]["time"]


def test_validate_ohlcv_rejects_missing_columns():
    df = make_ohlcv(n=5).drop(columns=["volume"])
    with pytest.raises(OHLCVSchemaError, match="missing required columns"):
        validate_ohlcv(df, symbol="HPG")


def test_validate_ohlcv_rejects_non_monotonic_time():
    df = make_ohlcv(n=5)
    df.loc[2, "time"] = df.loc[0, "time"]  # break ordering
    with pytest.raises(OHLCVSchemaError, match="monotonically increasing|duplicate"):
        validate_ohlcv(df, symbol="HPG")


def test_validate_ohlcv_rejects_nonpositive_close_on_closed_bar():
    df = make_ohlcv(n=5)
    df.loc[3, "close"] = 0.0
    with pytest.raises(OHLCVSchemaError, match="non-positive"):
        validate_ohlcv(df, symbol="HPG")


def test_validate_ohlcv_rejects_negative_volume():
    df = make_ohlcv(n=5)
    df.loc[2, "volume"] = -1.0
    with pytest.raises(OHLCVSchemaError, match="negative"):
        validate_ohlcv(df, symbol="HPG")


def test_validate_ohlcv_rejects_partial_not_at_tail():
    df = make_ohlcv(n=5, with_partial=True)
    # Move partial flag to the middle row instead of the tail
    df.loc[2, "is_partial"] = True
    df.loc[df.index[-1], "is_partial"] = False
    with pytest.raises(OHLCVSchemaError, match="more than one partial bar|partial bar must be the last"):
        validate_ohlcv(df, symbol="HPG")


def test_validate_ohlcv_partial_bar_can_have_nan_volume():
    """Phase 1 contract: partial bars carry NaN volume, never 0."""
    df = make_ohlcv(n=5, with_partial=True)
    assert np.isnan(df.loc[df.index[-1], "volume"])
    validate_ohlcv(df, symbol="HPG")  # must not raise


def test_validate_ohlcv_empty_allowed_when_flag_set():
    df = pd.DataFrame()
    meta = validate_ohlcv(df, symbol="HPG", require_non_empty=False)
    assert meta.n_bars == 0


def test_validate_ohlcv_empty_rejected_by_default():
    with pytest.raises(OHLCVSchemaError, match="empty"):
        validate_ohlcv(pd.DataFrame(), symbol="HPG")


def test_closed_bars_drops_partial_row():
    df = make_ohlcv(n=5, with_partial=True)
    closed = closed_bars(df)
    assert len(closed) == 5
    assert closed["is_partial"].any() is np.False_ or not closed["is_partial"].any()


def test_closed_bars_passthrough_without_is_partial():
    df = make_ohlcv(n=5).drop(columns=["is_partial"])
    out = closed_bars(df)
    assert len(out) == 5


# -----------------------------
# Hypothesis property tests
# -----------------------------

@given(
    n=st.integers(min_value=2, max_value=200),
    base_price=st.floats(min_value=1_000.0, max_value=500_000.0, allow_nan=False, allow_infinity=False),
    seed=st.integers(min_value=0, max_value=10_000),
    with_partial=st.booleans(),
)
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_property_well_formed_frame_validates(n, base_price, seed, with_partial):
    df = make_ohlcv(n=n, seed=seed, base_price=base_price, with_partial=with_partial)
    meta = validate_ohlcv(df, symbol="HPG")
    # Invariants the plan calls out explicitly:
    closed = closed_bars(df)
    assert closed["close"].notna().all(), "close NaN on closed bar"
    assert (closed["close"] > 0).all(), "close <= 0 on closed bar"
    assert (closed["volume"].fillna(0) >= 0).all(), "negative volume on closed bar"
    assert df["time"].is_monotonic_increasing, "time not monotonic"
    assert not df["time"].duplicated().any(), "duplicate timestamps"
    assert meta.n_closed_bars == len(closed)
