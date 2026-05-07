"""OHLCV DataFrame schema — the source-of-truth shape for every bar series in V2.

Every `DataProvider` boundary, backtester input, and indicator-engine input must
flow through `validate_ohlcv` so that downstream code can rely on:

- The exact set of required columns and dtypes.
- A monotonically increasing, unique time index.
- Non-negative volume, strictly positive prices on **closed** bars.
- An explicit `is_partial: bool` column distinguishing today's still-forming
  bar from settled history (the live-merge fix from Phase 1).

The schema is intentionally permissive about *extra* columns (indicators,
signals, strategy context) so it can be re-applied at multiple points in the
pipeline without forcing a column-strip.
"""

from __future__ import annotations

from typing import Iterable

import pandas as pd
from pydantic import BaseModel, Field

REQUIRED_COLUMNS: tuple[str, ...] = (
    "time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "is_partial",
)

NUMERIC_PRICE_COLS: tuple[str, ...] = ("open", "high", "low", "close")


class OHLCVSchemaError(ValueError):
    """Raised when a DataFrame fails `validate_ohlcv`.

    The agent reading a tool error wants the *list* of violations, not just the
    first. We accumulate problems and emit them all in one message so the
    caller can fix them in a single pass.
    """


class OHLCVFrame(BaseModel):
    """Lightweight metadata describing a validated OHLCV DataFrame.

    The DataFrame itself is not stored on the model (we don't want Pydantic
    serialising 500 bars of price data); this object carries the *contract*
    metadata an agent or tool layer would surface in a JSON response.
    """

    symbol: str = Field(..., description="Ticker symbol the frame describes.")
    resolution: str = Field("1D", description="Bar resolution, e.g. '1D'.")
    n_bars: int = Field(..., ge=0, description="Total bar count, including any partial bar.")
    n_closed_bars: int = Field(..., ge=0, description="Bar count excluding partial bars.")
    has_partial_bar: bool = Field(..., description="True if the final row is today's still-forming bar.")
    first_time: pd.Timestamp | None = Field(None, description="Timestamp of the first bar.")
    last_closed_time: pd.Timestamp | None = Field(None, description="Timestamp of the most recent closed bar.")
    price_unit: str = Field("VND", description="Currency unit of the price columns.")

    model_config = {"arbitrary_types_allowed": True}


def validate_ohlcv(
    df: pd.DataFrame,
    *,
    symbol: str,
    resolution: str = "1D",
    require_non_empty: bool = True,
    extra_required_columns: Iterable[str] = (),
) -> OHLCVFrame:
    """Validate a DataFrame against the OHLCV contract and return its metadata.

    Raises `OHLCVSchemaError` listing every violation found, so the caller can
    fix all of them in one pass instead of round-tripping per problem.

    Args:
        df: The candidate OHLCV frame.
        symbol: Ticker symbol (used only in the returned metadata).
        resolution: Bar resolution string for metadata.
        require_non_empty: If False, an empty DataFrame is allowed (used at the
            cache-miss boundary where the provider hasn't fetched anything yet).
        extra_required_columns: Additional columns the caller wants to enforce
            (e.g. `is_ipo` on cached frames). Optional.
    """
    problems: list[str] = []

    if df is None:
        raise OHLCVSchemaError(f"{symbol}: DataFrame is None")

    if df.empty:
        if require_non_empty:
            raise OHLCVSchemaError(f"{symbol}: DataFrame is empty")
        return OHLCVFrame(
            symbol=symbol,
            resolution=resolution,
            n_bars=0,
            n_closed_bars=0,
            has_partial_bar=False,
            first_time=None,
            last_closed_time=None,
        )

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    missing += [c for c in extra_required_columns if c not in df.columns]
    if missing:
        problems.append(f"missing required columns: {missing}")

    if "time" in df.columns:
        if not pd.api.types.is_datetime64_any_dtype(df["time"]):
            problems.append("'time' column is not datetime64")
        else:
            t = df["time"]
            if t.is_monotonic_increasing is False:
                problems.append("'time' column is not monotonically increasing")
            if t.duplicated().any():
                problems.append("'time' column contains duplicate timestamps")

    for col in NUMERIC_PRICE_COLS:
        if col in df.columns:
            series = df[col]
            if not pd.api.types.is_numeric_dtype(series):
                problems.append(f"'{col}' is not numeric")
                continue
            # Closed bars must be strictly positive; partial bars are allowed
            # to carry the live price (also positive) — but never negative.
            if (series < 0).any():
                problems.append(f"'{col}' contains negative values")

    if "close" in df.columns and "is_partial" in df.columns:
        closed = df.loc[df["is_partial"] != True, "close"]
        if closed.isna().any():
            problems.append("'close' contains NaN on closed bars")
        if (closed <= 0).any():
            problems.append("'close' contains non-positive values on closed bars")

    if "volume" in df.columns:
        vol = df["volume"]
        if not pd.api.types.is_numeric_dtype(vol):
            problems.append("'volume' is not numeric")
        else:
            # Volume may be NaN on the partial bar (we don't have intraday
            # cumulative volume). On closed bars it must be non-negative.
            if "is_partial" in df.columns:
                closed_vol = vol[df["is_partial"] != True]
            else:
                closed_vol = vol
            if (closed_vol.fillna(0) < 0).any():
                problems.append("'volume' contains negative values on closed bars")

    if "is_partial" in df.columns:
        n_partial = int(df["is_partial"].fillna(False).astype(bool).sum())
        if n_partial > 1:
            problems.append(f"more than one partial bar ({n_partial}); only the most recent row may be partial")
        if n_partial == 1 and bool(df["is_partial"].iloc[-1]) is not True:
            problems.append("partial bar must be the last row")

    if problems:
        joined = "; ".join(problems)
        raise OHLCVSchemaError(f"{symbol}: {joined}")

    n_bars = len(df)
    is_partial_series = df["is_partial"].fillna(False).astype(bool) if "is_partial" in df.columns else pd.Series([False] * n_bars)
    n_closed = int((~is_partial_series).sum())
    has_partial = bool(is_partial_series.iloc[-1]) if n_bars > 0 else False
    closed_times = df.loc[~is_partial_series, "time"]
    last_closed = closed_times.max() if not closed_times.empty else None
    first_time = df["time"].min() if "time" in df.columns else None

    return OHLCVFrame(
        symbol=symbol,
        resolution=resolution,
        n_bars=n_bars,
        n_closed_bars=n_closed,
        has_partial_bar=has_partial,
        first_time=first_time,
        last_closed_time=last_closed,
    )


def closed_bars(df: pd.DataFrame) -> pd.DataFrame:
    """Return the subset of `df` containing only fully-formed (non-partial) bars.

    Used by indicator engines and strategies that must not be contaminated by
    today's still-forming bar. Safe to call on a frame without `is_partial`.
    """
    if "is_partial" not in df.columns:
        return df
    mask = df["is_partial"].fillna(False).astype(bool)
    return df.loc[~mask].copy()  # type: ignore[return-value]
