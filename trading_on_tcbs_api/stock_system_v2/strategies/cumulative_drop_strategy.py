"""N-day cumulative drop strategy."""

from __future__ import annotations

import pandas as pd
from pydantic import Field

from trading_on_tcbs_api.stock_system_v2.schemas.strategy_meta import (
    StrategyDescription,
    StrategyParams,
)

from .strategy import SignalStrategy


class CumulativeDropStrategy(SignalStrategy):
    """BUY when price drops > drop_pct over `days` consecutive sessions."""

    class Params(StrategyParams):
        days: int = Field(3, ge=1, le=60)
        drop_pct: float = Field(10.0, gt=0.0, le=99.0)

    def __init__(
        self,
        days: int | None = None,
        drop_pct: float | None = None,
        *,
        params: "CumulativeDropStrategy.Params | dict | None" = None,
    ) -> None:
        kwargs: dict = {}
        if days is not None:
            kwargs["days"] = days
        if drop_pct is not None:
            kwargs["drop_pct"] = drop_pct
        super().__init__(params=params, **kwargs)
        self.min_bars_required = self.params.days + 1
        self.name = f"{self.params.days}-Day Cumulative Drop"
        self.description = (
            f"BUY when total price drop over {self.params.days} days is > {self.params.drop_pct}%."
        )

    @property
    def days(self) -> int:
        return self.params.days

    @property
    def drop_pct(self) -> float:
        return self.params.drop_pct

    def get_required_indicators(self) -> list[str]:
        return [f"roc_{self.params.days}"]

    def describe(self) -> StrategyDescription:
        d = super().describe()
        return d.model_copy(
            update={
                "expected_regime": "mean-revert",
                "known_failure_modes": "Persistent downtrends — drop threshold trips repeatedly into a falling knife.",
                "signal_semantics": "BUY only; exits delegated to CombinedStrategy / portfolio overlay.",
            }
        )

    def _compute_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        roc_col = f"roc_{self.params.days}"
        if roc_col not in df.columns:
            raise ValueError(f"Missing required indicator column: {roc_col}")
        df["signal"] = 0
        threshold = -abs(self.params.drop_pct)
        df.loc[df[roc_col] < threshold, "signal"] = 1
        return df
