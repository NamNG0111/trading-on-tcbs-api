"""Data-layer tools: list_symbols, get_history, get_quote, compute_indicators."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from trading_on_tcbs_api.stock_system_v2.exceptions import (
    DataFetchError,
    InvalidParameterError,
)
from trading_on_tcbs_api.stock_system_v2.tools.context import get_context
from trading_on_tcbs_api.stock_system_v2.tools.registry import tool


# — list_symbols —

class ListSymbolsIn(BaseModel):
    pass


class ListSymbolsOut(BaseModel):
    symbols: list[str]


@tool("list_symbols", input_model=ListSymbolsIn, output_model=ListSymbolsOut)
def list_symbols(_: ListSymbolsIn) -> ListSymbolsOut:
    """Return the configured equity universe.

    No arguments. Idempotent. Returns the symbol list from `Settings`.
    """
    return ListSymbolsOut(symbols=list(get_context().settings.symbols))


# — get_history —

class GetHistoryIn(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=10)
    days: int = Field(365, ge=1, le=365 * 10)
    include_live: bool = Field(False, description="Append today's still-forming bar as is_partial=True.")


class HistoryBar(BaseModel):
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: float | None
    is_partial: bool


class GetHistoryOut(BaseModel):
    symbol: str
    n_bars: int
    n_closed_bars: int
    has_partial_bar: bool
    bars: list[HistoryBar]


@tool("get_history", input_model=GetHistoryIn, output_model=GetHistoryOut)
def get_history(req: GetHistoryIn) -> GetHistoryOut:
    """Return cached OHLCV bars for `symbol`.

    Reads from the `DataProvider` cache (vnstock-KBS source). The frame
    conforms to `OHLCVFrame`: `is_partial=True` only on today's bar
    when `include_live=True`. Volume on partial bars is NaN — never 0.
    """
    ctx = get_context()
    df = ctx.data_provider.get_historical_data(
        req.symbol, days=req.days, include_live=req.include_live
    )
    if df.empty:
        raise DataFetchError(
            f"No data available for {req.symbol}",
            details={"symbol": req.symbol, "days": req.days},
        )
    bars = [
        HistoryBar(
            time=str(row["time"]),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]) if row["volume"] == row["volume"] else None,  # NaN check
            is_partial=bool(row["is_partial"]),
        )
        for _, row in df.iterrows()
    ]
    n_closed = sum(1 for b in bars if not b.is_partial)
    return GetHistoryOut(
        symbol=req.symbol,
        n_bars=len(bars),
        n_closed_bars=n_closed,
        has_partial_bar=any(b.is_partial for b in bars),
        bars=bars,
    )


# — get_quote —

class GetQuoteIn(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=10)


class GetQuoteOut(BaseModel):
    symbol: str
    price: float | None = Field(None, description="Latest live price; None outside trading hours / no auth.")
    last_close: float | None = Field(None, description="Most recent closed-bar close from the cache.")


@tool("get_quote", input_model=GetQuoteIn, output_model=GetQuoteOut)
def get_quote(req: GetQuoteIn) -> GetQuoteOut:
    """Return live + last-close price for `symbol`.

    `price` is the live tape mark when auth is set. `last_close` is the
    most recent closed-bar close from the cache. Either may be None
    independently — outside trading hours `price` is None but
    `last_close` is fresh.
    """
    ctx = get_context()
    live = ctx.data_provider.get_realtime_price(req.symbol)
    last_close: float | None = None
    try:
        df = ctx.data_provider.get_historical_data(req.symbol, days=10, include_live=False)
        if not df.empty:
            last_close = float(df["close"].iloc[-1])
    except DataFetchError:
        pass
    return GetQuoteOut(symbol=req.symbol, price=float(live) if live else None, last_close=last_close)


# — compute_indicators —

class ComputeIndicatorsIn(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=10)
    days: int = Field(365, ge=30, le=365 * 5)
    indicators: list[str] = Field(
        default_factory=lambda: ["sma_20", "sma_50", "rsi_14"],
        description="IndicatorEngine column names. Engine config is taken from defaults.",
    )


class IndicatorPoint(BaseModel):
    time: str
    values: dict[str, float | None]


class ComputeIndicatorsOut(BaseModel):
    symbol: str
    indicators: list[str]
    series: list[IndicatorPoint]


@tool("compute_indicators", input_model=ComputeIndicatorsIn, output_model=ComputeIndicatorsOut)
def compute_indicators(req: ComputeIndicatorsIn) -> ComputeIndicatorsOut:
    """Run the V2 `IndicatorEngine` and return requested columns.

    Indicator names match the lowercase pandas-ta output (`sma_20`,
    `rsi_14`, `roc_3`, `vol_sma_20`, …). Only closed bars are returned;
    today's still-forming bar is dropped by the engine.
    """
    ctx = get_context()
    df = ctx.data_provider.get_historical_data(req.symbol, days=req.days, include_live=False)
    if df.empty:
        raise DataFetchError(f"No data for {req.symbol}", details={"symbol": req.symbol})
    df_ind = ctx.indicator_engine.append_indicators(df)

    missing = [c for c in req.indicators if c not in df_ind.columns]
    if missing:
        raise InvalidParameterError(
            f"Indicator columns not available: {missing}",
            details={"available": [c for c in df_ind.columns if c not in {'open','high','low','close','volume','time','is_partial'}]},
        )

    series = [
        IndicatorPoint(
            time=str(row["time"]),
            values={
                col: (float(row[col]) if row[col] == row[col] else None)
                for col in req.indicators
            },
        )
        for _, row in df_ind.iterrows()
    ]
    return ComputeIndicatorsOut(
        symbol=req.symbol, indicators=list(req.indicators), series=series,
    )
