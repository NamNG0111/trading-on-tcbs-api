"""Strategy registry — single source of truth for "what strategies exist".

Phase-4 deliverable: an agent calling `list_strategies()` (Phase 7 tool)
gets back a dict keyed on the registry id, mapped to the strategy class.
From there it can call `cls().describe()` to get a `StrategyDescription`
including the JSON schema for `Params`, then instantiate by name with
validated arguments.

Adding a new strategy = adding one entry below. The registry is
populated at import time so a missing entry surfaces immediately when
the module is loaded.
"""

from __future__ import annotations

from typing import Type

from .combined_strategy import CombinedStrategy
from .cumulative_drop_strategy import CumulativeDropStrategy
from .dip_buy_strategy import DipBuyStrategy
from .intraday_dip_strategy import IntradayDipStrategy
from .ma_strategy import SimpleMAStrategy
from .rsi_divergence_strategy import RSIDivergenceStrategy
from .rsi_strategy import RSIStrategy
from .strategy import SignalStrategy
from .volume_strategy import VolumeBoomStrategy

STRATEGIES: dict[str, Type[SignalStrategy]] = {
    "simple_ma": SimpleMAStrategy,
    "rsi": RSIStrategy,
    "rsi_divergence": RSIDivergenceStrategy,
    "volume_boom": VolumeBoomStrategy,
    "dip_buy": DipBuyStrategy,
    "cumulative_drop": CumulativeDropStrategy,
    "intraday_dip": IntradayDipStrategy,
    # CombinedStrategy is a meta-strategy — registered for completeness so
    # `list_strategies()` returns every constructible class, but it cannot
    # be instantiated without sub-strategies.
    "combined": CombinedStrategy,
}


def get_strategy(name: str) -> Type[SignalStrategy]:
    """Look up a strategy class by registry id.

    Raises:
        KeyError: when `name` isn't registered. The error message lists
            every available id so an agent can self-correct.
    """
    if name not in STRATEGIES:
        available = ", ".join(sorted(STRATEGIES))
        raise KeyError(f"Unknown strategy '{name}'. Available: {available}")
    return STRATEGIES[name]
