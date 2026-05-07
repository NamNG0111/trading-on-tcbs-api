"""Position-sizing strategies for the V2 backtester (Phase 2).

The legacy backtester sized every entry at `cash // price` — i.e. all-in on a
single name. That dramatically inflates winners (compounding into one
position) and is not how anyone actually trades. The `PositionSizer`
interface here lets the backtester (and, later, the live executor) plug in a
realistic sizing rule.

Three implementations ship today:

- `FixedFractionSizer`  — risks a fixed % of equity per position.
- `EqualWeightSizer`    — splits equity equally across `target_positions` slots.
- `VolatilityTargetedSizer` — sizes inversely to recent realised volatility,
  targeting a constant per-position vol contribution.

All sizers return *integer* share counts already rounded to a tradable lot.
A return of 0 means "skip this fill" — the caller must respect that.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field


class SizerContext(BaseModel):
    """Inputs a sizer needs to decide how many shares to buy.

    Pydantic so it's serialisable into audit logs and tool responses; the
    DataFrame is intentionally not stored on the model.
    """

    cash: float = Field(..., ge=0.0, description="Cash currently available, in VND.")
    equity: float = Field(..., ge=0.0, description="Total portfolio value (cash + positions), in VND.")
    price: float = Field(..., gt=0.0, description="Reference price for the candidate fill.")
    lot_size: int = Field(1, ge=1, description="Round shares down to this lot.")

    model_config = {"arbitrary_types_allowed": True}


class PositionSizer(ABC):
    """Abstract sizer. Implementations decide share count given context + history."""

    @abstractmethod
    def size(self, ctx: SizerContext, history: pd.DataFrame | None = None) -> int:
        """Return integer share count (already rounded to lot). 0 means skip."""

    def _round_lot(self, shares: float, lot_size: int) -> int:
        if shares <= 0:
            return 0
        if lot_size <= 1:
            return int(shares)
        return int(shares) // lot_size * lot_size


class FixedFractionSizer(PositionSizer):
    """Risks `fraction` of total equity per position, capped by available cash."""

    def __init__(self, fraction: float = 0.10):
        if not 0.0 < fraction <= 1.0:
            raise ValueError(f"fraction must be in (0, 1]; got {fraction}")
        self.fraction = fraction

    def size(self, ctx: SizerContext, history: pd.DataFrame | None = None) -> int:
        target_notional = min(ctx.equity * self.fraction, ctx.cash)
        if target_notional <= 0:
            return 0
        raw_shares = target_notional / ctx.price
        return self._round_lot(raw_shares, ctx.lot_size)


class EqualWeightSizer(PositionSizer):
    """Splits equity equally across `target_positions` slots."""

    def __init__(self, target_positions: int = 5):
        if target_positions < 1:
            raise ValueError(f"target_positions must be >= 1; got {target_positions}")
        self.target_positions = target_positions

    def size(self, ctx: SizerContext, history: pd.DataFrame | None = None) -> int:
        target_notional = min(ctx.equity / self.target_positions, ctx.cash)
        if target_notional <= 0:
            return 0
        raw_shares = target_notional / ctx.price
        return self._round_lot(raw_shares, ctx.lot_size)


class VolatilityTargetedSizer(PositionSizer):
    """Targets a constant per-position volatility contribution.

    Notional = (target_vol_pct / realised_vol_pct) * equity, capped by cash.
    Realised vol is the annualised stdev of daily log returns over `vol_window`.
    Falls back to `EqualWeightSizer` semantics when `history` is absent or
    yields a degenerate vol estimate (NaN, 0).
    """

    def __init__(
        self,
        target_vol_pct: float = 0.02,
        vol_window: int = 20,
        max_fraction: float = 0.25,
        fallback_positions: int = 5,
    ):
        if target_vol_pct <= 0:
            raise ValueError("target_vol_pct must be > 0")
        if vol_window < 5:
            raise ValueError("vol_window must be >= 5")
        if not 0.0 < max_fraction <= 1.0:
            raise ValueError("max_fraction must be in (0, 1]")
        self.target_vol_pct = target_vol_pct
        self.vol_window = vol_window
        self.max_fraction = max_fraction
        self.fallback_positions = fallback_positions

    def _realised_vol(self, history: pd.DataFrame) -> float:
        if history is None or "close" not in history.columns or len(history) < self.vol_window + 1:
            return float("nan")
        closes = history["close"].astype(float).values[-(self.vol_window + 1) :]
        rets = np.diff(np.log(closes))
        if len(rets) == 0:
            return float("nan")
        return float(np.std(rets, ddof=1))

    def size(self, ctx: SizerContext, history: pd.DataFrame | None = None) -> int:
        vol = self._realised_vol(history) if history is not None else float("nan")
        if not np.isfinite(vol) or vol <= 0:
            target_notional = min(ctx.equity / self.fallback_positions, ctx.cash)
        else:
            fraction = min(self.target_vol_pct / vol, self.max_fraction)
            target_notional = min(ctx.equity * fraction, ctx.cash)
        if target_notional <= 0:
            return 0
        raw_shares = target_notional / ctx.price
        return self._round_lot(raw_shares, ctx.lot_size)
