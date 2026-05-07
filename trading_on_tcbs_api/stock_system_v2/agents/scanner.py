"""Scanner Agent (Phase 8).

Runs the morning scan across the universe and turns the raw
`ScanResult` rows into a structured, sortable `ScannerReport` an
operator can read at-a-glance.

Programmatic recipe drives `scan_market` then groups by strategy +
signal direction. The LLM equivalent (`prompts/scanner.md`) does the
same thing but writes a markdown daily report alongside.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from trading_on_tcbs_api.stock_system_v2.schemas import ScanResult
from trading_on_tcbs_api.stock_system_v2.tools import invoke


class ScanGroup(BaseModel):
    """Signals from one (strategy, direction) bucket."""

    model_config = ConfigDict(frozen=True)

    strategy: str
    side: str  # "BUY" / "SELL"
    n_signals: int
    symbols: list[str]
    rows: list[ScanResult]


class ScannerReport(BaseModel):
    """Structured daily scan summary."""

    model_config = ConfigDict(frozen=True)

    captured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    n_symbols: int
    n_strategies: int
    n_signals: int
    groups: list[ScanGroup]
    headline: str = Field(..., description="One-paragraph human-readable summary.")


def daily_scan(
    *,
    strategies: list[dict[str, Any]] | None = None,
    symbols: list[str] | None = None,
    history_days: int = 365,
) -> ScannerReport:
    """Run the daily scan and group the result by (strategy, side).

    Args:
        strategies: List of strategy specs (`{"name": ..., "params": {...}}`).
            Defaults to a sensible mix: RSI Reversal, SMA crossover, Volume
            Boom, Dip Buy. The agent prompt may override.
        symbols: Override the configured universe.
        history_days: How much history to feed each strategy.

    Returns:
        `ScannerReport` ready to be serialised into a daily markdown
        report or fed to a downstream agent.
    """
    if strategies is None:
        strategies = [
            {"name": "rsi", "params": {"is_reversal": True}, "label": "RSI Reversal"},
            {"name": "simple_ma", "params": {"short_window": 20, "long_window": 50}, "label": "SMA 20/50"},
            {"name": "volume_boom", "params": {"window": 20, "threshold_pct": 50.0}, "label": "Volume Boom"},
            {"name": "dip_buy", "params": {"sma_window": 20, "drop_pct": 10.0}, "label": "Dip Buy"},
        ]

    args: dict[str, Any] = {"strategies": strategies, "history_days": history_days}
    if symbols is not None:
        args["symbols"] = symbols
    resp = invoke("scan_market", args)
    out = resp.result

    # Group by (strategy_label, side).
    buckets: dict[tuple[str, str], list[ScanResult]] = {}
    for r in out.results:
        buckets.setdefault((r.strategy, r.signal), []).append(r)

    groups: list[ScanGroup] = [
        ScanGroup(
            strategy=label,
            side=side,
            n_signals=len(rows),
            symbols=sorted({r.symbol for r in rows}),
            rows=rows,
        )
        for (label, side), rows in sorted(buckets.items())
    ]

    headline = _build_headline(out.n_symbols, out.n_strategies, out.n_signals, groups)

    return ScannerReport(
        n_symbols=out.n_symbols,
        n_strategies=out.n_strategies,
        n_signals=out.n_signals,
        groups=groups,
        headline=headline,
    )


def _build_headline(n_symbols: int, n_strategies: int, n_signals: int, groups: list[ScanGroup]) -> str:
    if n_signals == 0:
        return (
            f"Quiet day: no strategy fired across {n_symbols} symbols × "
            f"{n_strategies} strategies."
        )
    buy = sum(g.n_signals for g in groups if g.side == "BUY")
    sell = sum(g.n_signals for g in groups if g.side == "SELL")
    top = max(groups, key=lambda g: g.n_signals, default=None)
    bias = "balanced"
    if buy and not sell:
        bias = "bullish skew"
    elif sell and not buy:
        bias = "bearish skew"
    elif buy > sell * 2:
        bias = "bullish skew"
    elif sell > buy * 2:
        bias = "bearish skew"
    top_str = (
        f" Top contributor: {top.strategy} {top.side} ({top.n_signals})."
        if top is not None else ""
    )
    return (
        f"{n_signals} signals across {n_symbols} symbols × {n_strategies} "
        f"strategies; {buy} BUY / {sell} SELL — {bias}.{top_str}"
    )
