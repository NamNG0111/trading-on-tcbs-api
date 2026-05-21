"""HITL tools: list_pending_signals, confirm_signal, reject_signal, set_trading_mode.

These let an MCP client (or future web UI) drive the human-in-the-loop
path that lives in `execution/hitl/coordinator.py`. The coordinator and
pending-signal store must be wired onto the `ToolContext` at process
start; absent them, the tools fail loudly so the operator can't approve
real money on a half-configured process.

Async-from-sync: the coordinator methods are async. The tool framework
is sync, so each side-effecting tool wraps the coro in `asyncio.run`.
That works fine inside the MCP transport thread and inside test code
that uses `invoke()` directly. It will NOT work if a caller is already
inside a running event loop — by design, since the tool was meant for
out-of-band confirmation, not in-cycle dispatch.
"""

from __future__ import annotations

import asyncio
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from trading_on_tcbs_api.stock_system_v2.exceptions import (
    InvalidParameterError,
    StockSystemError,
)
from trading_on_tcbs_api.stock_system_v2.schemas import PendingSignal
from trading_on_tcbs_api.stock_system_v2.tools.context import get_context
from trading_on_tcbs_api.stock_system_v2.tools.registry import tool


class _ConfigError(StockSystemError):
    """Raised when a tool is called against an unconfigured context."""


def _coordinator():
    coord = get_context().hitl_coordinator
    if coord is None:
        raise _ConfigError(
            "HITL coordinator is not configured on this ToolContext. "
            "Wire `hitl_coordinator` before invoking HITL tools."
        )
    return coord


def _store():
    ctx = get_context()
    store = ctx.pending_signal_store
    if store is None and ctx.hitl_coordinator is not None:
        store = ctx.hitl_coordinator.store
    if store is None:
        raise _ConfigError(
            "Pending-signal store is not configured. "
            "Set `pending_signal_store` (or `hitl_coordinator`) on the ToolContext."
        )
    return store


# — list_pending_signals (read-only) —


class ListPendingSignalsIn(BaseModel):
    include_terminal: bool = Field(
        False,
        description="When True, also return rows in terminal statuses (submitted/rejected/expired/stale/failed).",
    )
    limit: int | None = Field(
        None, ge=1, le=500,
        description="Optional cap on the number of rows returned. None returns all.",
    )


class ListPendingSignalsOut(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    open_count: int
    signals: list[PendingSignal]


@tool(
    "list_pending_signals",
    input_model=ListPendingSignalsIn,
    output_model=ListPendingSignalsOut,
)
def list_pending_signals(req: ListPendingSignalsIn) -> ListPendingSignalsOut:
    """List queued HITL signals. Read-only.

    By default returns only `awaiting` / `confirmed` rows — the ones an
    operator might still want to act on. Pass `include_terminal=True`
    to see the full audit trail for the current session.
    """
    store = _store()
    open_signals = store.load_open()
    if req.include_terminal:
        # iter_all yields every transition; collapse to latest-per-id.
        latest: dict[str, PendingSignal] = {}
        for sig in store.iter_all():
            latest[sig.id] = sig
        result = list(latest.values())
        result.sort(key=lambda s: s.created_at, reverse=True)
    else:
        result = sorted(open_signals, key=lambda s: s.created_at, reverse=True)
    if req.limit is not None:
        result = result[: req.limit]
    return ListPendingSignalsOut(open_count=len(open_signals), signals=result)


# — confirm_signal (side-effecting) —


class ConfirmSignalIn(BaseModel):
    signal_id: str = Field(..., min_length=1)


class ConfirmSignalOut(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    signal: PendingSignal


@tool(
    "confirm_signal",
    input_model=ConfirmSignalIn,
    output_model=ConfirmSignalOut,
    side_effecting=True,
)
def confirm_signal(req: ConfirmSignalIn) -> ConfirmSignalOut:
    """Confirm an `awaiting` HITL signal. Side-effecting; one-shot.

    Routes through the same revalidator + validator + order_manager that
    a channel-driven `yes` would. Idempotent on already-terminal signals.

    Raises `INVALID_PARAMS` when `signal_id` is unknown.
    """
    coord = _coordinator()
    try:
        sig = asyncio.run(coord.confirm_pending(req.signal_id))
    except KeyError as exc:
        raise InvalidParameterError(
            f"unknown pending signal id: {req.signal_id}",
            details={"signal_id": req.signal_id},
        ) from exc
    return ConfirmSignalOut(signal=sig)


# — reject_signal (side-effecting) —


class RejectSignalIn(BaseModel):
    signal_id: str = Field(..., min_length=1)
    reason: str | None = Field(None, description="Optional operator note recorded in the audit row.")


class RejectSignalOut(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    signal: PendingSignal


@tool(
    "reject_signal",
    input_model=RejectSignalIn,
    output_model=RejectSignalOut,
    side_effecting=True,
)
def reject_signal(req: RejectSignalIn) -> RejectSignalOut:
    """Reject an `awaiting` HITL signal. Side-effecting; idempotent."""
    coord = _coordinator()
    try:
        sig = asyncio.run(coord.reject_pending(req.signal_id))
    except KeyError as exc:
        raise InvalidParameterError(
            f"unknown pending signal id: {req.signal_id}",
            details={"signal_id": req.signal_id},
        ) from exc
    return RejectSignalOut(signal=sig)


# — set_trading_mode (side-effecting; explicit confirm flag) —


class SetTradingModeIn(BaseModel):
    mode: Literal["hitl", "auto"]
    confirm: bool = Field(
        False,
        description="Must be True to apply the change — guards against accidental auto-mode flips.",
    )


class SetTradingModeOut(BaseModel):
    previous: Literal["hitl", "auto"]
    current: Literal["hitl", "auto"]
    applied: bool


@tool(
    "set_trading_mode",
    input_model=SetTradingModeIn,
    output_model=SetTradingModeOut,
    side_effecting=True,
)
def set_trading_mode(req: SetTradingModeIn) -> SetTradingModeOut:
    """Toggle HITL ↔ auto at runtime. Side-effecting.

    Caller MUST pass `confirm=True`. The flag exists so a stray
    `set_trading_mode({"mode": "auto"})` cannot quietly disable the
    human gate — both the LLM and the human reviewer have to agree to
    the change.

    The toggle is in-process only; restart reverts to `Settings.trading_mode`.
    """
    coord = _coordinator()
    if not req.confirm:
        return SetTradingModeOut(
            previous=coord.trading_mode,
            current=coord.trading_mode,
            applied=False,
        )
    prev = coord.trading_mode
    new = coord.set_trading_mode(req.mode)
    return SetTradingModeOut(previous=prev, current=new, applied=True)
