"""Order tools: validate_order, submit_order, cancel_order."""

from __future__ import annotations

from pydantic import BaseModel, Field

from trading_on_tcbs_api.stock_system_v2.exceptions import RiskLimitViolatedError
from trading_on_tcbs_api.stock_system_v2.schemas import (
    MarketContext,
    OrderRequest,
    OrderResponse,
    RiskCheckResult,
)
from trading_on_tcbs_api.stock_system_v2.tools.context import get_context
from trading_on_tcbs_api.stock_system_v2.tools.handlers.account import _snapshot
from trading_on_tcbs_api.stock_system_v2.tools.registry import tool


def _build_market_context(symbol: str) -> MarketContext:
    """Build a single-symbol `MarketContext` from the data layer."""
    ctx = get_context()
    last_close: float | None = None
    try:
        df = ctx.data_provider.get_historical_data(symbol, days=10, include_live=False)
        if not df.empty:
            last_close = float(df["close"].iloc[-1])
    except Exception:  # noqa: BLE001 — health-of-validator should not depend on data path
        pass
    return MarketContext(
        last_close_prices={symbol: last_close} if last_close is not None else {},
        lot_size=ctx.settings.risk.max_open_positions and 100,  # HoSE default
    )


# — validate_order —

class ValidateOrderIn(BaseModel):
    request: OrderRequest


class ValidateOrderOut(BaseModel):
    risk_check: RiskCheckResult


@tool("validate_order", input_model=ValidateOrderIn, output_model=ValidateOrderOut)
def validate_order(req: ValidateOrderIn) -> ValidateOrderOut:
    """Run every pre-trade rule for `request` and return a `RiskCheckResult`.

    The token has a 60-second TTL and a `request_hash` bound to the
    exact order fields. `submit_order` will refuse if the agent supplies
    a stale or hash-mismatched token.

    Idempotent in the read-only sense — the validator does not register
    the order or hold cash. The token is cached under
    `risk_tokens[check_id]` so the agent can submit by id alone.
    """
    ctx = get_context()
    market = _build_market_context(req.request.symbol)
    result = ctx.validator.validate(req.request, account=_snapshot(), market=market)
    ctx.risk_tokens[result.check_id] = (result, req.request)
    return ValidateOrderOut(risk_check=result)


# — submit_order —

class SubmitOrderIn(BaseModel):
    request: OrderRequest
    risk_check_id: str | None = Field(
        None,
        description="ID of a token previously returned by `validate_order`. Either this or `risk_check` must be set in live mode.",
    )
    risk_check: RiskCheckResult | None = Field(
        None,
        description="Caller-supplied token (alternative to `risk_check_id`).",
    )


class SubmitOrderOut(BaseModel):
    response: OrderResponse


@tool(
    "submit_order",
    input_model=SubmitOrderIn,
    output_model=SubmitOrderOut,
    side_effecting=True,
)
def submit_order(req: SubmitOrderIn) -> SubmitOrderOut:
    """Place an order. Side-effecting. Idempotent on `client_order_id`.

    In **live mode** (safe_mode=False), a fresh, hash-matching
    `RiskCheckResult` is required — supply it inline or via
    `risk_check_id` (returned by `validate_order` ≤ 60s ago).
    The token is consumed (one-shot) on submit.

    In **safe mode**, the validator is bypassed by `OrderManager` and
    no token is needed; the call still reserves a `client_order_id` in
    the tracker and returns a mocked `FILLED` response.

    Duplicate submits with the same `client_order_id` raise
    `DUPLICATE_ORDER`. Tracker idempotency survives process restarts.
    """
    ctx = get_context()
    token: RiskCheckResult | None = req.risk_check
    if token is None and req.risk_check_id is not None:
        cached = ctx.risk_tokens.get(req.risk_check_id)
        if cached is None:
            raise RiskLimitViolatedError(
                f"No cached risk token for id {req.risk_check_id!r}.",
                details={"check_id": req.risk_check_id},
            )
        token = cached[0]

    response = ctx.order_manager.place_order(
        request=req.request, risk_check=token,
    )

    # One-shot consumption.
    if req.risk_check_id is not None:
        ctx.risk_tokens.pop(req.risk_check_id, None)

    return SubmitOrderOut(response=response)


# — cancel_order —

class CancelOrderIn(BaseModel):
    broker_order_id: str = Field(..., min_length=1)


class CancelOrderOut(BaseModel):
    cancelled: bool


@tool(
    "cancel_order",
    input_model=CancelOrderIn,
    output_model=CancelOrderOut,
    side_effecting=True,
)
def cancel_order(req: CancelOrderIn) -> CancelOrderOut:
    """Cancel a broker-side order. Side-effecting.

    Returns `cancelled=True` on success. Safe mode always succeeds; live
    mode requires the order to still be open at the broker.
    """
    ok = get_context().order_manager.cancel_order(req.broker_order_id)
    return CancelOrderOut(cancelled=bool(ok))
