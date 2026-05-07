"""Signal + ScanResult schemas (Phase 3).

Every strategy emits a `Signal` per bar; the scanner aggregates today's
non-zero signals into a list of `ScanResult` rows that an agent can iterate
on directly. `signal_context` carries strategy-specific extras (RSI value,
% from SMA, dip size) without forcing every consumer to know the column
names — the typed accessor lives on the strategy.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SignalAction = Literal["BUY", "SELL", "HOLD"]


class Signal(BaseModel):
    """A single strategy decision on one bar.

    Use `Signal.from_code(int)` when adapting from the legacy DataFrame
    `signal` column (1=BUY, -1=SELL, 0=HOLD).
    """

    model_config = ConfigDict(frozen=True)

    action: SignalAction
    code: int = Field(..., description="Legacy integer code: 1=BUY, -1=SELL, 0=HOLD.")

    @classmethod
    def from_code(cls, code: int) -> "Signal":
        if code == 1:
            return cls(action="BUY", code=1)
        if code == -1:
            return cls(action="SELL", code=-1)
        return cls(action="HOLD", code=0)


class ScanResult(BaseModel):
    """One row in a market-scan output.

    `price` is the closed-bar reference price the signal fired on.
    `live_price` is the most recent live-tape mark when available
    (None outside trading hours or when auth was missing).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    date: str
    symbol: str
    strategy: str
    signal: SignalAction
    price: float
    live_price: float | None = None
    signal_context: dict[str, Any] = Field(
        default_factory=dict,
        description="Strategy-specific context columns (RSI value, dip size, …).",
    )
