"""Unified Pydantic schema for backtest output (Phase 2 / Phase 3 prep).

Folds the native (strategy-driven entry/exit) and fixed-hold (BUY then exit
after N days) paths into a single discriminated record via the
`holding_strategy: "native" | "fixed"` field. Survivor-bias is now an
explicit boolean every report carries — agents must read it.

This object is the canonical return type for the upcoming `run_backtest`
tool. The legacy `Backtester.run` method still returns its dict for
backwards compatibility; `to_backtest_results` adapts the dict.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

HoldingStrategy = Literal["native", "fixed"]


class BacktestResult(BaseModel):
    """Single-symbol backtest outcome under one holding regime."""

    symbol: str
    strategy_name: str
    holding_strategy: HoldingStrategy = Field(..., description="`native` = strategy-driven exits; `fixed` = exit after N bars.")
    fixed_hold_days: int | None = Field(None, description="Bars held when `holding_strategy='fixed'`; null otherwise.")

    start_date: str
    end_date: str
    initial_capital: float

    final_value: float
    total_return_pct: float
    total_trades: int
    win_rate_pct: float
    max_drawdown_pct: float
    profit_factor: float = Field(..., description="Gross profit / gross loss; inf when no losing trades exist.")
    avg_hold_days: float = 0.0

    # Phase 2 fields —
    costs: dict[str, object] = Field(default_factory=dict, description="`TransactionCosts.model_dump()` snapshot used for the run.")
    sizer_name: str = Field("AllInSizer", description="Class name of the position sizer applied.")
    survivor_bias_corrected: bool = Field(False, description="True only if the universe was filtered for delisted symbols.")
    survivor_bias_disclaimer: str = Field(
        "Survivor bias has not been corrected; results may overstate live performance because delisted symbols are absent from the universe.",
        description="Plain-English warning for agents/operators reading this report.",
    )


def to_backtest_results(report: dict[str, object], *, strategy_name: str) -> list[BacktestResult]:
    """Adapt a `Backtester.run` dict into the new schema.

    Returns one entry per holding regime: 1 native + 1-per-N for fixed-hold.
    """
    if not report:
        return []

    base_kwargs = {
        "symbol": report["symbol"],
        "strategy_name": strategy_name,
        "start_date": report["start_date"],
        "end_date": report["end_date"],
        "initial_capital": report["initial_capital"],
        "costs": report.get("costs", {}),
        "sizer_name": report.get("sizer_name", "AllInSizer"),
        "survivor_bias_corrected": report.get("survivor_bias_corrected", False),
    }

    out: list[BacktestResult] = [
        BacktestResult(
            holding_strategy="native",
            fixed_hold_days=None,
            final_value=report["final_value"],
            total_return_pct=report["total_return_pct"],
            total_trades=report["total_trades"],
            win_rate_pct=report["win_rate_pct"],
            max_drawdown_pct=report["max_drawdown_pct"],
            profit_factor=report["profit_factor"],
            avg_hold_days=report.get("avg_hold_days", 0.0),
            **base_kwargs,
        )
    ]

    raw_fixed = report.get("fixed_hold_results") or {}
    fixed_hold: dict[int, dict[str, float]] = raw_fixed if isinstance(raw_fixed, dict) else {}
    for days, stats in fixed_hold.items():
        out.append(
            BacktestResult(
                holding_strategy="fixed",
                fixed_hold_days=int(days),
                final_value=float(base_kwargs["initial_capital"]) * (1.0 + stats["total_return_pct"] / 100.0),  # type: ignore[arg-type]
                total_return_pct=stats["total_return_pct"],
                total_trades=stats["total_trades"],
                win_rate_pct=stats["win_rate_pct"],
                max_drawdown_pct=0.0,  # not tracked in the fixed-hold sim today
                profit_factor=0.0,
                avg_hold_days=float(days),
                **base_kwargs,
            )
        )

    return out


class WalkForwardWindow(BaseModel):
    """Single OOS window's stats."""

    window_index: int = Field(..., ge=0)
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    n_test_trades: int
    test_return_pct: float
    test_win_rate_pct: float
    test_max_drawdown_pct: float


class WalkForwardResult(BaseModel):
    """Aggregated out-of-sample stats from a walk-forward run.

    Out-of-sample only by construction: train windows are used to *select*
    or *parameterise* the strategy (today: a no-op, since strategies are
    fixed-param), and the reported metrics aggregate the test windows
    only. In-sample numbers are intentionally not reported — the whole
    point of walk-forward is that they're misleading.
    """

    symbol: str
    strategy_name: str
    n_windows: int
    oos_total_return_pct: float = Field(..., description="Compounded return across all OOS windows.")
    oos_avg_window_return_pct: float
    oos_win_rate_pct: float
    oos_total_trades: int
    windows: list[WalkForwardWindow]
    costs: dict[str, object] = Field(default_factory=dict)
    sizer_name: str = "AllInSizer"
    survivor_bias_corrected: bool = False
    survivor_bias_disclaimer: str = (
        "Survivor bias has not been corrected; OOS results may still overstate live performance "
        "because delisted symbols are absent from the universe."
    )
