"""Health-check schema (Phase 6).

`HealthStatus` is the one-shot snapshot an operator (or a Phase-7 tool
caller) reads to answer "is the autotrader OK to act?". Every check is
boolean + a free-form `note`; the top-level `ok` is the AND of all
checks.

Emitted by `core.health.health_check(...)`. Designed to be cheap so a
loop can call it every minute.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CheckStatus = Literal["ok", "warn", "fail", "unknown"]


class HealthCheck(BaseModel):
    """One named sub-check inside a `HealthStatus`."""

    model_config = ConfigDict(frozen=True)

    name: str
    status: CheckStatus
    note: str = ""


class HealthStatus(BaseModel):
    """Top-level health snapshot."""

    model_config = ConfigDict(frozen=True)

    captured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ok: bool = Field(..., description="True iff every BLOCK-severity check is ok or warn.")
    checks: list[HealthCheck] = Field(default_factory=list)
    last_error: str | None = Field(None, description="Most recent error from sync/order/data layer; None if quiet.")
    open_orders: int = Field(0, ge=0, description="Open orders surfaced by the tracker on this snapshot.")
    data_freshness_seconds: int | None = Field(
        None,
        description="Age of the most recent closed bar in seconds; None when no data is loaded yet.",
    )
    auth_valid: bool = Field(..., description="True iff `StockAuth.validate()` reports a working token.")
