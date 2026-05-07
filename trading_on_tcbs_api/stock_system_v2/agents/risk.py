"""Risk Agent (Phase 8) — read-only advisory.

Given a proposed order, runs `validate_order` and joins the result with
portfolio context (current positions, exposure already in this name).
Returns a typed `RiskOpinion` the operator (or paper trader) reads
before deciding to submit.

Read-only by construction: the validator caches the token under
`risk_tokens[check_id]` but the risk agent never calls `submit_order`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from trading_on_tcbs_api.stock_system_v2.schemas import (
    AccountSnapshot,
    OrderRequest,
    Position,
    RiskCheckResult,
)
from trading_on_tcbs_api.stock_system_v2.tools import invoke

OpinionVerdict = Literal["approve", "approve_with_warnings", "reject"]


class RiskOpinion(BaseModel):
    """Structured advisory output."""

    model_config = ConfigDict(frozen=True)

    request: OrderRequest
    verdict: OpinionVerdict
    rationale: str
    risk_check: RiskCheckResult
    risk_check_id: str = Field(..., description="Use as `risk_check_id` in submit_order.")
    portfolio: AccountSnapshot
    existing_position: Position | None = Field(
        None, description="Current holding in this name; None when flat."
    )
    notes: list[str] = Field(default_factory=list)


def evaluate_proposed_order(request: OrderRequest) -> RiskOpinion:
    """Validate `request` and join the result with portfolio context.

    The verdict is:
      - `reject` when the validator returns `passed=False`.
      - `approve_with_warnings` when validation passes but at least one
        non-BLOCK finding exists, or when the order substantially
        changes existing exposure (>2× current notional).
      - `approve` otherwise.

    The returned `risk_check_id` is the cached token id — pass it
    straight to `submit_order` if the operator approves.
    """
    val_resp = invoke("validate_order", {"request": request.model_dump()})
    risk = val_resp.result.risk_check
    acct_resp = invoke("get_account")
    portfolio = acct_resp.result.snapshot

    existing = next(
        (p for p in portfolio.positions if p.symbol == request.symbol),
        None,
    )

    notes: list[str] = []
    for f in risk.findings:
        if f.severity != "BLOCK":
            notes.append(f"{f.severity}: {f.rule} — {f.message}")

    verdict: OpinionVerdict
    rationale: str

    if not risk.passed:
        verdict = "reject"
        rationale = (
            f"Pre-trade validator blocked the order: {risk.violations}. "
            f"Fix and revalidate."
        )
    else:
        notional = request.price * request.volume
        if existing is not None and existing.market_value > 0:
            ratio = notional / max(existing.market_value, 1.0)
            if ratio > 2.0:
                notes.append(
                    f"Order notional is {ratio:.1f}× current exposure in {request.symbol}; "
                    "concentration risk worth a second look."
                )
        if existing is not None and request.side == "BUY":
            notes.append(
                f"Top-up of existing position ({existing.quantity} sh @ "
                f"{existing.avg_cost:,.0f}); not a new name."
            )
        if notes:
            verdict = "approve_with_warnings"
            rationale = (
                f"Validator passed; {len(notes)} non-blocking note(s) attached. "
                f"Operator review recommended before submit."
            )
        else:
            verdict = "approve"
            rationale = (
                f"Validator passed cleanly; portfolio context shows no "
                f"concentration concern for {request.symbol}."
            )

    return RiskOpinion(
        request=request,
        verdict=verdict,
        rationale=rationale,
        risk_check=risk,
        risk_check_id=risk.check_id,
        portfolio=portfolio,
        existing_position=existing,
        notes=notes,
    )
