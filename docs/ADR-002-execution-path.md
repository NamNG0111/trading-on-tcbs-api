# ADR-002 — Canonical execution path

**Status:** Accepted (2026-05-08)
**Context:** Phase 5 — Execution Safety
**Companion:** `docs/AI_INTEGRATION_PLAN.md`

## Problem

V2 has two execution entry points:

1. **`AutoTrader`** (`core/auto_trader.py`) — async, scan → validate →
   submit, integrates `MarketScanner` + `OrderManager` + `AccountManager`
   + `OrderTracker`. Designed as the agent-facing orchestrator.

2. **`main.py` + `TradeManager`** (`execution/trade_manager.py`) — sync,
   loop calling `scanner.scan` and `trade_manager.execute` per signal.
   Predates the Phase-3 DI refactor.

Two execution paths means two places where a Phase-5 safety bug can hide:
the validator gate, the kill-switch, the tracker idempotency, the
position reconciliation. Diverging code paths around real money is the
exact "bug factory" the plan calls out.

## Decision

**`AutoTrader` is the canonical execution path.** `TradeManager` is
deprecated. New work targets `AutoTrader` exclusively.

`main.py` already composes `AutoTrader` (Phase-3 refactor). The legacy
`TradeManager` import in `main.py` is removed; the file becomes a pure
composition root for `AutoTrader`. `execution/trade_manager.py` remains
on disk for one release as a deprecation marker (raises
`DeprecationWarning` on import) and is excluded from mypy / lint.

## Consequences

- **Single safety surface.** Every order flows through `OrderManager`
  (which carries the kill-switch, validator gate, and idempotent
  tracker). There is no second path that can silently bypass these.
- **Async by default.** `AutoTrader.run` is `async`. Sync callers must
  wrap in `asyncio.run`; that's a one-liner in `main.py` already.
- **Operator-facing scripts** (`scripts/scan_market.py`, etc.) keep
  their existing wiring — they don't place orders, so the deprecation
  is invisible to them.
- **No live trading until Phase-5 soak completes.** The live path in
  `OrderManager` is wired but only reachable when `safe_mode=False`,
  `EXECUTION_DISABLED=false`, a fresh `RiskCheckResult` is supplied,
  and a `broker_client` is injected. The default composition in
  `main.py` keeps `safe_mode=True`.

## Migration notes

`execution/trade_manager.py` is the only legacy importer; it lives on
under the warning until Phase 6 lands the structured logging migration
that would otherwise have to keep `print` shims for the deprecated
class. Removing it then is a clean delete with no downstream churn.

## Alternatives considered

- **Keep both paths.** Rejected — duplicates every Phase-5 safety
  primitive and creates ambiguous "which one is real" failures.
- **Reverse the choice (TradeManager canonical).** Rejected — the agent
  story (Phase 7+) wants async tools so cancellation, parallel scans,
  and timeouts compose naturally. `TradeManager` would have to be
  rewritten anyway.
