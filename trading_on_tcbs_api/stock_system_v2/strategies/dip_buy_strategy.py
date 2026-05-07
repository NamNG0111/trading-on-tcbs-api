"""Dip-buy strategy: BUY when price drops X% below SMA."""

from __future__ import annotations

import pandas as pd
from pydantic import Field

from trading_on_tcbs_api.stock_system_v2.schemas.strategy_meta import (
    StrategyDescription,
    StrategyParams,
)

from .strategy import SignalStrategy


class DipBuyStrategy(SignalStrategy):
    """BUY on dips below the SMA, SELL on reversion to it."""

    name = "Dip Buy Strategy"
    description = "BUY when price drops > drop_pct below SMA; SELL on reversion."

    class Params(StrategyParams):
        sma_window: int = Field(20, ge=2, le=400)
        drop_pct: float = Field(10.0, gt=0.0, le=99.0)

    def __init__(
        self,
        sma_window: int | None = None,
        drop_pct: float | None = None,
        *,
        params: "DipBuyStrategy.Params | dict | None" = None,
    ) -> None:
        kwargs: dict = {}
        if sma_window is not None:
            kwargs["sma_window"] = sma_window
        if drop_pct is not None:
            kwargs["drop_pct"] = drop_pct
        super().__init__(params=params, **kwargs)
        self.min_bars_required = self.params.sma_window
        self.drop_multiplier = 1.0 - (self.params.drop_pct / 100.0)
        self.description = (
            f"BUY when price drops > {self.params.drop_pct}% below {self.params.sma_window}-day SMA."
        )

    @property
    def sma_window(self) -> int:
        return self.params.sma_window

    @property
    def drop_pct(self) -> float:
        return self.params.drop_pct

    @property
    def context_columns(self) -> tuple[str, ...]:  # type: ignore[override]
        return (f"%_from_sma{self.params.sma_window}",)

    def get_required_indicators(self) -> list[str]:
        return [f"sma_{self.params.sma_window}"]

    def describe(self) -> StrategyDescription:
        d = super().describe()
        return d.model_copy(
            update={
                "expected_regime": "mean-revert",
                "known_failure_modes": "Strong downtrends — repeated SELL trips on every reversion attempt.",
            }
        )

    def _compute_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        sma_col = f"sma_{self.params.sma_window}"
        if sma_col not in df.columns:
            raise ValueError(
                f"Missing required indicator column from IndicatorEngine: {sma_col}."
            )
        df["signal"] = 0
        context_col = f"%_from_sma{self.params.sma_window}"
        df[context_col] = ((df["close"] / df[sma_col]) - 1) * 100
        df[context_col] = df[context_col].round(2)

        target_buy_price = df[sma_col] * self.drop_multiplier
        df.loc[df["close"] < target_buy_price, "signal"] = 1
        df.loc[df["close"] >= df[sma_col], "signal"] = -1
        return df
