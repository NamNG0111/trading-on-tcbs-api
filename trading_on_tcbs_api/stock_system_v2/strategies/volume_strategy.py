"""Volume breakout strategy."""

from __future__ import annotations

import pandas as pd
from pydantic import Field

from trading_on_tcbs_api.stock_system_v2.schemas.strategy_meta import (
    StrategyDescription,
    StrategyParams,
)

from .strategy import SignalStrategy


class VolumeBoomStrategy(SignalStrategy):
    """BUY on green volume booms, SELL on red volume booms."""

    name = "Volume Breakout"
    description = "BUY when volume exceeds its rolling MA by `threshold_pct`%."

    class Params(StrategyParams):
        window: int = Field(20, ge=2, le=200)
        threshold_pct: float = Field(50.0, ge=0.0, le=1000.0)

    def __init__(
        self,
        window: int | None = None,
        threshold_pct: float | None = None,
        *,
        params: "VolumeBoomStrategy.Params | dict | None" = None,
    ) -> None:
        kwargs: dict = {}
        if window is not None:
            kwargs["window"] = window
        if threshold_pct is not None:
            kwargs["threshold_pct"] = threshold_pct
        super().__init__(params=params, **kwargs)
        self.min_bars_required = self.params.window
        self.threshold_multiplier = 1.0 + (self.params.threshold_pct / 100.0)
        self.description = (
            f"BUY when volume exceeds {self.params.window}-day VOL_SMA by {self.params.threshold_pct}%."
        )

    @property
    def window(self) -> int:
        return self.params.window

    @property
    def threshold_pct(self) -> float:
        return self.params.threshold_pct

    @property
    def context_columns(self) -> tuple[str, ...]:  # type: ignore[override]
        return ("%_vol_increase",)

    def get_required_indicators(self) -> list[str]:
        return ["volume", f"vol_sma_{self.params.window}"]

    def describe(self) -> StrategyDescription:
        d = super().describe()
        return d.model_copy(
            update={
                "expected_regime": "vol-expansion",
                "known_failure_modes": "Low-liquidity stocks where volume noise drowns out the signal.",
                "signal_semantics": "BUY on volume boom + green candle; SELL on volume boom + red candle.",
            }
        )

    def _compute_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        vol_ma_col = f"vol_sma_{self.params.window}"
        if vol_ma_col not in df.columns:
            raise ValueError(f"Missing required indicator column: {vol_ma_col}")

        df["%_vol_increase"] = ((df["volume"] / df[vol_ma_col]) - 1) * 100
        df["%_vol_increase"] = df["%_vol_increase"].round(2)
        df["vol_boom"] = df["volume"] > (df[vol_ma_col] * self.threshold_multiplier)

        df["signal"] = 0
        df.loc[df["vol_boom"] & (df["close"] > df["open"]), "signal"] = 1
        df.loc[df["vol_boom"] & (df["close"] < df["open"]), "signal"] = -1
        return df
