"""RiskCheckResult + MarketContext schemas (Phase 3).

`RiskCheckResult` is the typed token Phase-5 will gate every order on:
the agent calls `validate_order(req) -> RiskCheckResult`, and `submit_order`
refuses unless it sees a fresh, unexpired token whose `request_hash`
matches the order being placed. The 60-second TTL is enforced server-side.

`MarketContext` is the read-only "what's the market doing right now" object
the scanner and risk validator can both reference — last-close prices, vol
estimates, board lots — so they don't each go re-fetch the same data.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CheckSeverity = Literal["INFO", "WARN", "BLOCK"]
DEFAULT_TTL_SECONDS = 60


class RiskCheckFinding(BaseModel):
    """One result row from a single validator rule."""

    model_config = ConfigDict(frozen=True)

    rule: str = Field(..., description="Stable rule id, e.g. 'price_band'.")
    severity: CheckSeverity
    message: str
    details: dict[str, object] = Field(default_factory=dict)


class RiskCheckResult(BaseModel):
    """Outcome of running every pre-trade rule for a candidate order.

    The token (`check_id` + `request_hash`) is what the order-submit path
    must see — agents cannot synthesize one. `passed` is a hard `all` over
    the findings: any BLOCK severity flips it to False.
    """

    model_config = ConfigDict(frozen=True)

    check_id: str = Field(default_factory=lambda: f"chk_{uuid.uuid4().hex}")
    issued_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ttl_seconds: int = Field(DEFAULT_TTL_SECONDS, gt=0, le=300)
    request_hash: str = Field(..., description="Stable hash of the OrderRequest fields this check applied to.")
    passed: bool
    findings: list[RiskCheckFinding] = Field(default_factory=list)

    @property
    def expires_at(self) -> datetime:
        return self.issued_at + timedelta(seconds=self.ttl_seconds)

    def is_fresh(self, now: datetime | None = None) -> bool:
        """True iff the token has not expired."""
        ref = now or datetime.now(timezone.utc)
        return ref < self.expires_at

    @property
    def violations(self) -> list[str]:
        """List of rule ids with severity BLOCK — empty iff `passed` is True."""
        return [f.rule for f in self.findings if f.severity == "BLOCK"]


class MarketContext(BaseModel):
    """Snapshot of market state the scanner / validator can both consume."""

    model_config = ConfigDict(frozen=True)

    captured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_close_prices: dict[str, float] = Field(default_factory=dict, description="Symbol → most recent closed-bar price.")
    live_prices: dict[str, float] = Field(default_factory=dict, description="Symbol → live-tape mark; may be stale or empty outside trading hours.")
    realised_vol_pct: dict[str, float] = Field(default_factory=dict, description="Symbol → annualised realised vol (decimal).")
    lot_size: int = Field(100, ge=1, description="Default board lot for the venue.")
