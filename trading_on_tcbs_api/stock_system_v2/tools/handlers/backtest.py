"""Backtest tools: run_backtest, walk_forward."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from trading_on_tcbs_api.stock_system_v2.core.backtester import Backtester
from trading_on_tcbs_api.stock_system_v2.core.costs import (
    TCBS_DEFAULT_COSTS,
    ZERO_COSTS,
    TransactionCosts,
)
from trading_on_tcbs_api.stock_system_v2.core.walk_forward import WalkForwardBacktester
from trading_on_tcbs_api.stock_system_v2.exceptions import InvalidParameterError
from trading_on_tcbs_api.stock_system_v2.schemas import (
    BacktestResult,
    WalkForwardResult,
    to_backtest_results,
)
from trading_on_tcbs_api.stock_system_v2.strategies import get_strategy
from trading_on_tcbs_api.stock_system_v2.tools.context import get_context
from trading_on_tcbs_api.stock_system_v2.tools.registry import tool


def _resolve_costs(name: str | None, override: dict[str, Any] | None) -> TransactionCosts:
    if override:
        return TransactionCosts(**override)
    if name == "zero":
        return ZERO_COSTS
    return TCBS_DEFAULT_COSTS


def _resolve_strategy(name: str, params: dict[str, Any]) -> Any:
    try:
        cls = get_strategy(name)
    except KeyError as exc:
        raise InvalidParameterError(str(exc), details={"name": name}) from exc
    try:
        return cls(params=params) if params else cls()
    except Exception as exc:  # noqa: BLE001
        raise InvalidParameterError(
            f"Could not instantiate strategy {name!r}: {exc}",
            details={"name": name, "params": params},
        ) from exc


# — run_backtest —

class RunBacktestIn(BaseModel):
    strategy: str
    symbol: str = Field(..., min_length=1, max_length=10)
    days: int = Field(365 * 2, ge=60, le=365 * 10)
    params: dict[str, Any] = Field(default_factory=dict)
    initial_capital: float = Field(100_000_000.0, gt=0.0)
    costs: str | None = Field("tcbs", description="Preset: 'tcbs' (default) or 'zero'.")
    costs_override: dict[str, Any] | None = Field(None, description="Explicit `TransactionCosts` fields override the preset.")


class RunBacktestOut(BaseModel):
    results: list[BacktestResult]


@tool("run_backtest", input_model=RunBacktestIn, output_model=RunBacktestOut)
def run_backtest(req: RunBacktestIn) -> RunBacktestOut:
    """Run a single-symbol backtest with TCBS-default costs.

    Returns one `BacktestResult` per holding regime: `holding_strategy="native"`
    (strategy-driven exits) plus one per fixed-hold horizon. Survivor
    bias is **not corrected** — every result carries the disclaimer
    field set to True/False accordingly.
    """
    ctx = get_context()
    strat = _resolve_strategy(req.strategy, req.params)
    bt = Backtester(
        initial_capital=req.initial_capital,
        costs=_resolve_costs(req.costs, req.costs_override),
        data_provider=ctx.data_provider,
        indicator_engine=ctx.indicator_engine,
    )
    report = bt.run(strat, symbol=req.symbol, days=req.days)
    return RunBacktestOut(results=to_backtest_results(report, strategy_name=req.strategy))


# — walk_forward —

class WalkForwardIn(BaseModel):
    strategy: str
    symbol: str = Field(..., min_length=1, max_length=10)
    days: int = Field(365 * 3, ge=180, le=365 * 10)
    params: dict[str, Any] = Field(default_factory=dict)
    train_bars: int = Field(252, ge=30, le=365 * 2)
    test_bars: int = Field(63, ge=5, le=365)
    step_bars: int | None = Field(None, description="Defaults to test_bars (non-overlapping).")
    initial_capital: float = Field(100_000_000.0, gt=0.0)
    costs: str | None = Field("tcbs")
    costs_override: dict[str, Any] | None = None


class WalkForwardOut(BaseModel):
    result: WalkForwardResult


@tool("walk_forward", input_model=WalkForwardIn, output_model=WalkForwardOut)
def walk_forward(req: WalkForwardIn) -> WalkForwardOut:
    """Walk-forward backtest: rolling (train, test) windows, OOS-only stats.

    The `train` segment is currently a warmup buffer; once parameter
    fitting lands a future revision will fit on `train` and freeze for
    `test`. Mandatory evidence for any "this strategy works" claim —
    in-sample backtests should not be cited.
    """
    ctx = get_context()
    strat = _resolve_strategy(req.strategy, req.params)
    bt = WalkForwardBacktester(
        train_bars=req.train_bars,
        test_bars=req.test_bars,
        step_bars=req.step_bars,
        initial_capital=req.initial_capital,
        costs=_resolve_costs(req.costs, req.costs_override),
        data_provider=ctx.data_provider,
        indicator_engine=ctx.indicator_engine,
    )
    res = bt.run(strat, symbol=req.symbol, days=req.days)
    return WalkForwardOut(result=res)
