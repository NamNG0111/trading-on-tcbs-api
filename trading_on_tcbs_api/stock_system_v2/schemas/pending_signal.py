"""PendingSignal schema (Phase 10).

A `PendingSignal` is the durable representation of a scan-emitted signal
that is awaiting a human (or auto-mode) confirmation before placement.
Every signal the HITL coordinator dispatches becomes one row in
`EXPORT_DIR/pending_signals.jsonl`; state transitions append new rows so
a `kill -9` between any two steps recovers cleanly on restart — same
append-only contract the order ledger uses (Phase 5).

Status transitions are linear, except `awaiting → stale` skips placement:

    awaiting ─┬─ confirmed ─┬─ submitted   (revalidation passed, order placed)
              │             └─ failed      (broker rejected after revalidation)
              ├─ rejected                  (operator said no)
              ├─ expired                   (timeout hit before reply)
              └─ stale                     (revalidation failed; scanner takes over)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from trading_on_tcbs_api.stock_system_v2.schemas.revalidation import RevalidationResult

PendingSignalStatus = Literal[
    "awaiting",
    "confirmed",
    "rejected",
    "expired",
    "stale",
    "submitted",
    "failed",
]

TERMINAL_STATUSES: frozenset[PendingSignalStatus] = frozenset(
    {"rejected", "expired", "stale", "submitted", "failed"}
)

OPEN_STATUSES: frozenset[PendingSignalStatus] = frozenset({"awaiting", "confirmed"})


def _new_pending_id() -> str:
    """Default factory: short UUID prefixed `ps_` for log-grep convenience."""
    return f"ps_{uuid.uuid4().hex[:12]}"


class PendingSignal(BaseModel):
    """A scan-emitted signal queued for confirmation before placement.

    Carries enough state to re-instantiate the originating strategy on a
    fresh OHLCV fetch (re-validation requires this) plus the proposed
    order shape (so the post-confirmation path can build the OrderRequest
    without re-running the sizer). `correlation_id` chains every log line
    from scan → confirmation → revalidation → placement.
    """

    model_config = ConfigDict(frozen=False)  # status mutates via append-only store

    id: str = Field(default_factory=_new_pending_id)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime
    symbol: str = Field(..., min_length=1, max_length=10)
    side: Literal["BUY", "SELL"]
    strategy_name: str = Field(..., description="Registry id from `STRATEGIES`.")
    strategy_params: dict[str, object] = Field(
        default_factory=dict,
        description="Kwargs to re-instantiate the strategy via the registry.",
    )
    ref_price: float = Field(..., gt=0.0, description="Closed-bar price the original signal fired on, in VND.")
    ref_bar_close_ts: datetime = Field(..., description="Close timestamp of the bar the original signal fired on.")
    proposed_volume: int = Field(..., gt=0)
    proposed_notional_vnd: int = Field(..., gt=0)
    status: PendingSignalStatus = "awaiting"
    revalidation_result: RevalidationResult | None = None
    correlation_id: str = Field(..., description="Cycle-level correlation id from the scan that produced the signal.")
    notes: str | None = None

    @classmethod
    def from_scan(
        cls,
        *,
        symbol: str,
        side: Literal["BUY", "SELL"],
        strategy_name: str,
        ref_price: float,
        ref_bar_close_ts: datetime,
        proposed_volume: int,
        proposed_notional_vnd: int,
        correlation_id: str,
        timeout_seconds: int,
        strategy_params: dict[str, object] | None = None,
    ) -> "PendingSignal":
        """Construct a fresh `awaiting` pending signal with a TTL.

        `expires_at` is computed as `now + timeout_seconds` so the store
        can drop the row to `expired` without any operator action.
        """
        now = datetime.now(timezone.utc)
        return cls(
            created_at=now,
            expires_at=now + timedelta(seconds=timeout_seconds),
            symbol=symbol,
            side=side,
            strategy_name=strategy_name,
            strategy_params=strategy_params or {},
            ref_price=ref_price,
            ref_bar_close_ts=ref_bar_close_ts,
            proposed_volume=proposed_volume,
            proposed_notional_vnd=proposed_notional_vnd,
            correlation_id=correlation_id,
        )

    def is_expired(self, now: datetime | None = None) -> bool:
        """True iff the timeout window has elapsed."""
        ref = now or datetime.now(timezone.utc)
        return ref >= self.expires_at

    def is_terminal(self) -> bool:
        """True iff no further state transitions are expected."""
        return self.status in TERMINAL_STATUSES

    def with_status(
        self,
        status: PendingSignalStatus,
        *,
        revalidation_result: RevalidationResult | None = None,
        notes: str | None = None,
    ) -> "PendingSignal":
        """Return a copy with updated status (immutable-style update).

        The store writes the returned object as a new JSONL row; the
        previous row stays on disk for audit.
        """
        return self.model_copy(
            update={
                "status": status,
                "revalidation_result": revalidation_result
                if revalidation_result is not None
                else self.revalidation_result,
                "notes": notes if notes is not None else self.notes,
            }
        )
