"""Strategy-layer tools: list_strategies."""

from __future__ import annotations

from pydantic import BaseModel

from trading_on_tcbs_api.stock_system_v2.schemas import StrategyDescription
from trading_on_tcbs_api.stock_system_v2.strategies import STRATEGIES
from trading_on_tcbs_api.stock_system_v2.tools.registry import tool


class ListStrategiesIn(BaseModel):
    pass


class ListStrategiesOut(BaseModel):
    strategies: dict[str, StrategyDescription]


@tool("list_strategies", input_model=ListStrategiesIn, output_model=ListStrategiesOut)
def list_strategies(_: ListStrategiesIn) -> ListStrategiesOut:
    """Return every registered strategy + its agent-readable description.

    Each entry includes the strategy's `Params` JSON schema, declared
    `min_bars_required`, expected market regime, and known failure
    modes. The agent can use the params schema to construct a valid
    instance via `scan_market` / `run_backtest` without code-reading.
    """
    out: dict[str, StrategyDescription] = {}
    for name, cls in STRATEGIES.items():
        if name == "combined":
            continue  # meta-strategy; not constructible without sub-strategies.
        try:
            out[name] = cls().describe()
        except Exception:  # noqa: BLE001 — describe should never raise for our strategies
            continue
    return ListStrategiesOut(strategies=out)
