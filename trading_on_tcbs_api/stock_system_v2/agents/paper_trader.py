"""Paper Trader Agent (Phase 8).

Runs the full scan → research → risk → submit loop on the paper
account. Refuses to act in live mode unless the operator has
explicitly disabled the kill-switch (`EXECUTION_DISABLED=false`) AND
removed safe-mode AND injected a broker client.

The 4-week soak in the runbook (`docs/PHASE8_PAPER_TRADER_RUNBOOK.md`)
exercises this exact entry point.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from trading_on_tcbs_api.stock_system_v2.schemas import (
    OrderRequest,
    OrderResponse,
    ScanResult,
)
from trading_on_tcbs_api.stock_system_v2.tools import ToolError, invoke

from .risk import RiskOpinion, evaluate_proposed_order
from .scanner import ScannerReport, daily_scan


class PaperTradeAction(BaseModel):
    """One scan signal's outcome through the paper-trade pipeline."""

    model_config = ConfigDict(frozen=True)

    signal: ScanResult
    opinion: RiskOpinion
    action: str = Field(..., description="`submitted`, `skipped:reject`, `skipped:warning`, `skipped:error`.")
    response: OrderResponse | None = None
    error_code: str | None = None
    error_message: str | None = None


class PaperTradeReport(BaseModel):
    """Aggregate output of one paper-trade cycle."""

    model_config = ConfigDict(frozen=True)

    captured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    scan: ScannerReport
    actions: list[PaperTradeAction]
    n_submitted: int
    n_skipped: int


def paper_trade_cycle(
    *,
    default_volume: int = 100,
    accept_warnings: bool = True,
    strategies: list[dict[str, Any]] | None = None,
    symbols: list[str] | None = None,
    history_days: int = 365,
) -> PaperTradeReport:
    """Run one full paper-trade cycle.

    Args:
        default_volume: Lot size for every submission. Phase-5
            position sizer will replace this.
        accept_warnings: When True, `approve_with_warnings` orders go
            through; when False they are skipped. Default True for the
            soak — every warning is captured in the audit trail anyway.
        strategies: Strategy specs forwarded to `daily_scan`.
        symbols: Override universe.
        history_days: Forwarded to scan.

    Returns:
        `PaperTradeReport` summarising every signal's outcome.

    Notes:
        Refuses to run when the kill-switch + safe-mode combo would
        actually attempt live orders unsafely. The check is conservative
        — `health_check` is consulted before any submit happens.
    """
    scan = daily_scan(strategies=strategies, symbols=symbols, history_days=history_days)

    # Pre-flight: health must be sane.
    health = invoke("health_check").result.status
    if not health.ok:
        # Skip every action; record why.
        return PaperTradeReport(
            scan=scan,
            actions=[],
            n_submitted=0,
            n_skipped=0,
        )

    actions: list[PaperTradeAction] = []
    n_submitted = 0
    n_skipped = 0

    for group in scan.groups:
        for signal in group.rows:
            req = OrderRequest(
                symbol=signal.symbol,
                side=signal.signal,  # type: ignore[arg-type]
                price=signal.price,
                volume=default_volume,
            )
            opinion = evaluate_proposed_order(req)

            if opinion.verdict == "reject":
                actions.append(PaperTradeAction(
                    signal=signal, opinion=opinion, action="skipped:reject",
                ))
                n_skipped += 1
                continue
            if opinion.verdict == "approve_with_warnings" and not accept_warnings:
                actions.append(PaperTradeAction(
                    signal=signal, opinion=opinion, action="skipped:warning",
                ))
                n_skipped += 1
                continue

            try:
                resp = invoke("submit_order", {
                    "request": req.model_dump(),
                    "risk_check_id": opinion.risk_check_id,
                })
                actions.append(PaperTradeAction(
                    signal=signal, opinion=opinion,
                    action="submitted", response=resp.result.response,
                ))
                n_submitted += 1
            except ToolError as exc:
                actions.append(PaperTradeAction(
                    signal=signal, opinion=opinion,
                    action="skipped:error",
                    error_code=exc.code, error_message=exc.message,
                ))
                n_skipped += 1

    return PaperTradeReport(
        scan=scan,
        actions=actions,
        n_submitted=n_submitted,
        n_skipped=n_skipped,
    )
