# ADR-001 — Single Source of Truth for OHLCV

**Status:** **Accepted — Option B (both sources, with Reconciler).**
**Date:** 2026-05-06
**Phase:** 1 — Data Correctness
**Supersedes:** —

**Operator decision (2026-05-06):** Option B chosen. Rationale: TCBS is the more
trusted source for current/reference pricing on the Vietnamese market;
vnstock's upstream changes frequently (source rotations, schema breaks), so
the cross-check is load-bearing rather than belt-and-braces.

---

## Context

The V2 data layer currently reads from two independent sources without
reconciliation:

1. **vnstock (KBS)** — historical daily OHLCV, written to per-symbol CSV cache.
2. **TCBS `tickerCommons`** — live last-print, merged onto the latest bar.

The merge fabricates a synthetic candle for today (`open=high=low=close=live_price`,
`volume=0`) which contaminates indicator math (rolling means, RSI, MACD…) and
silently misfires volume strategies on every live scan. See `AI_INTEGRATION_PLAN.md`
§3 item 3 ("Kill the synthetic-candle bug").

Because the two sources are never compared, a divergence between them can
silently flip a signal — an unacceptable property for a tool an agent will
trust.

The orthogonal correctness fix (mark the partial bar, drop it from indicators)
has already landed in this phase. This ADR addresses the remaining structural
question: do we keep both sources, or collapse to one?

## Options

### Option A — vnstock only (recommended)

Drop the TCBS realtime merge. The scanner emits signals on the **last closed
bar** only; live price is informational metadata, not an OHLC value. Operators
who want to act intra-day call `DataProvider.get_realtime_price(symbol)`
explicitly to verify the current tape before placing an order.

**Pros**
- One source ⇒ no reconciliation required, no divergence by construction.
- Removes ~60 lines of partial-bar handling and the `prefetch_realtime_prices`
  batch loop.
- Aligns with the Phase 7 tool design (`get_quote` is a separate tool from
  `get_history`).

**Cons**
- Intra-day signal regeneration based on live price is no longer possible
  through `get_historical_data`. Strategies that historically fired
  intra-day on synthetic OHLC will have to be rewritten to consume the live
  price explicitly, or wait for the close.
- Pre-trade price-bound checks (Phase 5) need an explicit live quote — they
  cannot lean on the merged DataFrame.

### Option B — Both, with a Reconciler

Retain both sources. Add a `Reconciler` that compares the last N closed-bar
closes between vnstock and TCBS and emits a warning when the spread exceeds
a configurable threshold (e.g. 25 bps).

**Pros**
- No behavioural change to existing scanners and strategies.
- Cross-source check is itself useful diagnostic signal (one provider had a
  corp-action that hadn't propagated yet, etc.).

**Cons**
- Two code paths, two sets of failure modes, duplicated retry/auth logic.
- Reconciliation policy (warn? raise? fall back?) adds yet another decision
  point an agent must reason about.
- Live-price merge stays in the historical fetch path — the partial-bar
  scaffolding from this phase is permanent rather than transitional.

## Decision

**Accepted: Option B — both sources, with Reconciler.**

vnstock is treated as the historical truth (TCBS exposes no working OpenAPI
history endpoint), TCBS is treated as the live/reference truth, and a
`PriceReconciler` (`data_ingest/reconciler.py`) compares vnstock's last closed
close against TCBS `refPrice` on every fetch. Phase 1 lands the reconciler
with `severity='warn'`; Phase 5 will escalate it to `severity='raise'` for
order-placement code paths.

### TCBS history limitation

TCBS does not expose a working historical-bars endpoint via OpenAPI
(see `scripts/probe_history.py`). The runtime check is therefore necessarily
single-point — last closed close vs `refPrice` — rather than the "last-N
closes" originally sketched in `AI_INTEGRATION_PLAN.md`. The reconciler
ships with a `check_series` method so a future N-point implementation
(alternate provider, scraped close history, etc.) can drop in without
touching the call sites.

## Consequences

- The synthetic-candle scaffolding (`is_partial=True`, `volume=NaN`) becomes
  the permanent shape of the merged frame, not a transitional one.
- `DataProvider.__init__` accepts a `reconciler` parameter so tests and
  execution-critical callers can swap in a stricter (`raise`) reconciler.
- Reconciliation history is retained on the reconciler instance (the
  Phase-6 audit trail will lift this into structured logs).
- Any sustained reconciliation failure for a symbol must be investigated
  before that symbol is traded — divergence is the most likely tell of a
  corp-action that has propagated to one provider but not the other.

### Default threshold

`DEFAULT_THRESHOLD_BPS = 25.0` (0.25%). Tight enough to surface real
mismatches, loose enough to absorb tick rounding. Override on a per-symbol
or per-call basis when needed; revisit during Phase 6.
