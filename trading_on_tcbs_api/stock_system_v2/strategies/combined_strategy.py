"""CombinedStrategy — aggregate multiple strategies under explicit precedence.

Phase-4 precedence rules (codified, tested, frozen):

1. **Sell wins on conflict.** If, on the same bar, the buy_pool says BUY
   and the sell_pool says SELL, the bar's signal is SELL. Capital
   preservation comes first; we'd rather miss an entry than miss an exit.
2. **AND mode = unanimous.** Every member of the pool must agree (BUY for
   buy_pool, SELL for sell_pool) for the combined signal to fire.
3. **OR mode = any.** A single member is enough.

`buy_strategies` / `sell_strategies` are pool-specific lists; the
`strategies` argument feeds *both* pools.
"""

from __future__ import annotations

from typing import Any, List, Optional

import pandas as pd
from pydantic import Field

from trading_on_tcbs_api.stock_system_v2.schemas.strategy_meta import (
    StrategyDescription,
    StrategyParams,
)

from .strategy import SignalStrategy


class CombinedStrategy(SignalStrategy):
    """Aggregator that runs sub-strategies and applies AND/OR + sell-wins rules."""

    name = "Combined Strategy"
    description = "Aggregates underlying strategies under explicit AND/OR precedence."

    class Params(StrategyParams):
        buy_mode: str = Field("AND", pattern="^(AND|OR)$")
        sell_mode: str = Field("OR", pattern="^(AND|OR)$")

    def __init__(
        self,
        strategies: Optional[List[SignalStrategy]] = None,
        buy_strategies: Optional[List[SignalStrategy]] = None,
        sell_strategies: Optional[List[SignalStrategy]] = None,
        buy_mode: str = "AND",
        sell_mode: str = "OR",
        *,
        params: "CombinedStrategy.Params | dict | None" = None,
    ) -> None:
        super().__init__(params=params, buy_mode=buy_mode.upper(), sell_mode=sell_mode.upper())
        self.common_strategies = strategies or []
        self.buy_only_strategies = buy_strategies or []
        self.sell_only_strategies = sell_strategies or []

        all_subs = self.common_strategies + self.buy_only_strategies + self.sell_only_strategies
        self.min_bars_required = max((s.min_bars_required for s in all_subs), default=0)

    @property
    def buy_mode(self) -> str:
        return self.params.buy_mode

    @property
    def sell_mode(self) -> str:
        return self.params.sell_mode

    def get_brief(self) -> str:
        briefs = [s.get_brief() for s in self.common_strategies + self.buy_only_strategies if hasattr(s, "get_brief")]
        if not briefs:
            return super().get_brief()
        return " AND ".join(briefs) if self.params.buy_mode == "AND" else " OR ".join(briefs)

    def get_required_indicators(self) -> list[str]:
        reqs: list[str] = []
        for s in self.common_strategies + self.buy_only_strategies + self.sell_only_strategies:
            for req in s.get_required_indicators():
                if req not in reqs:
                    reqs.append(req)
        return reqs

    def describe(self) -> StrategyDescription:
        d = super().describe()
        return d.model_copy(
            update={
                "rationale": (
                    "Aggregates sub-strategies. Buy pool fires under "
                    f"`{self.params.buy_mode}`, sell pool under `{self.params.sell_mode}`. "
                    "On simultaneous BUY+SELL the SELL wins (capital-preservation default)."
                ),
                "signal_semantics": "Sell precedence over buy; AND = unanimous; OR = any.",
            }
        )

    def _compute_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()

        def run_pool(strats: list[SignalStrategy], prefix: str) -> list[str]:
            cols: list[str] = []
            for i, strat in enumerate(strats):
                res = strat.generate_signals(df)
                col = f"{prefix}_{i}_sig"
                df[col] = res["signal"]
                for c in res.columns:
                    if c not in df.columns:
                        df[c] = res[c]
                cols.append(col)
            return cols

        common_sigs = run_pool(self.common_strategies, "common")
        buy_only_sigs = run_pool(self.buy_only_strategies, "buy_only")
        sell_only_sigs = run_pool(self.sell_only_strategies, "sell_only")

        buy_pool = common_sigs + buy_only_sigs
        sell_pool = common_sigs + sell_only_sigs

        df["signal"] = 0

        if buy_pool:
            if self.params.buy_mode == "AND":
                is_buy = (df[buy_pool] == 1).all(axis=1)
            else:
                is_buy = (df[buy_pool] == 1).any(axis=1)
        else:
            is_buy = pd.Series(False, index=df.index)

        if sell_pool:
            if self.params.sell_mode == "AND":
                is_sell = (df[sell_pool] == -1).all(axis=1)
            else:
                is_sell = (df[sell_pool] == -1).any(axis=1)
        else:
            is_sell = pd.Series(False, index=df.index)

        # Sell wins on conflict — apply BUY first, then overwrite with SELL.
        df.loc[is_buy, "signal"] = 1
        df.loc[is_sell, "signal"] = -1

        return df
