"""Pre-trade validator (Phase 5).

Every order must pass through `PreTradeValidator.validate(req, ctx)`
before `OrderManager.place_order` will accept it. The validator returns
a `RiskCheckResult` whose `request_hash` binds the token to the exact
fields of the `OrderRequest` — an agent that mutates the request after
validation gets a fresh hash and the token rejects.

Five rules ship today (all configurable):

  1. **Position-count limit** — refuse new BUYs once the open-position
     count meets `max_open_positions`. Sells of existing positions are
     always allowed.
  2. **Price-band check** — limit price must be within `price_band_pct`
     of the most recent closed-bar price. Catches fat-finger inputs and
     stale-quote orders.
  3. **Notional limit** — `price * volume` must not exceed
     `max_notional_vnd`. Hard cap regardless of cash.
  4. **Available cash** — buys must be covered by `cash + buying_power`
     (mock or real, via `AccountSnapshot`).
  5. **Tradability** — symbol must be in the configured universe and
     volume must be a multiple of the venue lot size.

Rules emit `RiskCheckFinding` rows with severity `BLOCK` (fatal),
`WARN` (note in the audit trail, does not fail the check), or `INFO`
(observability only). `RiskCheckResult.passed` is False iff any
finding carries severity `BLOCK`.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from trading_on_tcbs_api.stock_system_v2.schemas import (
    AccountSnapshot,
    MarketContext,
    OrderRequest,
    RiskCheckFinding,
    RiskCheckResult,
)


class DailyTradeStats(BaseModel):
    """Per-day execution stats supplied by the caller for hard-cap checks.

    Phase-10 adds three caps that depend on cross-order state the validator
    cannot infer alone (a single `OrderRequest` doesn't know how many
    orders have already fired today). The HITL coordinator builds this
    object once per signal — typically from `OrderTracker.get_history()`
    and `AccountManager` — and hands it to the validator.

    All counts/values are "as of right now", before the new order would
    be placed. The validator does the arithmetic to project post-trade
    state itself.
    """

    model_config = ConfigDict(frozen=True)

    trades_today: int = Field(0, ge=0, description="Orders the system has already submitted today.")
    realized_pnl_today_vnd: float = Field(0.0, description="Realized PnL today, in VND (negative = loss).")


def request_hash(req: OrderRequest) -> str:
    """Stable SHA-256 over the order's binding fields.

    Re-validation must produce the same hash for the same intent —
    `client_order_id` is included so the agent can't reuse a token for
    a different idempotency key. Tokens are bound to the exact
    (symbol, side, price, volume, order_type, client_order_id) tuple.
    """
    payload = {
        "symbol": req.symbol,
        "side": req.side,
        "price": req.price,
        "volume": req.volume,
        "order_type": req.order_type,
        "client_order_id": req.client_order_id,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class ValidatorConfig:
    """Tunable thresholds for the pre-trade validator."""

    max_open_positions: int = 5
    price_band_pct: float = 0.07  # ±7% of last close
    max_notional_vnd: float = 200_000_000.0  # 200M VND default cap
    lot_size: int = 100
    # — Phase-10 daily/per-position hard caps. Sentinel 0 disables. —
    max_position_size_vnd: float = 0.0
    max_daily_loss_vnd: float = 0.0
    max_trades_per_day: int = 0


class PreTradeValidator:
    """Apply every pre-trade rule and emit a `RiskCheckResult` token.

    Args:
        config: Tunable thresholds. Defaults are conservative.
        universe: Allowed symbols. None disables the membership check
            (the universe is then implicit "anything tradable").

    Example:
        >>> v = PreTradeValidator(universe=("HPG", "TCB"))
        >>> result = v.validate(req, account=acct, market=ctx)
        >>> if result.passed and result.is_fresh():
        ...     order_manager.place_order(request=req, risk_check=result)
    """

    def __init__(
        self,
        config: ValidatorConfig | None = None,
        *,
        universe: tuple[str, ...] | None = None,
    ) -> None:
        self.config = config or ValidatorConfig()
        self.universe = tuple(universe) if universe is not None else None

    def validate(
        self,
        req: OrderRequest,
        *,
        account: AccountSnapshot,
        market: MarketContext,
        daily_stats: "DailyTradeStats | None" = None,
    ) -> RiskCheckResult:
        """Run every rule for `req` against `account` + `market` state.

        Args:
            req: The order under consideration.
            account: Current account snapshot (cash, positions).
            market: Snapshot of last-close prices + lot size.

        Returns:
            `RiskCheckResult` carrying every finding. `passed=False`
            when any rule emits a `BLOCK` finding.
        """
        findings: list[RiskCheckFinding] = []

        # 1. Tradability — universe + lot size.
        if self.universe is not None and req.symbol not in self.universe:
            findings.append(RiskCheckFinding(
                rule="universe_membership",
                severity="BLOCK",
                message=f"Symbol {req.symbol} is not in the configured universe.",
                details={"symbol": req.symbol, "universe_size": len(self.universe)},
            ))
        lot = market.lot_size or self.config.lot_size
        if lot > 1 and req.volume % lot != 0:
            findings.append(RiskCheckFinding(
                rule="lot_size",
                severity="BLOCK",
                message=f"Volume {req.volume} is not a multiple of lot size {lot}.",
                details={"volume": req.volume, "lot_size": lot},
            ))

        # 2. Price band — limit price within ±X% of last close.
        last_close = market.last_close_prices.get(req.symbol)
        if last_close is not None and last_close > 0:
            deviation = abs(req.price - last_close) / last_close
            if deviation > self.config.price_band_pct:
                findings.append(RiskCheckFinding(
                    rule="price_band",
                    severity="BLOCK",
                    message=(
                        f"Limit price {req.price:,.0f} is "
                        f"{deviation*100:.2f}% away from last close {last_close:,.0f}; "
                        f"max allowed is {self.config.price_band_pct*100:.2f}%."
                    ),
                    details={"last_close": last_close, "deviation_pct": deviation * 100},
                ))
        else:
            findings.append(RiskCheckFinding(
                rule="price_band",
                severity="WARN",
                message=f"No last-close mark available for {req.symbol}; price-band check skipped.",
                details={"symbol": req.symbol},
            ))

        # 3. Notional limit.
        notional = req.price * req.volume
        if notional > self.config.max_notional_vnd:
            findings.append(RiskCheckFinding(
                rule="notional_limit",
                severity="BLOCK",
                message=(
                    f"Notional {notional:,.0f} VND exceeds cap "
                    f"{self.config.max_notional_vnd:,.0f} VND."
                ),
                details={"notional_vnd": notional, "cap_vnd": self.config.max_notional_vnd},
            ))

        # 4. Available cash (buys only) / position-cover (sells only).
        if req.side == "BUY":
            free_cash = account.cash - account.locked_cash
            available = max(free_cash, account.buying_power)
            if notional > available:
                findings.append(RiskCheckFinding(
                    rule="available_cash",
                    severity="BLOCK",
                    message=(
                        f"BUY notional {notional:,.0f} exceeds available "
                        f"{available:,.0f} (cash={free_cash:,.0f}, "
                        f"buying_power={account.buying_power:,.0f})."
                    ),
                    details={"notional_vnd": notional, "available_vnd": available},
                ))
        else:  # SELL
            held = next(
                (p.quantity for p in account.positions if p.symbol == req.symbol),
                0,
            )
            if held < req.volume:
                findings.append(RiskCheckFinding(
                    rule="position_cover",
                    severity="BLOCK",
                    message=f"SELL {req.volume} {req.symbol} but holding only {held}.",
                    details={"held": held, "requested": req.volume},
                ))

        # 5. Position-count limit (BUY only; opening a new name).
        if req.side == "BUY":
            already_held = any(p.symbol == req.symbol for p in account.positions)
            if not already_held and len(account.positions) >= self.config.max_open_positions:
                findings.append(RiskCheckFinding(
                    rule="max_open_positions",
                    severity="BLOCK",
                    message=(
                        f"Would open position #{len(account.positions)+1}; "
                        f"limit is {self.config.max_open_positions}."
                    ),
                    details={
                        "open_positions": len(account.positions),
                        "limit": self.config.max_open_positions,
                    },
                ))

        # 6. Per-position size cap (BUY only; SELL reduces position).
        if req.side == "BUY" and self.config.max_position_size_vnd > 0:
            existing_value = sum(
                p.quantity * p.avg_cost
                for p in account.positions
                if p.symbol == req.symbol
            )
            projected_value = existing_value + notional
            if projected_value > self.config.max_position_size_vnd:
                findings.append(RiskCheckFinding(
                    rule="max_position_size",
                    severity="BLOCK",
                    message=(
                        f"Post-trade position value {projected_value:,.0f} VND "
                        f"would exceed cap {self.config.max_position_size_vnd:,.0f} VND."
                    ),
                    details={
                        "existing_value_vnd": existing_value,
                        "projected_value_vnd": projected_value,
                        "cap_vnd": self.config.max_position_size_vnd,
                    },
                ))

        # 7. Daily trade-count cap.
        if daily_stats is not None and self.config.max_trades_per_day > 0:
            if daily_stats.trades_today >= self.config.max_trades_per_day:
                findings.append(RiskCheckFinding(
                    rule="max_trades_per_day",
                    severity="BLOCK",
                    message=(
                        f"Already submitted {daily_stats.trades_today} orders today; "
                        f"daily cap is {self.config.max_trades_per_day}."
                    ),
                    details={
                        "trades_today": daily_stats.trades_today,
                        "cap": self.config.max_trades_per_day,
                    },
                ))

        # 8. Daily realized-loss cap. The cap is a POSITIVE VND amount;
        #    block when realized PnL today is more negative than -cap.
        if daily_stats is not None and self.config.max_daily_loss_vnd > 0:
            loss_floor = -abs(self.config.max_daily_loss_vnd)
            if daily_stats.realized_pnl_today_vnd <= loss_floor:
                findings.append(RiskCheckFinding(
                    rule="max_daily_loss",
                    severity="BLOCK",
                    message=(
                        f"Realized PnL today {daily_stats.realized_pnl_today_vnd:,.0f} VND "
                        f"has reached the daily loss floor "
                        f"({loss_floor:,.0f} VND); no further trades allowed."
                    ),
                    details={
                        "realized_pnl_today_vnd": daily_stats.realized_pnl_today_vnd,
                        "loss_floor_vnd": loss_floor,
                    },
                ))

        passed = not any(f.severity == "BLOCK" for f in findings)
        return RiskCheckResult(
            request_hash=request_hash(req),
            passed=passed,
            findings=findings,
        )
