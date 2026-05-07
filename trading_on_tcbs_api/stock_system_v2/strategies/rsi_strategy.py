"""RSI strategy: oversold/overbought (basic) or breakout (reversal) modes."""

from __future__ import annotations

import pandas as pd
from pydantic import Field

from trading_on_tcbs_api.stock_system_v2.schemas.strategy_meta import (
    StrategyDescription,
    StrategyParams,
)

from .strategy import SignalStrategy


class RSIStrategy(SignalStrategy):
    """RSI mean-revert strategy.

    Two modes:
      - **Reversal (default):** BUY when RSI crosses *up* through the
        oversold line; SELL when it crosses *down* through overbought.
      - **Basic:** BUY whenever RSI is below oversold; SELL above overbought.
    """

    name = "RSI Reversal"
    description = "Mean-reversion via RSI extremes."

    class Params(StrategyParams):
        period: int = Field(14, ge=2, le=200)
        overbought: int = Field(70, ge=50, le=99)
        oversold: int = Field(30, ge=1, le=50)
        is_reversal: bool = True

    def __init__(
        self,
        period: int | None = None,
        overbought: int | None = None,
        oversold: int | None = None,
        is_reversal: bool | None = None,
        *,
        params: "RSIStrategy.Params | dict | None" = None,
    ) -> None:
        kwargs: dict = {}
        for k, v in (
            ("period", period),
            ("overbought", overbought),
            ("oversold", oversold),
            ("is_reversal", is_reversal),
        ):
            if v is not None:
                kwargs[k] = v
        super().__init__(params=params, **kwargs)
        self.min_bars_required = self.params.period + 1
        self.name = "RSI Reversal" if self.params.is_reversal else "RSI Basic"
        self.description = (
            f"BUY when RSI crosses above {self.params.oversold} (Reversal)."
            if self.params.is_reversal
            else f"BUY when RSI is below {self.params.oversold} (Oversold)."
        )

    @property
    def period(self) -> int:
        return self.params.period

    @property
    def overbought(self) -> int:
        return self.params.overbought

    @property
    def oversold(self) -> int:
        return self.params.oversold

    @property
    def is_reversal(self) -> bool:
        return self.params.is_reversal

    def get_required_indicators(self) -> list[str]:
        return [f"rsi_{self.params.period}"]

    def describe(self) -> StrategyDescription:
        d = super().describe()
        return d.model_copy(
            update={
                "expected_regime": "mean-revert",
                "known_failure_modes": "Trending markets — RSI can stay overbought/oversold for extended periods.",
            }
        )

    def _compute_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        rsi_col = f"rsi_{self.params.period}"
        if rsi_col not in df.columns:
            raise ValueError(f"Missing required indicator column: {rsi_col}")

        df["signal"] = 0
        if self.params.is_reversal:
            df["prev_rsi"] = df[rsi_col].shift(1)
            df.loc[(df["prev_rsi"] < self.params.oversold) & (df[rsi_col] >= self.params.oversold), "signal"] = 1
            df.loc[(df["prev_rsi"] > self.params.overbought) & (df[rsi_col] <= self.params.overbought), "signal"] = -1
        else:
            df.loc[df[rsi_col] < self.params.oversold, "signal"] = 1
            df.loc[df[rsi_col] > self.params.overbought, "signal"] = -1
        return df
