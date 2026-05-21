"""Re-validation schemas (Phase 10).

When a human (HITL) or auto-mode coordinator confirms a queued signal, the
system MUST re-run the originating strategy against fresh market data
before placing the order — the operator may have been away from the desk
for an hour, and the signal that fired at 10:03 is not necessarily still
valid at 11:42. `RevalidationResult` is the typed outcome of that check.

A pass requires every entry in `checks` to be `passed=True`. A single
failure flips the overall `passed` to False and the coordinator returns
the signal to the scanner without placing an order.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RevalCheckName = Literal["signal_reemitted", "new_bar", "price_drift", "freshness"]


class RevalCheck(BaseModel):
    """One row of the re-validation report — a single rule + its verdict."""

    model_config = ConfigDict(frozen=True)

    name: RevalCheckName
    passed: bool
    detail: str = Field(..., description="Human-readable explanation of the verdict.")


class RevalidationResult(BaseModel):
    """Outcome of strict re-validation against fresh market data.

    A coordinator should only place the order when `passed` is True. When
    False, every failing rule is in `checks` with severity-bearing detail
    so the operator gets a clean post-mortem in their audit log.
    """

    model_config = ConfigDict(frozen=True)

    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    passed: bool
    checks: list[RevalCheck] = Field(default_factory=list)
    fresh_price: float | None = Field(None, description="Latest closed-bar price observed during revalidation, in VND.")
    fresh_bar_close_ts: datetime | None = Field(None, description="Close timestamp of the latest closed bar.")
    price_drift_pct: float | None = Field(None, description="abs(fresh - ref) / ref * 100, or None if not computable.")
    reason: str | None = Field(None, description="Short summary of the first failing check, or None on pass.")

    @property
    def failed_checks(self) -> list[RevalCheck]:
        """Subset of `checks` that did not pass — empty iff `passed` is True."""
        return [c for c in self.checks if not c.passed]
