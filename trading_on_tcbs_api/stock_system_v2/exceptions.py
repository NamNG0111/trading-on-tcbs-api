"""Typed exceptions for the V2 stock system (Phase 3).

The Phase-3 contract is: every public function either succeeds with a typed
return, or raises one of these. No `return None` to mean "something went
wrong"; no bare `except Exception: pass`. Agents reading a tool error need
the *kind* of failure, not just a message.

Hierarchy:

    StockSystemError                — root for everything we raise
    ├── DataFetchError              — generic upstream/data fetch failure
    │   ├── StaleCacheError         — cached frame older than the freshness budget
    │   └── InsufficientHistoryError — fewer bars than the strategy needs
    ├── InvalidParameterError       — bad input at a public boundary
    ├── AuthExpiredError            — JWT/OTP refresh required
    ├── OrderRejectedError          — broker or simulator refused the order
    └── RiskLimitViolatedError      — pre-trade validator blocked the order

Each error carries a structured `details` mapping that can be serialised
verbatim into a tool response so the caller (human or agent) can fix the
problem without round-tripping for clarification.
"""

from __future__ import annotations

from typing import Any, Mapping


class StockSystemError(Exception):
    """Root exception for all V2-system failures.

    The message stays human-readable; structured context goes in `details`.
    Subclasses should pass `details` through unchanged so layered handlers
    (e.g. a tool wrapper) can surface every field they need.
    """

    def __init__(self, message: str, *, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, Any] = dict(details or {})

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} | details={self.details}"
        return self.message


class DataFetchError(StockSystemError):
    """Upstream history/quote source failed (vnstock or TCBS REST).

    Use `details={"symbol": ..., "source": ..., "cause": str(exc)}` so the
    caller can decide whether to retry, fall back, or skip the symbol.
    """


class StaleCacheError(DataFetchError):
    """Cached OHLCV frame is older than the freshness budget for the request.

    Distinct from `DataFetchError` because the right response is usually
    "refresh and retry," not "give up."
    """


class InsufficientHistoryError(DataFetchError):
    """Cached/fetched frame has fewer bars than the strategy needs.

    Triggered when `len(closed_bars(df)) < min_bars_required`. Tools should
    surface the missing-bar count so the caller can pick a longer window.
    """


class InvalidParameterError(StockSystemError):
    """Caller passed a value that violates a public-boundary contract.

    Examples: negative `days`, unknown strategy name, malformed symbol, a
    `StrategyParams` field outside its declared range.
    """


class AuthExpiredError(StockSystemError):
    """JWT is expired or absent and a fresh OTP login is required.

    Distinct error class so an agent can route to the human (OTP) path
    rather than treat it as a generic API failure.
    """


class OrderRejectedError(StockSystemError):
    """Broker (or paper-simulator) rejected the order outright.

    Wraps both real-broker rejections (e.g. price-band, board, cash) and
    deterministic simulator rejections (e.g. duplicate `client_order_id`).
    """


class PositionDriftError(StockSystemError):
    """Local position book disagrees with the broker beyond tolerance.

    Carries the per-symbol diff in `details["diff"]: dict[symbol, (local, broker)]`.
    The system **never** silently overwrites local state on drift — the
    operator must reconcile manually before the autotrader can resume.
    """


class DuplicateOrderError(OrderRejectedError):
    """An order with the same `client_order_id` has already been placed.

    Subclass of `OrderRejectedError` so generic catch sites still see the
    rejection; agents that distinguish "duplicate" from "broker said no"
    can match on the precise type.
    """


class RiskLimitViolatedError(StockSystemError):
    """Pre-trade validator refused to authorise the order.

    Carry the violated rule(s) in `details["violations"]: list[str]` so the
    agent can report each one, and `details["check_id"]` so the audit log
    cross-references the `RiskCheckResult` row.
    """
