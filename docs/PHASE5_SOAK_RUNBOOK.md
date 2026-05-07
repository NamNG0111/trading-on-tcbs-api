# Phase 5 — Paper Soak + First Live Trade Runbook

**Audience:** the operator (you) — not the agent.
**Purpose:** the two open Phase-5 items (`2-week paper soak` and the
small live trade) are operational steps no automated test can run from
inside this repo. This runbook is the checklist you walk through to
close the Phase-5 DoD.

Code-side, every primitive Phase 5 listed is in place:

  - `OrderManager` — kill-switch + risk-token gate + safe-mode mock fill.
  - `OrderTracker` — append-only ledger, idempotent `register_pending`,
    `recover_open_orders()` after a crash.
  - `PreTradeValidator` — five rules + 60-second `RiskCheckResult` token.
  - `finance/reconciler.py` — `assert_no_drift` raises `PositionDriftError`
    instead of silently overwriting positions.
  - ADR-002 — `AutoTrader` is the only sanctioned execution path.

What's left is **operator confidence**: prove on real market data that
the recovery primitives actually catch the failures they claim to.

---

## Pre-flight (once)

- [ ] `EXECUTION_DISABLED=true` is set in your shell. Even with `safe_mode=True`,
      the kill-switch makes accidental live-mode runs reject every order.
- [ ] `~/.zshrc` (or equivalent) exports `EXECUTION_DISABLED=true` so
      every new terminal inherits it.
- [ ] `config/local_config.json` points `DATA_DIR` and `EXPORT_DIR` at
      Google Drive (so the soak's ledger is backed up off-machine).
- [ ] Latest TCBS credentials in `config/credentials.yaml`; OTP-renewed
      token in `config/token.json`.
- [ ] `python -c "from trading_on_tcbs_api.stock_system_v2.settings import Settings; s=Settings.load(); print(s.execution_disabled)"` prints `True`.

## 2-week paper soak

Goal: `AutoTrader` runs against live market data continuously, every
bar reconciles, no `PositionDriftError`s, no recovery surprises.

Day 1 setup:
  - [ ] Wipe `EXPORT_DIR/ledger.csv` so the soak starts from a clean
        ledger (or rotate it to `ledger.preSoak.csv`).
  - [ ] Start `python trading_on_tcbs_api/stock_system_v2/main.py` in a
        long-lived `tmux` / `screen` session. Safe-mode + kill-switch
        means no real orders, but the loop exercises the full path.
  - [ ] Tail `logs/` for any `[Account] Sync Error` or `PositionDrift`
        events.

Daily check (1 minute):
  - [ ] `tail -n 200 logs/<latest>.log | grep -iE "drift|reject|error"`
        returns nothing unexpected.
  - [ ] `python -c "from trading_on_tcbs_api.stock_system_v2.execution.order_tracker import OrderTracker; print(len(OrderTracker().recover_open_orders()))"`
        prints `0` (no stuck PENDING rows).
  - [ ] Mock account balance + positions match what the strategies
        signalled — eyeball the CSV.

Mid-soak crash test (day ~7):
  - [ ] In another terminal, run `pkill -9 -f "stock_system_v2/main.py"`.
  - [ ] Restart `main.py` in the same tmux pane.
  - [ ] Confirm log line `[Tracker] recovered N open orders` (manual
        observation — the autotrader logs this on startup once Phase 6
        wires structured logging).
  - [ ] `recover_open_orders()` returns the orders that were in flight
        at kill time.

Soak exit criteria (all must hold for ≥14 consecutive trading days):
  - [ ] Zero `PositionDriftError` raises.
  - [ ] Zero `DuplicateOrderError` raises (idempotency holds).
  - [ ] Zero stuck PENDING orders at end-of-day.
  - [ ] Reconciler warnings (last-close vs `refPrice`) under 25 bps for
        every prefetched symbol.

Mark this checklist done in `docs/AI_INTEGRATION_TODO.md` once the soak
clears.

## First small live trade

Goal: end-to-end live order with full audit trail. Cap the blast radius:
single name, single round lot, hard stop the moment anything looks off.

Pre-trade:
  - [ ] Soak above is green for 2 weeks.
  - [ ] Choose a single liquid symbol from the universe (e.g. `HPG`)
        and a notional under 10M VND.
  - [ ] Construct the order off-loop: open a Python REPL, instantiate
        `PreTradeValidator`, call `validate(req, account, market)`,
        confirm `result.passed and result.is_fresh()`.
  - [ ] In the same REPL, instantiate `OrderManager(safe_mode=False,
        execution_disabled=False, broker_client=client)` — both flags
        are off here, the **only** time in the soak you do this.
  - [ ] Verify the broker client account_no points at the right
        sub-account (normal, not margin) by reading
        `client.account_no`.

Submit:
  - [ ] `om.place_order(request=req, risk_check=token)`.
  - [ ] Confirm `OrderResponse.status == "ACCEPTED"` and
        `broker_order_id` is non-null.
  - [ ] In a second terminal, run `tail -n 5 EXPORT_DIR/ledger.csv` and
        confirm a PENDING row followed by an ACCEPTED row, both with
        the same `client_order_id`.

Fill confirmation:
  - [ ] Watch the broker UI / call `client.get_order_matches(order_id)`
        until the order fills.
  - [ ] Manually update the ledger to FILLED (Phase-6 will automate
        this with a fill-poller).
  - [ ] `assert_no_drift(account.positions, broker_positions)` — no
        drift after the fill propagates.

Close it:
  - [ ] Place the matching SELL via the same flow.
  - [ ] Confirm round-trip PnL matches expectation (cash delta minus
        TCBS commission + sell tax).

Done — tick the DoD line in `docs/AI_INTEGRATION_TODO.md` and re-set
`EXECUTION_DISABLED=true` in your shell.

## What this runbook does NOT cover

- **Multi-day open positions** — the autotrader's overnight behaviour
  (gap-up risk, re-validation on the next session) is Phase 6+.
- **Margin / shorting** — out of scope; default sub-account is the
  cash account.
- **Real-time fill polling** — Phase 6 wires it as a structured event
  stream; until then, manual UI confirmation is the contract.
