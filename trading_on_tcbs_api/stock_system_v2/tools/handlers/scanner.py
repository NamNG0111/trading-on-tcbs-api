"""Scanner tool: scan_market."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from trading_on_tcbs_api.stock_system_v2.core.market_scanner import MarketScanner
from trading_on_tcbs_api.stock_system_v2.exceptions import InvalidParameterError
from trading_on_tcbs_api.stock_system_v2.schemas import ScanResult
from trading_on_tcbs_api.stock_system_v2.strategies import get_strategy
from trading_on_tcbs_api.stock_system_v2.tools.context import get_context
from trading_on_tcbs_api.stock_system_v2.tools.registry import tool


class StrategySpec(BaseModel):
    """One strategy to run inside `scan_market`.

    `name` is a registry id (see `list_strategies`); `params` is a dict
    that constructs the strategy's nested `Params` model.
    """

    name: str
    label: str | None = Field(None, description="Display name in the result rows; defaults to the registry id.")
    params: dict[str, Any] = Field(default_factory=dict)


class ScanMarketIn(BaseModel):
    strategies: list[StrategySpec] = Field(..., min_length=1)
    symbols: list[str] | None = Field(
        None,
        description="Override the configured universe. None → use Settings.symbols.",
    )
    history_days: int = Field(365, ge=60, le=365 * 5)


class ScanMarketOut(BaseModel):
    n_symbols: int
    n_strategies: int
    n_signals: int
    results: list[ScanResult]


@tool("scan_market", input_model=ScanMarketIn, output_model=ScanMarketOut)
def scan_market(req: ScanMarketIn) -> ScanMarketOut:
    """Run every strategy in `strategies` across `symbols` and return today's signals.

    Read-only. Builds a fresh `MarketScanner` per call so per-call
    `history_days` overrides don't leak between invocations.
    """
    ctx = get_context()

    instances: dict[str, Any] = {}
    for spec in req.strategies:
        try:
            cls = get_strategy(spec.name)
        except KeyError as exc:
            raise InvalidParameterError(str(exc), details={"name": spec.name}) from exc
        try:
            instance = cls(params=spec.params) if spec.params else cls()
        except Exception as exc:  # noqa: BLE001 — pydantic validation, mostly
            raise InvalidParameterError(
                f"Could not instantiate strategy {spec.name!r}: {exc}",
                details={"name": spec.name, "params": spec.params},
            ) from exc
        instances[spec.label or spec.name] = instance

    scanner = MarketScanner(
        data_provider=ctx.data_provider,
        indicator_engine=ctx.indicator_engine,
        strategies=instances,
        history_days=req.history_days,
    )
    symbols = req.symbols if req.symbols is not None else list(ctx.settings.symbols)
    results = scanner.scan(symbols)

    return ScanMarketOut(
        n_symbols=len(symbols),
        n_strategies=len(instances),
        n_signals=len(results),
        results=results,
    )
