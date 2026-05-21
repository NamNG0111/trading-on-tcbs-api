"""Confirmation channel protocol + shared response schema (Phase 10).

A `ConfirmationChannel` answers one question for the HITL coordinator:
"does the human want to place this order?" The protocol is intentionally
narrow so terminal, Telegram, web, or future channels are all drop-in.

Channels do not call the placement path themselves — they return a typed
`ConfirmationResponse` and the coordinator decides what to do next. This
keeps the safety story in one place (the coordinator), not spread across
every channel implementation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from trading_on_tcbs_api.stock_system_v2.schemas import PendingSignal

Decision = Literal["yes", "no", "timeout"]


class ConfirmationResponse(BaseModel):
    """Typed result of asking a human (or stand-in) about a `PendingSignal`."""

    model_config = ConfigDict(frozen=True)

    signal_id: str
    decision: Decision
    answered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    raw: str | None = Field(None, description="Raw operator input, when available (e.g. terminal keystroke).")
    reason: str | None = Field(None, description="Optional human-supplied note (rejection reason, etc.).")


@runtime_checkable
class ConfirmationChannel(Protocol):
    """Asynchronous human-confirmation channel.

    Implementations MUST be safe to call from an asyncio loop and MUST
    respect the `PendingSignal.expires_at` deadline — once the deadline
    passes, `request` should return `decision='timeout'` promptly rather
    than block forever.
    """

    async def request(self, pending: PendingSignal) -> ConfirmationResponse:
        """Prompt the operator about `pending`; return their decision.

        On expiry the channel returns `decision='timeout'` instead of
        raising. Exceptions are reserved for unrecoverable channel
        failures (e.g. Telegram auth lost) so the coordinator can surface
        them as `failed` rather than `expired`.
        """
        ...

    async def notify_outcome(
        self,
        pending: PendingSignal,
        outcome: str,
        details: str | None = None,
    ) -> None:
        """Inform the operator of the final disposition of `pending`.

        `outcome` is a short tag like `submitted`, `stale`, `rejected`,
        `expired`, `failed`. `details` is free-form, e.g. broker order
        id + filled price, or the failing revalidation rule.
        """
        ...

    async def replay_pending(self, pendings: list[PendingSignal]) -> None:
        """Re-display every still-open pending signal on startup.

        Called once by the coordinator after `PendingSignalStore.load_open()`
        so a restart never silently drops a signal awaiting a reply.
        Implementations may batch or rate-limit as appropriate.
        """
        ...
