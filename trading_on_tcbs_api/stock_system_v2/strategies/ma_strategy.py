"""Simple Moving Average crossover strategy."""

from __future__ import annotations

import pandas as pd
from pydantic import Field

from trading_on_tcbs_api.stock_system_v2.schemas.strategy_meta import (
    StrategyDescription,
    StrategyParams,
)

from .strategy import SignalStrategy


class SimpleMAStrategy(SignalStrategy):
    """SMA crossover.

    BUY when the short MA crosses above the long MA (regime change up).
    SELL when it crosses below (regime change down). Optional `invert`
    flips the polarity for use as an exit overlay (e.g. "exit on cross
    *up* through SMA20").
    """

    name = "SMA Crossover"
    description = "BUY on short-MA cross above long-MA; SELL on cross below."

    class Params(StrategyParams):
        short_window: int = Field(20, ge=1, le=400)
        long_window: int = Field(50, ge=2, le=400)
        invert: bool = False

    def __init__(
        self,
        short_window: int | None = None,
        long_window: int | None = None,
        invert: bool | None = None,
        *,
        params: "SimpleMAStrategy.Params | dict | None" = None,
    ) -> None:
        kwargs: dict = {}
        if short_window is not None:
            kwargs["short_window"] = short_window
        if long_window is not None:
            kwargs["long_window"] = long_window
        if invert is not None:
            kwargs["invert"] = invert
        super().__init__(params=params, **kwargs)
        self.min_bars_required = max(self.params.long_window, 1)
        self.name = "SMA Crossover" if not self.params.invert else "SMA Exit"
        if self.params.invert:
            self.description = (
                f"SELL when {self.params.short_window}-MA sweeps below {self.params.long_window}-MA."
            )
        else:
            self.description = (
                f"BUY when {self.params.short_window}-MA > {self.params.long_window}-MA."
            )

    # — back-compat properties so call sites that read .short_window keep working —
    @property
    def short_window(self) -> int:
        return self.params.short_window

    @property
    def long_window(self) -> int:
        return self.params.long_window

    @property
    def invert(self) -> bool:
        return self.params.invert

    def get_required_indicators(self) -> list[str]:
        reqs: list[str] = []
        if self.params.short_window > 1:
            reqs.append(f"sma_{self.params.short_window}")
        if self.params.long_window > 1:
            reqs.append(f"sma_{self.params.long_window}")
        return reqs

    def describe(self) -> StrategyDescription:
        d = super().describe()
        return d.model_copy(
            update={
                "expected_regime": "trend",
                "known_failure_modes": "Choppy / range-bound markets — frequent false crossovers.",
                "signal_semantics": "BUY on regime flip up; SELL on regime flip down. Inverted mode flips both.",
            }
        )

    def _compute_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()

        short_col = "close" if self.params.short_window == 1 else f"sma_{self.params.short_window}"
        long_col = "close" if self.params.long_window == 1 else f"sma_{self.params.long_window}"

        if short_col not in df.columns or long_col not in df.columns:
            raise ValueError(f"Missing required indicator columns: {short_col}, {long_col}")

        df["signal"] = 0
        df["regime"] = 0
        df.loc[df[short_col] > df[long_col], "regime"] = 1
        df.loc[df[short_col] <= df[long_col], "regime"] = -1
        df["prev_regime"] = df["regime"].shift(1)

        df.loc[(df["regime"] == 1) & (df["prev_regime"] == -1), "signal"] = 1
        df.loc[(df["regime"] == -1) & (df["prev_regime"] == 1), "signal"] = -1

        if self.params.invert:
            df["signal"] = df["signal"] * -1

        return df
