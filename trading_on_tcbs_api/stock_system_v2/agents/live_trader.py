"""Live Trader Agent — gated stub (Phase 8).

The real live-trader implementation is intentionally **not** wired
yet. This module exists as a structured refusal: any attempt to use
it raises `NotImplementedError` with a pointer to the graduation
runbook. The Phase-5 + Phase-8 soaks must complete and the operator
must explicitly land the implementation alongside the production
hard caps.

When implementation does land, the contract:

  - Identical to `paper_trade_cycle` minus the `EXECUTION_DISABLED`
    bypass and minus safe-mode.
  - Hard caps from `Settings.risk` (and forthcoming Phase-8 keys for
    `max_daily_loss_vnd`, `max_trades_per_day`) are enforced *before*
    `submit_order`. A cap miss is a `reject`, not a warn — there is no
    operator override.
  - Kill-switch (`EXECUTION_DISABLED=true`) is consulted at the start
    of every cycle, every order. The same env flip stops the loop
    immediately.
"""

from __future__ import annotations


def live_trade_cycle(*_args: object, **_kwargs: object) -> None:
    """Refuse-by-default live-trade entry point.

    Until the Phase-8 paper-trader graduation review passes (see
    `docs/PHASE8_PAPER_TRADER_RUNBOOK.md`) and the per-cycle hard caps
    are wired, calling this raises `NotImplementedError`. The barrier
    is intentional — every other agent in this package has a tested
    recipe; this one does not, and the operator is the only legitimate
    path to flipping it on.
    """
    raise NotImplementedError(
        "Live Trader is gated on the Phase-8 paper-trader graduation review. "
        "See docs/PHASE8_PAPER_TRADER_RUNBOOK.md for the criteria. "
        "Do not bypass this stub — it is the safety contract."
    )
