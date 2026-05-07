"""Transaction cost model for V2 backtests (Phase 2).

The old backtester implicitly assumed zero costs — every fill happened at the
exact close price with no commission, no slippage, no minimum ticket. That
overstates strategy performance, sometimes by a lot. Real Vietnamese equities
costs from TCBS in 2024-2025:

- Commission: ~0.10–0.15% per side (paid on both buy and sell).
- Sales tax: 0.10% on sell-side only (gross proceeds).
- Slippage: a working assumption of 5–10 bps for liquid HoSE names; higher
  for thin small caps. Hard to model perfectly, so we expose it as a knob.
- Minimum ticket size: HoSE lot size = 100 shares; informal minimum
  notional is whatever the broker enforces.

Defaults below approximate TCBS retail equities. Override per-call when the
universe / venue differs.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TransactionCosts(BaseModel):
    """All-in cost configuration applied to backtest fills.

    `commission_bps` is paid on **each side** (buy and sell). `slippage_bps`
    is applied as an adverse price adjustment (buy fills above mid, sell
    fills below mid). `sell_tax_bps` is paid on the gross sell value only.
    `min_ticket_vnd` floors the per-trade notional — orders below this size
    are rejected by the simulator (returns 0 fills, no cash movement).
    """

    commission_bps: float = Field(0.0, ge=0.0, description="Per-side commission in basis points (TCBS retail default ~15 bps).")
    slippage_bps: float = Field(5.0, ge=0.0, description="Adverse price slippage in bps applied symmetrically per side.")
    sell_tax_bps: float = Field(10.0, ge=0.0, description="Sell-side capital-gains tax (Vietnam: 0.1% on gross proceeds).")
    min_ticket_vnd: float = Field(0.0, ge=0.0, description="Minimum trade notional in VND; smaller fills are rejected.")
    lot_size: int = Field(100, ge=1, description="Round shares down to this lot. HoSE board lot = 100.")

    def buy_fill_price(self, mid_price: float) -> float:
        """Effective price paid when buying at `mid_price` (slippage only)."""
        return mid_price * (1.0 + self.slippage_bps / 10_000.0)

    def sell_fill_price(self, mid_price: float) -> float:
        """Effective price received when selling at `mid_price` (slippage only)."""
        return mid_price * (1.0 - self.slippage_bps / 10_000.0)

    def buy_cost(self, fill_price: float, shares: int) -> float:
        """Total cash leaving the account on a buy fill (notional + commission)."""
        gross = fill_price * shares
        commission = gross * self.commission_bps / 10_000.0
        return gross + commission

    def sell_proceeds(self, fill_price: float, shares: int) -> float:
        """Net cash received on a sell fill after commission and sales tax."""
        gross = fill_price * shares
        commission = gross * self.commission_bps / 10_000.0
        tax = gross * self.sell_tax_bps / 10_000.0
        return gross - commission - tax

    def round_shares(self, shares: int) -> int:
        """Round share count down to a tradable multiple of `lot_size`."""
        if self.lot_size <= 1:
            return int(shares)
        return int(shares) // self.lot_size * self.lot_size


ZERO_COSTS = TransactionCosts(commission_bps=0.0, slippage_bps=0.0, sell_tax_bps=10.0, min_ticket_vnd=0.0, lot_size=100)
"""Cost-free model — preserves the legacy backtester's zero-cost behaviour."""

TCBS_DEFAULT_COSTS = TransactionCosts()
"""TCBS retail-equity defaults: 0 bps commission, 5 bps slippage, 10 bps sell tax."""
