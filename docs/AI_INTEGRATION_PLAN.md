# AI-Agent Integration Plan — Stock System V2

**Date:** 2026-05-06
**Companion to:** `SYSTEM_ASSESSMENT.md`
**North star:** Every public function in this repo becomes a tool that an AI agent can call with confidence. The codebase is the **trusted toolbelt** — the agent is the strategy.

---

## 0. Framing

The user's framing is correct and worth restating: **you are not building a trading bot, you are building a fleet of trustworthy tools that an agent will eventually orchestrate.** Everything that follows — schemas, validation, observability, MCP wrapping — is in service of that single inversion.

This reframing implies three principles for every change:

1. **Honesty over heroics.** A function that returns `None` on failure is dishonest to an agent. Raise typed exceptions or return discriminated-union responses. Never swallow.
2. **Determinism over magic.** Heuristics (the `<500 → ×1000` price scaler, the 5-day IPO tolerance) are unsuitable for tools an agent must trust. Replace with explicit, queryable contracts.
3. **One way to do it.** Two execution entry points, two simulation paths, two data sources without reconciliation — all are bug factories. Pick one and document the other as deprecated.

---

## 1. Phase Map (at a glance)

| Phase | Theme | Duration estimate | Outcome |
|---|---|---|---|
| **0** | Test harness foundation | 1 week | Can run `pytest`; mocked TCBS client; CI green |
| **1** | Data correctness | 1–2 weeks | Trustworthy OHLCV; one source-of-truth schema |
| **2** | Backtesting rigor | 1–2 weeks | No look-ahead; costs modelled; walk-forward built |
| **3** | Public-API contracts | 2 weeks | Pydantic models everywhere; typed errors; no `Dict[str, Any]` |
| **4** | Strategy framework v2 | 1 week | Validated params; warmup enforced; metadata exposed |
| **5** | Execution safety | 2 weeks | Real order path live; pre-trade validators; idempotent tracker |
| **6** | Observability | 1 week | Structured logs; metrics; correlation IDs; audit trail |
| **7** | Tool layer (MCP/HTTP) | 1–2 weeks | Every capability is an agent-callable tool with schema |
| **8** | Agent integration | 2–3 weeks | First agent loops on top of the toolbelt |
| **9** | Continuous learning | ongoing | Agent's decisions feed back into research |

Total to agent readiness: ~10–13 weeks of focused work. Phases 0–6 are repo cleanup; **Phase 7 is the inflection point.**

---

## 2. Phase 0 — Test Harness Foundation (Week 1)

**Why first.** Every subsequent phase risks regressions. Without a test harness you cannot verify anything you change.

**Deliverables:**
- `tests/` directory with `pytest.ini`, `conftest.py` (fixtures for fake DataFrames, mocked TCBS responses, sample OHLCV CSVs in `tests/fixtures/`).
- A `FakeStockApiClient` and `FakeDataProvider` so tests run with zero network.
- One test per existing strategy that locks in current signal output on a fixed fixture (regression seal).
- One test that runs the backtester end-to-end on a tiny synthetic series and asserts a known outcome.
- GitHub Actions (or Makefile target) running `pytest` + `ruff check` + `mypy`.

**Definition of done:** `make test` is green from a clean clone with no credentials.

---

## 3. Phase 1 — Data Correctness (Weeks 2–3)

The data layer is the input substrate for every other layer. Fix it first.

**Deliverables:**
1. **Define `OHLCVFrame` schema** (Pydantic / pandera) with required columns, dtypes, monotonic time index, and validation called at every fetch boundary.
2. **Resolve the two-source problem.** Choose one of:
   - **Option A (recommended):** vnstock for everything; drop TCBS realtime entirely. Simpler, more consistent.
   - **Option B:** Keep both, but add a `Reconciler` that compares last-N closes between sources and surfaces a warning when they disagree by > X bps.
3. **Kill the synthetic-candle bug.** Today's bar must be marked `is_partial=True` and never have `volume=0` written into a column volume strategies read. Either: (a) exclude today from indicator computation entirely and surface live price as a separate field; or (b) carry `volume_so_far` from the live tape.
4. **Replace the `<500 ×1000` heuristic** with an explicit `price_unit` column or a per-symbol metadata table loaded once.
5. **Strengthen cache validation.** Replace IPO heuristic with explicit `min_bars_required` parameter. If cache has fewer bars than required, treat as miss.
6. **Property-based tests** (hypothesis): no NaN in close after fetch; index strictly monotonic; volume ≥ 0; price > 0.

**Definition of done:** A backtest run on the same symbol two days in a row produces identical historical bars. Volume strategies do not silently mis-fire on the live scan day.

---

## 4. Phase 2 — Backtesting Rigor (Weeks 3–4, can overlap with Phase 1)

**Deliverables:**
1. **Eliminate look-ahead bias.** Indicators must only use bars `[0, t-1]` when emitting the signal for bar `t`. Audit every indicator in `indicator_engine.py`. Add a `assert_no_lookahead(df)` test utility that shifts inputs and confirms signals also shift.
2. **Transaction costs model.** Configurable `commission_bps`, `slippage_bps`, `min_ticket_vnd`. Default to TCBS's real costs.
3. **Realistic position sizing.** Replace "all cash → one name" with `PositionSizer` interface (fixed-fraction, equal-weight, volatility-targeted). Inject into backtester.
4. **Walk-forward harness.** `WalkForwardBacktester` runs N rolling windows of (train, test), reports out-of-sample stats only. Mandatory for any backtest the agent will use as evidence.
5. **Survivor-bias note.** Until we have a delisted-symbols list, every backtest report includes a "survivor bias: not corrected" disclaimer field. An agent reading this knows to discount.
6. **Single result schema** (`BacktestResult` Pydantic model): merge native and fixed-hold paths into one object with explicit `holding_strategy: "native" | "fixed"`.

**Definition of done:** Re-running the existing top-3 momentum backtest with costs and walk-forward enabled produces a more conservative number than today's report. Document the delta.

---

## 5. Phase 3 — Public-API Contracts (Weeks 4–5)

This is the phase that converts the codebase from "scripts" into "tools."

**Deliverables:**
1. **Pydantic models** for every cross-module return type:
   - `OHLCVFrame`, `Signal`, `ScanResult`, `BacktestResult`, `OrderRequest`, `OrderResponse`, `Position`, `AccountSnapshot`, `RiskCheckResult`, `MarketContext`.
2. **Typed exceptions** in a `exceptions.py` module:
   - `DataFetchError`, `StaleCacheError`, `InsufficientHistoryError`, `InvalidParameterError`, `OrderRejectedError`, `RiskLimitViolatedError`, `AuthExpiredError`.
3. **Replace catch-all blocks.** Every `except Exception: return None` becomes either (a) a narrow catch + log + raise typed, or (b) removed entirely.
4. **Inject dependencies.** `MarketScanner(data_provider, indicator_engine, strategies)` — no internal instantiation. Same for `AutoTrader`. Construct at the entrypoint, pass everything in.
5. **Kill the global `config` import.** Pass a `Settings` object (Pydantic BaseSettings) explicitly to constructors. Allow per-call overrides.
6. **Document every public method** with: purpose, params, returns, raises, example. This documentation will be lifted directly into agent tool descriptions in Phase 7.

**Definition of done:** `mypy --strict` passes on the V2 package. No `Dict[str, Any]` outside internal helpers. Every public function has a docstring an agent could read.

---

## 6. Phase 4 — Strategy Framework v2 (Week 6)

**Deliverables:**
1. **Pydantic-validated strategy params** via `StrategyParams` base class. Bad params raise at construction, not at compute.
2. **Warmup enforcement.** Each strategy declares `min_bars_required`; base class refuses to emit signals before that bar.
3. **Strategy metadata.** Each strategy exposes `.describe() -> StrategyDescription` with name, description, params schema, indicators used, signal semantics. Used for both UI and agent tool listings.
4. **Standardised context columns.** Strategies attach context via a typed `signal_context: dict[str, Any]` column instead of named columns; scanner reads via the typed accessor.
5. **CombinedStrategy precedence rules** explicit and tested. Specify and document: simultaneous buy+sell → sell wins; AND modes are unanimous; OR modes are any-true.
6. **Strategy registry.** `STRATEGIES: dict[str, type[SignalStrategy]]` so an agent can list, instantiate by name, and inspect schema without import gymnastics.
7. **Strategy Contribution Checklist.** A single document (`strategies/CONTRIBUTING.md`) that any new strategy — added by you, a teammate, or a Phase 9 agent — must satisfy before merge. Mechanical, enforceable in CI:

   **Code requirements:**
   - [ ] Subclasses `SignalStrategy`; lives in `strategies/<name>_strategy.py`.
   - [ ] Declares a `Params(StrategyParams)` Pydantic model with field types, ranges (`Field(ge=…, le=…)`), and one-line descriptions per field.
   - [ ] Sets `min_bars_required: int` as a class attribute, justified by the longest lookback used.
   - [ ] Declares `indicators_used: list[str]` matching keys from `IndicatorEngine`. Adding a new indicator? Extend the engine first, in a separate PR.
   - [ ] Implements `.describe() -> StrategyDescription` — name, one-paragraph rationale, signal semantics, expected market regime, known failure modes.
   - [ ] Registered in `STRATEGIES` registry.
   - [ ] No `print()`; uses module logger.
   - [ ] No catch-all `except Exception`; raises typed errors from `exceptions.py`.

   **Required tests** (under `tests/strategies/test_<name>.py`):
   - [ ] **Regression fixture test** — runs the strategy on a checked-in OHLCV CSV and asserts the resulting signal series matches a checked-in expected output. Locks behaviour against accidental change.
   - [ ] **No-lookahead test** — uses the shared `assert_no_lookahead(strategy, df)` utility from Phase 2: shifts inputs by k bars and confirms signals shift by the same k.
   - [ ] **Warmup test** — asserts no non-zero signal is emitted before `min_bars_required`.
   - [ ] **Param-validation test** — instantiating with out-of-range params raises `InvalidParameterError`.
   - [ ] **Determinism test** — same input twice produces identical output (no hidden randomness or time-of-day dependence).

   **Performance smoke gates** (run by `make strategy-smoke <name>` and in CI):
   - [ ] Walk-forward backtest on the standard universe (≥5 symbols, ≥3 years, with costs) completes without error.
   - [ ] Out-of-sample Sharpe is reported, even if negative — strategies are allowed to be bad, but their badness must be visible.
   - [ ] Trade count is within sane bounds (configurable; default: between 5 and 500 trades over the test window) — guards against degenerate "always buy" or "never trade" strategies.
   - [ ] Max single-bar drawdown is finite and reported.

   **Documentation:**
   - [ ] One-line summary added to `strategies/README.md` table.
   - [ ] Docstring on the class is written as if for an agent reading it cold — no internal jargon.

   This checklist is the enabling artifact for Phase 9's "agent proposes strategies as PRs": the agent has a finite, mechanical bar to clear, and CI is the referee.

**Definition of done:** An agent can call `list_strategies()` → get JSON schema for every strategy → instantiate one by name with validated params. A new strategy can be added by following `CONTRIBUTING.md` alone, with no edits to the scanner, backtester, or agent tool layer.

---

## 7. Phase 5 — Execution Safety (Weeks 7–8)

This is the highest-risk phase. Capital is involved. Move slowly.

**Deliverables:**
1. **Implement the real TCBS order path** (`order_manager.py:64`). Behind safe-mode, with full logging.
2. **Pre-trade validator** (`PreTradeValidator`): position count limit, price-bound check (within X% of last close), notional limit, available cash, instrument tradability (board, lot size). Returns `RiskCheckResult` — order placement is **gated** on this passing.
3. **Idempotent OrderTracker.** Every order has a client-generated `client_order_id` (UUID); duplicates rejected. Tracker reads back on startup to recover state after crashes.
4. **Position reconciliation v2.** Sync diffs mock vs API state, raises `PositionDriftError` if delta exceeds threshold; never silently overwrites without a logged diff.
5. **Kill-switch.** `EXECUTION_DISABLED=true` env var hard-blocks every order, regardless of safe-mode. Belt and braces.
6. **Single execution path.** Pick `AutoTrader` (async) as canonical; deprecate `main.py + TradeManager`. Document the decision.
7. **Soak test.** Run on paper for 2 weeks against live data; reconcile every bar. No silent state drift allowed.

**Definition of done:** A real (small) live trade executes end-to-end with full audit trail, idempotency, and a recovery path proven by a kill -9 mid-flight.

---

## 8. Phase 6 — Observability (Week 9)

**Deliverables:**
1. **Structured logging.** Replace every `print()` with `logger.info(event, **fields)`. JSON output. One logger per module.
2. **Correlation IDs.** Every request/scan/backtest gets a UUID; every log line in that flow carries it.
3. **Metrics.** Counters/timers for: data fetches (hit/miss/error), scans run, signals emitted by strategy, orders placed/rejected/filled, drift events. Stdout for now; Prometheus later.
4. **Audit trail.** Every order decision writes a single row to `decisions.jsonl` with: timestamp, signal, strategy, prices used, validators passed, account snapshot. This is the agent's memory of what it did.
5. **Health endpoint.** `health_check()` returns auth status, data freshness, account sync age, open orders, last error — agent calls this to know whether to act.

**Definition of done:** "What did the system do in the last hour?" answerable in one query against logs and metrics, no rerun needed.

---

## 9. Phase 7 — Tool Layer (Weeks 10–11) — **THE INFLECTION POINT**

This is where the codebase becomes **agent-callable**. Two implementations, pick whichever fits the agent runtime:

### Option A — MCP Server (recommended for Claude/Anthropic agents)

Build a Model Context Protocol server in `tools/mcp_server.py` that exposes each capability as a registered tool. Tool definitions are auto-generated from the Pydantic schemas built in Phase 3.

### Option B — HTTP/JSON-RPC

A FastAPI server with one endpoint per capability. Agent uses standard tool-calling. Easier to debug, slightly more friction.

**Tools to expose (initial set):**

| Tool | Reads | Writes | Notes |
|---|---|---|---|
| `list_symbols()` | universe | – | Returns the configurable universe |
| `get_history(symbol, lookback)` | data | – | Returns `OHLCVFrame` |
| `get_quote(symbol)` | live | – | Returns last price + freshness |
| `compute_indicators(symbol, indicators[])` | data | – | Returns indicator series |
| `list_strategies()` | – | – | Returns strategy registry with schemas |
| `scan_market(strategies[], symbols[]?)` | data | – | Returns `list[ScanResult]` |
| `run_backtest(strategy, params, window, costs)` | data | – | Returns `BacktestResult` |
| `walk_forward(strategy, params, windows)` | data | – | Returns OOS-only stats |
| `get_account()` | account | – | Returns `AccountSnapshot` |
| `get_positions()` | account | – | Returns `list[Position]` |
| `validate_order(req)` | risk | – | Returns `RiskCheckResult` — **agent must call before submit** |
| `submit_order(req)` | – | order | Idempotent on `client_order_id` |
| `cancel_order(id)` | – | order | |
| `get_audit_log(filter)` | logs | – | Replay decisions |
| `health_check()` | – | – | One-call status snapshot |

**Tool design rules:**
- Every tool is **idempotent or explicitly marked side-effecting** in its description.
- Every tool's response carries a `correlation_id` and a `data_freshness_seconds` field.
- Every error is a structured `ToolError` with `code`, `message`, `retriable: bool`, `details`.
- Order-side tools **require** a fresh `RiskCheckResult` token from `validate_order`, expiring in 60s — the agent cannot bypass.

**Definition of done:** A human can drive every workflow (scan → backtest → trade) entirely through tool calls in a chat session, never touching Python directly.

---

## 10. Phase 8 — Agent Integration (Weeks 12–14)

With trustworthy tools in place, build the first agent loops.

**Agent roles to build, in order of risk:**

1. **Research Agent (read-only).**
   Goal: answer questions like "which strategy looks best on this symbol over the last year?" Tools: `get_history`, `compute_indicators`, `run_backtest`, `walk_forward`. Cannot trade. Outputs: a structured research note.

2. **Scanner Agent (read-only).**
   Goal: every morning, run scans across the universe, summarise notable signals, write to a daily report. Tools: `scan_market`, `get_quote`, `list_strategies`. Cannot trade.

3. **Risk Agent (read-only, advisory).**
   Goal: given a proposed order, evaluate it against portfolio context, recent volatility, and concentration. Tools: `get_positions`, `get_history`, `validate_order` (dry-run). Returns a structured opinion. Human places the order.

4. **Paper Trader Agent (writes to paper account only).**
   Goal: end-to-end loop scan → research → risk → submit, but only against the paper trade manager. Same tools as live but `EXECUTION_DISABLED=true` for the real path. Soak for ≥4 weeks.

5. **Live Trader Agent.**
   Only after the paper agent has demonstrated:
   - No risk-rule violations
   - Audit trail matches reasoning
   - Performance roughly tracks backtest expectations
   Hard caps: max position size, max daily loss, max trades/day. Kill-switch always wired.

**Definition of done:** A research agent answers "what's the best strategy for HPG right now?" in one prompt and produces a defensible answer the operator can verify against the audit log.

---

## 11. Phase 9 — Continuous Learning (Ongoing)

Once agents are running, the loop closes:

- **Decision log → research input.** Every agent decision and outcome flows back into a dataset that future research agents query.
- **Strategy proposals.** Periodic agent run that scans the literature / live data and proposes new strategies as PRs (code + backtest + walk-forward report).
- **Drift detection.** Agent monitors live PnL vs backtest expectation; alerts when divergence exceeds threshold.
- **Tool quality feedback.** Agent flags tools that returned unusable results; those become Phase-3 contract fixes.

---

## 12. Cross-Cutting Engineering Standards

Apply throughout all phases:

- **Type hints required** on every public function. `mypy --strict` in CI.
- **Pydantic for all I/O boundaries.** No raw dicts crossing module borders.
- **No silent failures.** Every `except` either re-raises typed or logs+returns a typed error object.
- **Tests with every change.** No new public function lands without at least one test.
- **Idempotency by default.** Side-effecting operations carry client-generated IDs.
- **Read-only first.** New tools default to read-only; write capability is a deliberate, separately-reviewed PR.
- **Documentation is tool-spec.** Docstrings will be the agent's understanding of the function. Write them like API docs.

---

## 13. Order-of-Battle (Concrete Next 5 Steps)

If executing this plan starting tomorrow:

1. **This week:** Phase 0. Stand up `pytest`, write a `FakeDataProvider`, lock in regression tests for the 3 most-used strategies.
2. **Next week:** Phase 1, item 3 (kill the synthetic candle) + item 1 (define `OHLCVFrame`). These two changes alone restore correctness for ~half the live scanner output.
3. **Week 3:** Phase 2, item 1 (eliminate look-ahead). Until this is done, every other backtest result is suspect.
4. **Week 4:** Phase 3, items 1+2 (Pydantic models + typed exceptions). This is the ergonomic transformation that makes everything afterwards faster.
5. **Week 5:** Decide MCP vs HTTP for the eventual tool layer (Phase 7), and start writing tool docstrings in that format from Phase 3 onward — so when Phase 7 arrives, wrapping is mechanical.

---

## 14. What "done" looks like

A future operator (or you, six months from now) can sit down with a Claude agent and say:

> "Look at the universe. Find me a strategy that has held up out-of-sample on at least 5 symbols over the last 2 years. Show me the walk-forward stats. If you're confident, propose a paper-trade plan and run it for a week."

…and the agent does it, end-to-end, using only the tools this codebase exposes, and the operator can audit every step from the decision log.

That is the goal. Everything in this plan is in service of it.
