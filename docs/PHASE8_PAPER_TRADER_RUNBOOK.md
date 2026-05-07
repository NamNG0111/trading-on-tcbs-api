# Phase 8 — Paper Trader Soak + Graduation Runbook

**Audience:** the operator (you) — this is calendar-gated, not
code-gated. The paper trader's full Python recipe is unit-tested on
fixtures (8 tests, all green); what's left is operating it against
live data for 4 weeks.

## Pre-flight (one time)

- [ ] `EXECUTION_DISABLED=true` is set in your shell.
- [ ] Phase-5 paper soak (the 2-week "watch the autotrader" run) has
      already completed. The paper-trader soak runs *on top of* that
      one — same environment, more agentic loop.
- [ ] `python -c "from trading_on_tcbs_api.stock_system_v2.agents import paper_trade_cycle; print('ok')"` prints `ok`.
- [ ] `decisions.jsonl` is being written to `EXPORT_DIR/decisions.jsonl`
      (verify by running the cycle once: `python -c "from trading_on_tcbs_api.stock_system_v2.tools.mcp_server import _bootstrap_context; from trading_on_tcbs_api.stock_system_v2.agents import paper_trade_cycle; _bootstrap_context(); r = paper_trade_cycle(); print(r.n_submitted, r.n_skipped)"`).

## Daily loop (4 weeks, ≥20 trading days)

Every trading day before the open:

- [ ] Run one paper-trade cycle. Record the `correlation_id` of the
      run (the autotrader logs it once at start).
- [ ] `tail -n 200 logs/<latest>.log | grep '"event":"reconcile.drift"'`
      returns nothing.
- [ ] `python -c "from trading_on_tcbs_api.stock_system_v2.execution.order_tracker import OrderTracker; print(len(OrderTracker().recover_open_orders()))"`
      prints `0` (no stuck PENDING rows).
- [ ] Spot-check one row in `decisions.jsonl` against the
      `RiskOpinion` rationale visible in the corresponding scanner
      report. They should agree — if the report says "approve" but
      the row says "skipped:reject", investigate.

## Mid-soak crash test (week 2)

- [ ] Mid-cycle, `pkill -9 -f "paper_trader"` (or the equivalent for
      your runtime).
- [ ] Restart. Confirm:
  - The autotrader's startup log line `auto_trader.init` carries a
    non-zero `recovered_open_orders`.
  - The next cycle skips the recovered ids (idempotent).

## Graduation review (end of soak)

All four must hold for ≥20 consecutive trading days:

- [ ] **Zero risk-rule violations.** No `decisions.jsonl` row has
      `decision="reject:*"` due to a risk-cap miss that the agent
      should have anticipated. (Validator-blocked submits are fine —
      that's the validator working.)
- [ ] **Audit trail matches reasoning.** Random-sample 5 rows per
      week. The scan signal that triggered each submit must be visible
      in the same correlation_id's scanner report; the risk opinion's
      verdict must match the action.
- [ ] **Performance roughly tracks backtest.** The paper book's
      compounded return over the soak is within ±50% of the
      walk-forward OOS Sharpe expectation for the strategies that
      actually fired. Not "matches" — "tracks." A wildly different
      live result is a bug, not a feature.
- [ ] **Drift events: zero.** No `PositionDriftError` raised during
      the entire soak.

If any criterion fails, the paper trader does not graduate. Diagnose,
fix, restart the soak.

## Promoting to the Live Trader

Only after graduation. The Live Trader Agent (`agents/live_trader.py`,
not built yet) inherits everything from the paper trader plus:

- Hard caps: max position size, max daily loss, max trades/day.
  Configured in `Settings`; refusing-to-trade behaviour rather than
  warnings.
- `EXECUTION_DISABLED` flipped off **per-session**, never persisted.
- Kill-switch wired to a single env flip.

Until that ships, treat the paper-trader graduation review as the
end-state of Phase 8 and move on to Phase 9.
