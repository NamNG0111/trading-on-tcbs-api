"""Research Agent (Phase 8).

Answers questions of the form "which strategy looks best on `symbol`
over the last `days`?" by running every registered strategy through
`walk_forward` and ranking by out-of-sample Sharpe. The output is a
typed `ResearchNote` an operator can audit row-by-row.

Two views:

  1. Programmatic recipe (`research_strategy_for_symbol`) — drives the
     tool layer directly. Deterministic, testable, no LLM.
  2. LLM system prompt (`prompts/research.md`) — describes the toolbelt
     and the expected output schema for an Anthropic API session.

Both are equivalent in tool-call sequence. The DoD example —
"best strategy for HPG right now?" — is exactly the input to
`research_strategy_for_symbol("HPG")`.
"""

from __future__ import annotations

import math
import statistics
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from trading_on_tcbs_api.stock_system_v2.tools import ToolError, invoke


class StrategyEvaluation(BaseModel):
    """One strategy's measured behaviour on `symbol` over the test window."""

    model_config = ConfigDict(frozen=True)

    strategy: str
    n_windows: int
    oos_total_return_pct: float
    oos_avg_window_return_pct: float
    oos_win_rate_pct: float
    oos_total_trades: int
    sharpe: float = Field(..., description="Annualised quasi-Sharpe over per-window returns. NaN when <2 windows or zero variance.")
    max_window_drawdown_pct: float
    notes: list[str] = Field(default_factory=list)


class ResearchNote(BaseModel):
    """Structured answer to 'best strategy for symbol X over window Y'."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    window_days: int
    universe: list[str] = Field(..., description="Strategies actually evaluated.")
    skipped: dict[str, str] = Field(default_factory=dict, description="Strategy → skip reason.")
    evaluations: list[StrategyEvaluation]
    recommended: str | None = Field(
        None,
        description="Top-ranked strategy by Sharpe, or None when no evaluation was viable.",
    )
    rationale: str
    survivor_bias_disclaimer: str = (
        "Survivor bias has not been corrected; results may overstate live "
        "performance because delisted symbols are absent from the universe."
    )


# Strategies that are meaningless to run alone (meta-strategies, etc.).
_SKIP_BY_DEFAULT = frozenset({"combined"})


def _annualised_sharpe(per_window_pct: list[float], windows_per_year: float = 4.0) -> float:
    """Quasi-Sharpe over per-window returns. Returns NaN when undefined."""
    if len(per_window_pct) < 2:
        return float("nan")
    decimals = [r / 100.0 for r in per_window_pct]
    mean = statistics.mean(decimals)
    stdev = statistics.pstdev(decimals)
    if stdev == 0:
        return 0.0
    return (mean / stdev) * math.sqrt(windows_per_year)


def research_strategy_for_symbol(
    symbol: str,
    *,
    days: int = 365 * 3,
    train_bars: int = 252,
    test_bars: int = 63,
    skip: frozenset[str] = _SKIP_BY_DEFAULT,
) -> ResearchNote:
    """Walk-forward every strategy on `symbol` and rank by OOS Sharpe.

    Args:
        symbol: Ticker to evaluate.
        days: History window for the WF run. Default 3 years.
        train_bars: Warmup buffer (no parameter fitting yet).
        test_bars: OOS test segment per window.
        skip: Strategy registry ids to skip. Default skips meta-only
            entries (`combined`) which can't be instantiated alone.

    Returns:
        `ResearchNote` ranking each strategy.
    """
    strategies_resp = invoke("list_strategies")
    strategy_names = [n for n in strategies_resp.result.strategies if n not in skip]

    evaluations: list[StrategyEvaluation] = []
    skipped: dict[str, str] = {}

    for name in strategy_names:
        try:
            resp = invoke("walk_forward", {
                "strategy": name,
                "symbol": symbol,
                "days": days,
                "train_bars": train_bars,
                "test_bars": test_bars,
            })
        except ToolError as exc:
            skipped[name] = f"{exc.code}: {exc.message}"
            continue

        wf = resp.result.result
        if wf.n_windows == 0:
            skipped[name] = "no walk-forward windows produced (history too short)"
            continue

        per_window = [w.test_return_pct for w in wf.windows]
        sharpe = _annualised_sharpe(per_window)
        max_dd = min((w.test_max_drawdown_pct for w in wf.windows), default=0.0)

        notes: list[str] = []
        if wf.oos_total_trades == 0:
            notes.append("zero trades — strategy never fired in the test window")
        if math.isnan(sharpe):
            notes.append("sharpe undefined (only one window or zero variance)")

        evaluations.append(StrategyEvaluation(
            strategy=name,
            n_windows=wf.n_windows,
            oos_total_return_pct=wf.oos_total_return_pct,
            oos_avg_window_return_pct=wf.oos_avg_window_return_pct,
            oos_win_rate_pct=wf.oos_win_rate_pct,
            oos_total_trades=wf.oos_total_trades,
            sharpe=sharpe,
            max_window_drawdown_pct=max_dd,
            notes=notes,
        ))

    # Rank by Sharpe (NaN sorts last). Tie-break on OOS total return.
    def _rank_key(e: StrategyEvaluation) -> tuple[float, float]:
        s = e.sharpe if math.isfinite(e.sharpe) else float("-inf")
        return (s, e.oos_total_return_pct)

    ranked = sorted(evaluations, key=_rank_key, reverse=True)
    recommended: str | None = None
    rationale: str

    if not ranked:
        rationale = (
            f"No strategy produced a usable walk-forward result for {symbol} over "
            f"{days} days. Either the history is too short or every strategy errored. "
            f"Skipped: {skipped}."
        )
    else:
        top = ranked[0]
        if not math.isfinite(top.sharpe) or top.oos_total_trades == 0:
            rationale = (
                f"No strategy produced a defensible result for {symbol}. The top "
                f"candidate ({top.strategy}) has Sharpe={top.sharpe} and "
                f"{top.oos_total_trades} OOS trade(s). Treat as inconclusive."
            )
        else:
            recommended = top.strategy
            rationale = (
                f"On {symbol} over {days} days, {top.strategy} ranks first by "
                f"OOS Sharpe ({top.sharpe:.2f}) with {top.oos_total_trades} "
                f"trades and an OOS compounded return of "
                f"{top.oos_total_return_pct:.2f}%. Worst per-window drawdown "
                f"was {top.max_window_drawdown_pct:.2f}%. Survivor bias is not "
                f"corrected; treat the headline number as an upper bound."
            )

    return ResearchNote(
        symbol=symbol,
        window_days=days,
        universe=[e.strategy for e in evaluations],
        skipped=skipped,
        evaluations=ranked,
        recommended=recommended,
        rationale=rationale,
    )
