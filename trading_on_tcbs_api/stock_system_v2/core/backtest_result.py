"""Backwards-compatibility shim — the canonical home is `schemas.backtest`.

Existing callers (and the Phase-2 `WalkForwardBacktester`) import
`BacktestResult`/`WalkForwardResult` from this module; keeping the
re-export avoids a churn-only diff while we land Phase 3.
"""

from trading_on_tcbs_api.stock_system_v2.schemas.backtest import (
    BacktestResult,
    HoldingStrategy,
    WalkForwardResult,
    WalkForwardWindow,
    to_backtest_results,
)

__all__ = [
    "BacktestResult",
    "HoldingStrategy",
    "WalkForwardResult",
    "WalkForwardWindow",
    "to_backtest_results",
]
