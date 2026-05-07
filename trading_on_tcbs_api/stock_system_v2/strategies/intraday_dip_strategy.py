"""Intraday dip-buy strategy for low-liquidity large caps."""

from __future__ import annotations

import numpy as np
import pandas as pd
from pydantic import Field

from trading_on_tcbs_api.stock_system_v2.schemas.strategy_meta import (
    StrategyDescription,
    StrategyParams,
)

from .strategy import SignalStrategy


class IntradayDipStrategy(SignalStrategy):
    """BUY when intraday low dips ≥ rolling-percentile threshold below prev close."""

    name = "Intraday Dip Strategy"

    class Params(StrategyParams):
        lookback_days: int = Field(60, ge=20, le=400)
        percentile: float = Field(75.0, ge=1.0, le=99.0)

    def __init__(
        self,
        lookback_days: int | None = None,
        percentile: float | None = None,
        *,
        params: "IntradayDipStrategy.Params | dict | None" = None,
    ) -> None:
        kwargs: dict = {}
        if lookback_days is not None:
            kwargs["lookback_days"] = lookback_days
        if percentile is not None:
            kwargs["percentile"] = percentile
        super().__init__(params=params, **kwargs)
        # Engine warmup is handled by the rolling min_periods=20; we still
        # declare a floor so the base class masks pre-history.
        self.min_bars_required = 20
        self.description = (
            f"BUY when intraday dip from prev close ≥ P{self.params.percentile:.0f} "
            f"of last {self.params.lookback_days} sessions."
        )

    @property
    def lookback_days(self) -> int:
        return self.params.lookback_days

    @property
    def percentile(self) -> float:
        return self.params.percentile

    @property
    def context_columns(self) -> tuple[str, ...]:  # type: ignore[override]
        return ("dip_pct", "dip_threshold", "simulated_buy_price", "simulated_profit_pct")

    def get_required_indicators(self) -> list[str]:
        return []

    def describe(self) -> StrategyDescription:
        d = super().describe()
        return d.model_copy(
            update={
                "expected_regime": "any",
                "known_failure_modes": "Trending names where dips don't recover by close — entry fills but price keeps sliding.",
                "signal_semantics": "BUY only (each trade is intraday); exit at close handled by simulator.",
            }
        )

    def _compute_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        df["prev_close"] = df["close"].shift(1)
        df["dip_pct"] = (df["prev_close"] - df["low"]) / df["prev_close"]
        df["dip_pct"] = df["dip_pct"].clip(lower=0)

        df["dip_threshold"] = df["dip_pct"].rolling(
            window=self.params.lookback_days, min_periods=20
        ).quantile(self.params.percentile / 100.0)

        df["simulated_buy_price"] = df["prev_close"] * (1 - df["dip_threshold"])

        df["signal"] = 0
        buy_condition = (
            (df["low"] <= df["simulated_buy_price"])
            & (df["dip_threshold"] > 0)
            & (df["dip_threshold"].notna())
        )
        df.loc[buy_condition, "signal"] = 1

        df["simulated_profit_pct"] = np.where(
            df["signal"] == 1,
            (df["close"] - df["simulated_buy_price"]) / df["simulated_buy_price"] * 100,
            np.nan,
        )
        return df
