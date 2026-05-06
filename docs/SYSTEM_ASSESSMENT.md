# Stock System V2 — Complete System Assessment

**Date:** 2026-05-06
**Scope:** Full assessment of `trading_on_tcbs_api/`, with deep focus on `stock_system_v2/`
**Lens:** AI-agent readiness — "Are these functions trustworthy enough that an autonomous agent can rely on them?"

---

## 1. Executive Summary

The codebase is a **structurally sound, operationally incomplete** algorithmic trading system. The V2 architecture (~6,000 LOC) demonstrates good intent: clean module separation, a centralised indicator engine, a clear strategy ABC, and a unified data provider. However, it is **not ready to be wrapped as agent-callable tools** in its current state.

The single most important insight from the audit is this: **the system currently behaves like a script, not a service.** It returns untyped dicts, swallows exceptions, mutates global config, depends on `print()` for visibility, mixes safe-mode mocks with stubs for live trading, and has zero automated tests. Each of these is a normal smell in a research codebase, but each is a hard blocker for an LLM agent that must reason about success/failure and chain calls.

The good news: there is **no architectural rewrite required**. Almost every weakness is a localised fix — schema definition, validation, error semantics, dependency injection, observability. The work is large in count, small in radius.

**Bottom line:** ~60% of the way to a usable backtest/scan engine, ~30% of the way to live trading, ~15% of the way to agent-tool readiness. Assessment below makes both numbers concrete.

---

## 2. Codebase Inventory

| Layer | LOC | Status | AI-Tool Readiness |
|---|---:|---|---|
| `auth/` | 192 | Working | Medium — JWT lifecycle is opaque to agent |
| `data_ingest/` | 274 | Working with smells | Low — schema undefined, two sources, synthetic candles |
| `core/indicator_engine.py` | 102 | Working | Medium — single-pass, but adds look-ahead columns |
| `core/market_scanner.py` | 144 | Working | Low — monolithic `scan()`, untyped returns |
| `core/backtester.py` | 272 | Working but unrigorous | Low — look-ahead bias, no costs, no walk-forward |
| `core/stock_api_client.py` | 442 | Partially working | Medium — best-typed module in the project |
| `core/auto_trader.py` | 135 | Half-finished | Low — orchestrator hardcodes strategies |
| `strategies/` | ~530 | Working | Medium — clear ABC, no parameter validation |
| `execution/order_manager.py` | 71 | **Stub for live** | None — real path raises NotImplemented |
| `execution/order_tracker.py` | 54 | Write-only | Low — never read back, no idempotency |
| `execution/trade_manager.py` | 67 | Working (paper) | Medium |
| `finance/account_manager.py` | 222 | Working | Medium — sync overwrites mock state |
| `finance/performance_analyzer.py` | 141 | Working | Medium |
| `scripts/` (operator CLIs) | ~1,800 | Mixed quality | N/A — these are runners, not tools |
| **Tests** | 0 lines real tests | **Missing** | Hard blocker |

Legacy systems (`stock_strategy/`, `futures_strategy/`, `simple_wow/`, `indicators/`, top-level `core/`, `ws_clients/`) are in maintenance mode and should remain frozen — agents should never touch them.

---

## 3. Architectural Assessment

### 3.1 What works

- **Layering is correct.** Auth → Data → Indicators → Strategies → Scanner → Execution → Finance is the right pipeline and each module roughly knows its job.
- **Indicator engine is single-pass.** Computing all indicators once via pandas-ta avoids the classic mistake of recomputing per-strategy. This is the single best design decision in the codebase.
- **Strategy ABC is clean.** `SignalStrategy.generate_signals(df) -> df` with a `signal` column of {1, 0, -1} is a contract an agent can reason about.
- **Data caching has the right shape.** Per-symbol CSV cache, freshness check, depth check — the bones are correct.
- **Safe-mode default for orders.** Order placement defaults to dry-run. This is the right paranoia.

### 3.2 What's tangled

- **Global config import.** ~8 modules `from stock_system_v2 import config`. This makes per-call configuration impossible and forces agents to mutate global state before instantiation.
- **MarketScanner instantiates its dependencies.** `DataProvider` and `IndicatorEngine` are constructed inside the scanner, not injected. Agents cannot swap data sources, mock for tests, or use a custom indicator set.
- **AutoTrader hardcodes strategies.** `auto_trader.py:29-39` constructs strategies inline — adding/removing one requires editing the orchestrator.
- **Two parallel execution paths.** `auto_trader.py` (async, uses AccountManager) and `main.py` (sync, uses TradeManager). They have not been reconciled. An agent picking the "wrong" entry point silently gets different behaviour.
- **`scan()` is monolithic.** 75 lines doing fetch + compute + signal + context-extraction. An agent cannot call "compute indicators only" or "evaluate one strategy on prepared data."

### 3.3 The contract problem (the central blocker)

Agents call tools and act on returned values. **The current return contracts are unfit for that.**

- `MarketScanner.scan()` → `List[Dict[str, Any]]` — keys vary by strategy.
- `Backtester.run()` → `Dict` — keys `trades_log`, `signal_details`, `fixed_hold_results` may or may not be present (`backtester.py:250-268`).
- `OrderManager.place_order()` → `Dict[str, Any]` — no schema for success vs error branches.
- `DataProvider.get_realtime_price()` → `Optional[float]` and silently mutates an internal cache.
- `validate_order()` → `{'valid': bool, 'reason': str}` — undocumented, no type.

An agent given these tools cannot type-check, cannot reliably detect failures, cannot distinguish "no signal today" from "data fetch failed," and cannot chain calls without try/except scaffolding for every shape it might get back.

---

## 4. Data Layer Assessment

The data layer is the **highest-leverage area to fix first**, because every downstream component (indicators, strategies, backtests, live signals) inherits its bugs.

### 4.1 Source mismatch — HIGH

History is fetched from **vnstock (KBS)**; live price is fetched from **TCBS API**. There is no reconciliation. Closing prices on the two sources can differ. An agent reasoning over a chart where today's bar comes from a different source than the rest is silently working with corrupted data.

### 4.2 Synthetic live candle — HIGH

In `data_provider.py:246-264`, on a trading day the live real-time price is appended as a fresh OHLCV row with `open=high=low=close=price` and **`volume=0`**. Every volume-based strategy (`VolumeBoomStrategy`, the volume-MA filters, the new top-3 momentum strategy) reads 0 for today and either misfires or under-fires. This is a silent correctness bug, not a stylistic issue.

### 4.3 Price-unit normalisation heuristic — MEDIUM

A hardcoded `if mean(close) < 500: multiply by 1000` (`data_provider.py:205-208`) attempts to fix unit mismatches. Stocks trading legitimately under 500 VND will be silently scaled 1000x. Order sizing, P&L, and signals will all be wrong on those names.

### 4.4 Cache "depth" check is heuristic — MEDIUM

Cache validity uses an IPO-tolerance heuristic (first cached date within 5 days of requested start). For recent IPOs the check passes with very few bars, then strategies run on insufficient warmup data without warning.

### 4.5 No schema validation — MEDIUM

DataFrame columns are normalised to lowercase but never validated. Strategies assume `close/open/high/low/volume` exist; if a fetch returns a missing column, strategies fail or NaN-out silently.

---

## 5. Strategy Framework Assessment

### 5.1 Strengths

- Strategy ABC provides a single, predictable contract (`signal` column ∈ {-1, 0, 1}).
- Most strategies parameterise their windows/thresholds.
- `CombinedStrategy` provides AND/OR aggregation primitives.

### 5.2 Issues

- **No parameter validation.** `RSIStrategy(period=0)` is constructible; `DipBuyStrategy(drop_pct=150)` produces a negative multiplier; nothing fails until backtest runtime.
- **No warmup enforcement.** Strategies emit signals on bar 1 even when the underlying SMA-50 is NaN. The backtester comment "We assume 'signal' column accounts for this" is a TODO disguised as documentation.
- **Aggregation precedence is contradictory.** `CombinedStrategy` claims sell priority but checks buy first then sell — for an agent assembling combined strategies dynamically, this is a behavioural landmine.
- **Context columns leak.** Strategies attach helper columns (`%_vol_increase`, `%_from_smaX`); the scanner tries to capture them by suffix matching, which is fragile and underspecified.
- **Hidden dependencies.** `RSIDivergenceStrategy` requires scipy; this is not declared anywhere a tooling layer could read.

---

## 6. Backtesting Rigor Assessment

This is the area where current results are most likely to mislead an agent (and the operator).

| Issue | Severity | Why it matters for agents |
|---|---|---|
| **Look-ahead bias.** Indicators (e.g. ROC for the cumulative-drop strategy) are computed across the whole frame before backtest, using future bars to label past ones | CRITICAL | Backtest returns are inflated; agent's strategy selection is biased toward overfit/leaky strategies |
| No transaction costs (TCBS commissions ~0.1–0.15%) | HIGH | Live PnL will trail backtest PnL by several %/year |
| No slippage / VN low-liquidity modelling | HIGH | Same |
| Position sizing = "all cash into one name" | MEDIUM | Risk metrics are not comparable between strategies |
| No walk-forward / out-of-sample split | MEDIUM | Cannot distinguish edge from curve fit |
| Survivor bias in symbol universe | MEDIUM | Edge over-stated |
| Two parallel sims (native vs fixed-hold) reported together | LOW | Conflicting numbers; agent doesn't know which to trust |

Until at minimum (1) the look-ahead bug is fixed and (2) transaction costs are modelled, **no agent should be allowed to make allocation decisions based on backtest output**.

---

## 7. Execution Safety Assessment

| Issue | Severity | Notes |
|---|---|---|
| Live trading is **not implemented**; real path is a stub (`order_manager.py:64`) | CRITICAL | Safe-mode is the only mode that runs |
| No pre-trade validation: `max_open_positions=5` is in config but never checked | HIGH | Risk-rule violations possible |
| No price-bound sanity check (could submit 999,999 VND order from a unit bug) | HIGH | |
| Position reconciliation overwrites mock with API state without diff | HIGH | State diverges silently |
| OrderTracker is write-only; never deduplicates or replays | MEDIUM | Crash mid-loop = orphaned positions |
| Two execution paths (`auto_trader` vs `main.py`/`TradeManager`) | MEDIUM | Behavioural ambiguity |

For an agent: today, the only safe operation in execution is the dry-run paper simulator. The live order path is unfinished, not just disabled.

---

## 8. Observability Assessment

- Logging is mostly `print()`. A structured logger exists but is barely wired in.
- No metrics: no counters for orders placed/rejected, scans run, data fetches, cache hits.
- OrderTracker only logs successful submissions — rejections are invisible.
- No request-IDs / correlation-IDs across the stack.

An agent that ran this system today and was asked "did anything go wrong in the last hour?" could not answer the question without re-running everything.

---

## 9. Testing Assessment

- **0 unit tests.** No `pytest` collection, no assertions.
- 6 "test_*.py" scripts under `scripts/` are integration probes that require live credentials — not tests in the CI sense.
- `verify_*.py` scripts are operator inspection tools — they print, they don't assert.
- No mocked TCBS client; nothing testable without network.

This is the largest single gap. Every other improvement compounds with tests; without them, every change is a coin flip.

---

## 10. Top Weaknesses (ranked by AI-agent integration impact)

| # | Weakness | Severity | Where |
|---|---|---|---|
| 1 | Untyped, unschematised return values throughout the public surface | CRITICAL | scanner, backtester, order_manager, data_provider |
| 2 | Look-ahead bias in indicators/backtester | CRITICAL | `indicator_engine.py:87-92` + `backtester.py:47` |
| 3 | Live order placement is a stub | CRITICAL | `order_manager.py:64` |
| 4 | Synthetic live candle with volume=0 corrupts volume strategies | HIGH | `data_provider.py:246-264` |
| 5 | Two data sources (KBS + TCBS) never reconciled | HIGH | `data_provider.py:190-200` |
| 6 | No transaction costs / slippage in backtester | HIGH | `backtester.py:85-179` |
| 7 | No parameter validation in strategies | HIGH | all strategy `__init__` |
| 8 | No pre-trade risk validation (position count, price bounds) | HIGH | `order_manager.py`, `auto_trader.py:105-130` |
| 9 | Tight coupling — scanner instantiates its dependencies | HIGH | `market_scanner.py:4-6,17-18` |
| 10 | No automated tests | HIGH | repo-wide |
| 11 | No structured logging / metrics / correlation IDs | MEDIUM | repo-wide |
| 12 | Two parallel execution entry points (auto_trader vs main.py) | MEDIUM | `auto_trader.py`, `main.py` |
| 13 | Global config import couples every module | MEDIUM | repo-wide |
| 14 | Hardcoded price-unit heuristic (`< 500 → ×1000`) | MEDIUM | `data_provider.py:205-208` |
| 15 | OrderTracker is write-only, no idempotency | MEDIUM | `execution/order_tracker.py` |

---

## 11. Top Strengths (worth preserving)

1. **Single-pass indicator engine.** Architecturally correct; should remain the canonical computation layer.
2. **`SignalStrategy` ABC.** Clean contract; the right base for an extensible strategy library.
3. **Per-symbol cached CSV with freshness/depth checks.** Right shape, just needs harder schema and fewer heuristics.
4. **Safe-mode default for orders.** The right paranoia setting; should remain the default forever.
5. **Layer separation.** Auth/Data/Indicators/Strategies/Scanner/Execution/Finance is the correct decomposition; no rewrite needed.
6. **`stock_api_client.py` typing.** The most agent-ready file in the project; it is the model for how every other public function should look.

---

## 12. Verdict for AI-Agent Integration

> **An AI agent on this codebase today could lose money quietly. It would not be able to detect that it had.**

The system needs three categories of work, in this order, before it is safe to expose to an agent:

1. **Correctness** — fix look-ahead bias, fix synthetic candle, reconcile data sources, add transaction costs. Without this, the agent's evidence base is corrupted.
2. **Contracts** — typed return values (Pydantic), typed exceptions, pre-trade validators, parameter validation. Without this, the agent cannot reason over results or recover from failure.
3. **Observability + Tests** — structured logs, metrics, automated test suite. Without this, neither agent nor human can verify anything.

A detailed, phased plan for executing this work is in `AI_INTEGRATION_PLAN.md`.
