"""OrderManager — places live or paper orders with full safety gating.

Phase-5 contract:

  - Every `place_order` call requires a fresh, matching `RiskCheckResult`
    when the manager is **not** in safe mode. The token's `request_hash`
    must equal `request_hash(req)` and `is_fresh()` must be True; any
    mismatch raises `RiskLimitViolatedError`.
  - `EXECUTION_DISABLED` (env var or `Settings.execution_disabled`) is a
    hard kill-switch — it overrides safe-mode and rejects every order.
  - `OrderTracker.register_pending(req)` is called **before** submission
    so a crash between submit and log still leaves a recovery breadcrumb.
  - Real TCBS submission uses `StockTradingClient.place_stock_order` (async).
    The sync `OrderManager` runs it under `asyncio.run` so existing call
    sites stay synchronous; AutoTrader's async loop can also `await` the
    underlying client directly when it lands an async order path.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Optional

from trading_on_tcbs_api.stock_system_v2 import config
from trading_on_tcbs_api.stock_system_v2.exceptions import (
    OrderRejectedError,
    RiskLimitViolatedError,
)
from trading_on_tcbs_api.stock_system_v2.execution.order_tracker import OrderTracker
from trading_on_tcbs_api.stock_system_v2.execution.pre_trade_validator import (
    request_hash,
)
from trading_on_tcbs_api.stock_system_v2.obs import (
    get_logger,
    log_event,
    record_metric,
    with_correlation,
    write_decision,
)
from trading_on_tcbs_api.stock_system_v2.schemas import (
    OrderRequest,
    OrderResponse,
    OrderSide,
    RiskCheckResult,
)

_logger = get_logger("order_manager")


class OrderManager:
    """Places live or paper orders with safe-mode + risk-token gating.

    Args:
        auth: Authenticated `StockAuth`. Required for live mode; ignored
            in safe mode.
        safe_mode: When True (default), every call returns a mocked
            `OrderResponse` and never hits the broker.
        execution_disabled: Hard kill-switch. When True, every call
            returns REJECTED regardless of `safe_mode`. Wired to
            `Settings.execution_disabled` (and `EXECUTION_DISABLED` env).
        tracker: `OrderTracker` for idempotency + audit. If omitted the
            manager builds a default one — supply your own to share
            ledger state across components.
        broker_client: Async TCBS client for live orders. Required only
            when `safe_mode=False`. Tests inject a fake.
    """

    def __init__(
        self,
        auth: Any,
        *,
        safe_mode: bool = True,
        execution_disabled: bool = False,
        tracker: Optional[OrderTracker] = None,
        broker_client: Any = None,
    ) -> None:
        self.auth = auth
        self.safe_mode = safe_mode
        self.execution_disabled = execution_disabled
        self.base_url = config.BASE_URL
        self.tracker = tracker if tracker is not None else OrderTracker()
        self.broker_client = broker_client
        log_event(
            _logger, "order_manager.init",
            safe_mode=self.safe_mode, execution_disabled=self.execution_disabled,
        )

    def place_order(
        self,
        symbol: str | OrderRequest | None = None,
        side: OrderSide | str | None = None,
        price: float | None = None,
        volume: int | None = None,
        order_type: str = "LO",
        *,
        request: OrderRequest | None = None,
        risk_check: RiskCheckResult | None = None,
    ) -> OrderResponse:
        """Submit one order, after every safety check has passed.

        Calling conventions:
          - **Typed (preferred):** `place_order(request=OrderRequest(...), risk_check=...)`.
          - **Legacy positional:** `place_order(symbol, side, price, volume, order_type)`.
            The kwargs build an `OrderRequest` so Pydantic still validates.

        Risk-check gating:
          - Safe mode allows `risk_check=None` (paper trading skips the
            validator). Live mode requires a fresh, matching token.

        Returns:
            `OrderResponse`. Status `FILLED` (safe-mode mock), `ACCEPTED`
            / `PARTIALLY_FILLED` / `FILLED` (live), or `REJECTED`
            (kill-switch / broker refusal / dry-run validator).

        Raises:
            RiskLimitViolatedError: in live mode without a valid token,
                or when the token is stale / hash-mismatched / failed.
            DuplicateOrderError: when the tracker has already seen the
                `client_order_id` (idempotency).
            OrderRejectedError: when the broker call itself raises.
        """
        req = self._build_request(symbol, side, price, volume, order_type, request)

        with with_correlation(prefix="order"):
            return self._place_order_inner(req, risk_check)

    def _place_order_inner(
        self, req: OrderRequest, risk_check: Optional[RiskCheckResult]
    ) -> OrderResponse:
        if self.execution_disabled:
            resp = OrderResponse(
                client_order_id=req.client_order_id,
                status="REJECTED",
                note="EXECUTION_DISABLED kill-switch is on.",
            )
            self.tracker.log_order(resp, req.symbol, req.side, req.price, req.volume)
            log_event(_logger, "order.rejected.kill_switch", request=req)
            record_metric("orders.rejected", 1.0, reason="kill_switch")
            self._audit(req, resp, risk_check, decision="reject:kill_switch")
            return resp

        if not self.safe_mode:
            self._enforce_risk_token(req, risk_check)

        # Idempotency: register before the wire call so a crash between
        # submit and log still surfaces the order on recovery.
        self.tracker.register_pending(req)
        log_event(_logger, "order.registered", request=req)
        record_metric("orders.placed", 1.0, symbol=req.symbol, side=req.side)

        if self.safe_mode:
            mock_id = f"mock_{uuid.uuid4().hex[:8]}"
            resp = OrderResponse(
                client_order_id=req.client_order_id,
                broker_order_id=mock_id,
                status="FILLED",
                filled_volume=req.volume,
                avg_fill_price=req.price,
                note="Safe-mode dry run.",
            )
            self.tracker.log_order(resp, req.symbol, req.side, req.price, req.volume)
            log_event(_logger, "order.filled.safe_mode", request=req, broker_order_id=mock_id)
            record_metric("orders.filled", 1.0, symbol=req.symbol, mode="safe")
            self._audit(req, resp, risk_check, decision="submit:safe_mode")
            return resp

        # — live path —
        if self.broker_client is None:
            raise OrderRejectedError(
                "Live trading requires a broker_client; refusing to submit.",
                details={"client_order_id": req.client_order_id},
            )

        log_event(_logger, "order.live.submit", request=req)

        try:
            broker_id = self._call_broker_sync(req)
        except OrderRejectedError:
            record_metric("orders.rejected", 1.0, reason="broker", symbol=req.symbol)
            raise
        except (RuntimeError, ValueError, OSError) as exc:
            resp = OrderResponse(
                client_order_id=req.client_order_id,
                status="REJECTED",
                note=f"Broker call failed: {exc!r}",
            )
            self.tracker.log_order(resp, req.symbol, req.side, req.price, req.volume)
            log_event(_logger, "order.live.broker_error", request=req, cause=str(exc), level=40)
            record_metric("orders.rejected", 1.0, reason="broker_error", symbol=req.symbol)
            self._audit(req, resp, risk_check, decision="reject:broker_error")
            raise OrderRejectedError(
                f"Broker call failed for {req.symbol}",
                details={"client_order_id": req.client_order_id, "cause": str(exc)},
            ) from exc

        if broker_id is None:
            resp = OrderResponse(
                client_order_id=req.client_order_id,
                status="REJECTED",
                note="Broker returned no order id.",
            )
            self.tracker.log_order(resp, req.symbol, req.side, req.price, req.volume)
            log_event(_logger, "order.live.no_id", request=req, level=40)
            record_metric("orders.rejected", 1.0, reason="no_broker_id", symbol=req.symbol)
            self._audit(req, resp, risk_check, decision="reject:no_broker_id")
            return resp

        resp = OrderResponse(
            client_order_id=req.client_order_id,
            broker_order_id=str(broker_id),
            status="ACCEPTED",
            filled_volume=0,
            note="Submitted to TCBS; awaiting fill confirmation.",
        )
        self.tracker.log_order(resp, req.symbol, req.side, req.price, req.volume)
        log_event(_logger, "order.live.accepted", request=req, broker_order_id=str(broker_id))
        record_metric("orders.accepted", 1.0, symbol=req.symbol, mode="live")
        self._audit(req, resp, risk_check, decision="submit:live")
        return resp

    def _audit(
        self,
        req: OrderRequest,
        resp: OrderResponse,
        risk_check: Optional[RiskCheckResult],
        *,
        decision: str,
    ) -> None:
        """Append one row to `decisions.jsonl` for the audit trail."""
        try:
            write_decision({
                "decision": decision,
                "symbol": req.symbol,
                "side": req.side,
                "request": req.model_dump(),
                "response": resp.model_dump(),
                "risk_check": risk_check.model_dump() if risk_check else None,
                "safe_mode": self.safe_mode,
                "execution_disabled": self.execution_disabled,
            })
        except OSError as exc:
            log_event(_logger, "audit.write_failed", level=40, cause=str(exc))

    def cancel_order(self, order_id: str) -> bool:
        """Cancel a broker-side order. Returns True on success.

        Safe mode always returns True. Live mode requires `broker_client`.
        """
        if self.execution_disabled:
            log_event(_logger, "order.cancel.kill_switch", broker_order_id=order_id, level=30)
            return False
        if self.safe_mode:
            log_event(_logger, "order.cancel.safe_mode", broker_order_id=order_id)
            return True
        if self.broker_client is None:
            return False
        try:
            return bool(asyncio.run(self.broker_client.cancel_stock_order(order_id)))
        except (RuntimeError, ValueError, OSError) as exc:
            log_event(_logger, "order.cancel.failed", broker_order_id=order_id, cause=str(exc), level=40)
            return False

    # — internals —

    @staticmethod
    def _build_request(
        symbol: str | OrderRequest | None,
        side: str | None,
        price: float | None,
        volume: int | None,
        order_type: str,
        request: OrderRequest | None,
    ) -> OrderRequest:
        if isinstance(symbol, OrderRequest):
            return symbol
        if request is not None:
            return request
        if not symbol or side is None or price is None or volume is None:
            raise TypeError(
                "place_order requires symbol/side/price/volume or a `request=` OrderRequest."
            )
        norm_side = side.upper()
        if norm_side == "NB":
            norm_side = "BUY"
        elif norm_side == "NS":
            norm_side = "SELL"
        return OrderRequest(
            symbol=symbol,
            side=norm_side,  # type: ignore[arg-type]
            price=float(price),
            volume=int(volume),
            order_type=order_type,  # type: ignore[arg-type]
        )

    def _enforce_risk_token(self, req: OrderRequest, token: Optional[RiskCheckResult]) -> None:
        if token is None:
            raise RiskLimitViolatedError(
                "Live order requires a RiskCheckResult; none supplied.",
                details={"client_order_id": req.client_order_id},
            )
        if not token.passed:
            raise RiskLimitViolatedError(
                "RiskCheckResult.passed is False.",
                details={"violations": token.violations, "check_id": token.check_id},
            )
        if not token.is_fresh():
            raise RiskLimitViolatedError(
                "RiskCheckResult has expired.",
                details={"check_id": token.check_id, "issued_at": str(token.issued_at)},
            )
        expected = request_hash(req)
        if token.request_hash != expected:
            raise RiskLimitViolatedError(
                "RiskCheckResult.request_hash does not match the OrderRequest.",
                details={
                    "expected": expected,
                    "received": token.request_hash,
                    "check_id": token.check_id,
                },
            )

    def _call_broker_sync(self, req: OrderRequest) -> Any:
        """Block-call the async TCBS client from a sync context.

        Kept as a separate method so tests can override (`broker_client`
        is async by contract; a sync test fake can monkeypatch this).
        """
        return asyncio.run(
            self.broker_client.place_stock_order(
                symbol=req.symbol,
                side=req.side,
                quantity=req.volume,
                price=req.price,
                order_type=req.order_type,
            )
        )
