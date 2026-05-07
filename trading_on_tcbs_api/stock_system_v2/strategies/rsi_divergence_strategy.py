"""RSI Divergence strategy."""

from __future__ import annotations

import numpy as np
import pandas as pd
from pydantic import Field
from scipy.signal import argrelextrema

from trading_on_tcbs_api.stock_system_v2.schemas.strategy_meta import (
    StrategyDescription,
    StrategyParams,
)

from .strategy import SignalStrategy


class RSIDivergenceStrategy(SignalStrategy):
    """Divergence between price extrema and RSI extrema.

    Bullish: price lower-low, RSI higher-low → BUY.
    Bearish: price higher-high, RSI lower-high → SELL.

    Causality fix (Phase 2): peaks confirmed by `argrelextrema` need
    `lookback` future bars to be detected; the signal therefore fires at
    `peak_idx + lookback`, not at the peak itself.
    """

    name = "RSI Divergence"

    class Params(StrategyParams):
        rsi_period: int = Field(14, ge=2, le=200)
        lookback: int = Field(5, ge=1, le=60)
        max_bars_between: int = Field(30, ge=2, le=200)

    def __init__(
        self,
        rsi_period: int | None = None,
        lookback: int | None = None,
        max_bars_between: int | None = None,
        *,
        params: "RSIDivergenceStrategy.Params | dict | None" = None,
    ) -> None:
        kwargs: dict = {}
        for k, v in (
            ("rsi_period", rsi_period),
            ("lookback", lookback),
            ("max_bars_between", max_bars_between),
        ):
            if v is not None:
                kwargs[k] = v
        super().__init__(params=params, **kwargs)
        self.min_bars_required = self.params.rsi_period + 2 * self.params.lookback + 1
        self.description = (
            f"BUY on bullish divergence (price lower low + RSI higher low), "
            f"SELL on bearish divergence. RSI({self.params.rsi_period}), "
            f"lookback={self.params.lookback}, max_gap={self.params.max_bars_between}."
        )

    @property
    def rsi_period(self) -> int:
        return self.params.rsi_period

    @property
    def lookback(self) -> int:
        return self.params.lookback

    @property
    def max_bars_between(self) -> int:
        return self.params.max_bars_between

    def get_required_indicators(self) -> list[str]:
        return [f"rsi_{self.params.rsi_period}"]

    def describe(self) -> StrategyDescription:
        d = super().describe()
        return d.model_copy(
            update={
                "expected_regime": "mean-revert",
                "known_failure_modes": "Strong trends — divergences accumulate but the trend grinds through them.",
                "signal_semantics": "BUY at confirmation bar (peak + lookback) on bullish divergence, SELL on bearish.",
            }
        )

    def _compute_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        rsi_col = f"rsi_{self.params.rsi_period}"
        if rsi_col not in df.columns:
            raise ValueError(f"Missing required indicator column: {rsi_col}")

        df["signal"] = 0
        close = df["close"].values
        rsi = df[rsi_col].values
        n = len(df)

        if n < self.params.lookback * 2 + 1:
            return df

        price_min_indices = argrelextrema(close, np.less_equal, order=self.params.lookback)[0]
        price_max_indices = argrelextrema(close, np.greater_equal, order=self.params.lookback)[0]
        signal_loc = df.columns.get_loc("signal")

        for i in range(1, len(price_min_indices)):
            curr_idx = price_min_indices[i]
            prev_idx = price_min_indices[i - 1]
            if curr_idx - prev_idx > self.params.max_bars_between:
                continue
            if np.isnan(rsi[curr_idx]) or np.isnan(rsi[prev_idx]):
                continue
            if close[curr_idx] < close[prev_idx] and rsi[curr_idx] > rsi[prev_idx]:
                emit_idx = curr_idx + self.params.lookback
                if emit_idx < n:
                    df.iloc[emit_idx, signal_loc] = 1

        for i in range(1, len(price_max_indices)):
            curr_idx = price_max_indices[i]
            prev_idx = price_max_indices[i - 1]
            if curr_idx - prev_idx > self.params.max_bars_between:
                continue
            if np.isnan(rsi[curr_idx]) or np.isnan(rsi[prev_idx]):
                continue
            if close[curr_idx] > close[prev_idx] and rsi[curr_idx] < rsi[prev_idx]:
                emit_idx = curr_idx + self.params.lookback
                if emit_idx < n:
                    df.iloc[emit_idx, signal_loc] = -1

        return df
