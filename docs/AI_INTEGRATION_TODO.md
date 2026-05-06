# AI-Agent Integration — Execution To-Do List

**Source:** `docs/AI_INTEGRATION_PLAN.md`
**Generated:** 2026-05-06
**Format:** Mechanical checklist; each item is mergeable as its own PR unless noted.

Legend: `[ ]` open · `[~]` in progress · `[x]` done · `★` blocking next phase

---

## Phase 0 — Test Harness Foundation (Week 1) ★

Goal: `make test` green from clean clone, no credentials.

- [ ] Create `tests/` package with `__init__.py`, `pytest.ini` (testpaths, markers `unit|integration|slow`).
- [ ] Add `tests/conftest.py` with shared fixtures.
- [ ] Add `tests/fixtures/` and check in 2–3 small OHLCV CSVs (e.g. HPG, TCB, FPT — 500 bars each).
- [ ] Build `FakeStockApiClient` — in-memory responses for auth, quote, history, order endpoints.
- [ ] Build `FakeDataProvider` — returns fixture DataFrames; supports cache hit/miss simulation.
- [ ] Regression seal: one fixture-based test per strategy in `stock_system_v2/strategies/` locking current signal output.
  - [ ] `SimpleMAStrategy`
  - [ ] `RSIStrategy`
  - [ ] `VolumeBoomStrategy`
  - [ ] `IntradayDipStrategy`
  - [ ] `DipBuyStrategy`
  - [ ] `CumulativeDropStrategy`
  - [ ] `RSIDivergenceStrategy`
- [ ] End-to-end backtester test on synthetic series with known outcome (deterministic seed).
- [ ] Add `Makefile` targets: `make test`, `make lint`, `make typecheck`.
- [ ] Wire CI: GitHub Actions running `pytest`, `ruff check`, `mypy` on push/PR.
- [ ] README badge for CI status.

**DoD:** Fresh clone → `make test` exits 0 with no network/credentials.

---

## Phase 1 — Data Correctness (Weeks 2–3) ★

Goal: Trustworthy OHLCV; one source-of-truth schema.

- [ ] Define `OHLCVFrame` schema (Pydantic or pandera) — required cols, dtypes, monotonic UTC index.
- [ ] Insert schema validation at every fetch boundary in `data_ingest/data_provider.py`.
- [ ] **Decision:** Source strategy — Option A (vnstock-only, drop TCBS realtime) vs Option B (both + Reconciler). Document in `docs/ADR-001-data-source.md`.
- [ ] Implement chosen option:
  - [ ] If A: remove TCBS realtime merge path; update tests.
  - [ ] If B: build `Reconciler` comparing last-N closes; warn if delta > X bps.
- [ ] Kill synthetic-candle bug:
  - [ ] Mark today's bar `is_partial=True`.
  - [ ] Either exclude today from indicator pass OR carry `volume_so_far` from live tape.
  - [ ] Volume strategies must not silently misfire on scan day — add explicit test.
- [ ] Replace `<500 → ×1000` heuristic with explicit `price_unit` column or per-symbol metadata table loaded once.
- [ ] Replace IPO 5-day tolerance with `min_bars_required` parameter on cache validation; cache miss if insufficient.
- [ ] Add hypothesis property tests:
  - [ ] No NaN in close after fetch.
  - [ ] Index strictly monotonic.
  - [ ] `volume >= 0`.
  - [ ] `price > 0`.
- [ ] Idempotency test: same symbol fetched twice on consecutive days → identical historical bars.

**DoD:** Two-day rerun produces identical history; volume strategies don't silently misfire live.

---

## Phase 2 — Backtesting Rigor (Weeks 3–4)

Can overlap with Phase 1.

- [ ] Audit every indicator in `core/indicator_engine.py` for look-ahead; document each lookback window.
- [ ] Build `assert_no_lookahead(df_or_strategy)` test utility (shifts inputs by k, asserts signals shift by k).
- [ ] Apply utility to every existing strategy; fix any leakage found.
- [ ] Implement transaction cost model: `commission_bps`, `slippage_bps`, `min_ticket_vnd` — defaults to TCBS real costs.
- [ ] Define `PositionSizer` interface:
  - [ ] `FixedFractionSizer`
  - [ ] `EqualWeightSizer`
  - [ ] `VolatilityTargetedSizer`
  - [ ] Inject into `core/backtester.py`; replace "all cash → one name".
- [ ] Build `WalkForwardBacktester` (rolling train/test windows; reports OOS-only stats).
- [ ] Add survivor-bias disclaimer field to every backtest report.
- [ ] Define unified `BacktestResult` Pydantic model with `holding_strategy: "native" | "fixed"`; merge native and fixed-hold paths.
- [ ] Re-run top-3 momentum backtest with costs + walk-forward; document delta vs old report.

**DoD:** Re-run produces more conservative numbers; delta documented.

---

## Phase 3 — Public-API Contracts (Weeks 4–5) ★

Goal: codebase becomes "tools" not "scripts."

- [ ] Create `stock_system_v2/schemas/` package with Pydantic models:
  - [ ] `OHLCVFrame`
  - [ ] `Signal`
  - [ ] `ScanResult`
  - [ ] `BacktestResult`
  - [ ] `OrderRequest` / `OrderResponse`
  - [ ] `Position`
  - [ ] `AccountSnapshot`
  - [ ] `RiskCheckResult`
  - [ ] `MarketContext`
- [ ] Create `stock_system_v2/exceptions.py`:
  - [ ] `DataFetchError`
  - [ ] `StaleCacheError`
  - [ ] `InsufficientHistoryError`
  - [ ] `InvalidParameterError`
  - [ ] `OrderRejectedError`
  - [ ] `RiskLimitViolatedError`
  - [ ] `AuthExpiredError`
- [ ] Replace every `except Exception: return None` — narrow catch + typed raise, or remove.
- [ ] Refactor to dependency injection:
  - [ ] `MarketScanner(data_provider, indicator_engine, strategies)`
  - [ ] `AutoTrader(...)` — no internal instantiation
  - [ ] All construction in entry-point scripts.
- [ ] Replace global `config` import with `Settings(BaseSettings)`; pass explicitly; allow per-call overrides.
- [ ] Write agent-grade docstring on every public method (purpose, params, returns, raises, example).
- [ ] Eliminate `Dict[str, Any]` from public signatures.
- [ ] Enable `mypy --strict` on V2 package; fix until clean.

**DoD:** `mypy --strict` passes; every public function has agent-readable docstring.

---

## Phase 4 — Strategy Framework v2 (Week 6)

- [ ] Add `StrategyParams` Pydantic base class; convert every strategy's params.
- [ ] Add `min_bars_required` class attr; base class refuses signals before threshold.
- [ ] Add `.describe() -> StrategyDescription` to base + every strategy.
- [ ] Replace ad-hoc context columns with typed `signal_context: dict` + accessor.
- [ ] Codify `CombinedStrategy` precedence: simultaneous buy+sell → sell wins; AND = unanimous; OR = any. Add tests.
- [ ] Build `STRATEGIES` registry (`dict[str, type[SignalStrategy]]`).
- [ ] Write `stock_system_v2/strategies/CONTRIBUTING.md` covering:
  - [ ] Code requirements checklist
  - [ ] Required test list (regression / no-lookahead / warmup / param-validation / determinism)
  - [ ] Performance smoke gates (Sharpe report, trade-count bounds, max drawdown)
  - [ ] Documentation requirements
- [ ] Add `make strategy-smoke <name>` Makefile target running smoke gates.
- [ ] Wire smoke gates into CI for any PR touching `strategies/`.
- [ ] Migrate every existing strategy to satisfy the checklist.

**DoD:** Agent can `list_strategies()` → schema → instantiate; new strategy mergeable via CONTRIBUTING alone.

---

## Phase 5 — Execution Safety (Weeks 7–8) ★ HIGH RISK

- [ ] Implement real TCBS order path at `execution/order_manager.py:64`, behind safe-mode + full logging.
- [ ] Build `PreTradeValidator`:
  - [ ] Position-count limit
  - [ ] Price-bound check (within X% of last close)
  - [ ] Notional limit
  - [ ] Available cash
  - [ ] Tradability (board, lot size)
  - [ ] Returns `RiskCheckResult` (typed token, 60s TTL).
- [ ] Gate all order placement on `RiskCheckResult` pass.
- [ ] Add `client_order_id` (UUID) to every order; reject duplicates in `OrderTracker`.
- [ ] Implement crash recovery: `OrderTracker` reads back open orders on startup.
- [ ] Position reconciliation v2: diff mock vs API; raise `PositionDriftError` over threshold; never silently overwrite.
- [ ] Add `EXECUTION_DISABLED=true` env-var hard kill-switch (overrides safe-mode).
- [ ] **Decision:** Canonical execution path = `AutoTrader` (async). Deprecate `main.py + TradeManager`. ADR `docs/ADR-002-execution-path.md`.
- [ ] Run 2-week paper soak vs live data; reconcile every bar; zero silent drift.
- [ ] Crash-recovery test: `kill -9` mid-flight, restart, state recovered from tracker.

**DoD:** Real (small) live trade end-to-end with audit trail, idempotency, proven recovery.

---

## Phase 6 — Observability (Week 9)

- [ ] Replace every `print()` with module-scoped `logger.info(event, **fields)`; JSON output.
- [ ] Add correlation-ID middleware: every scan/backtest/order request gets a UUID; propagated in all log lines.
- [ ] Counters/timers (start with stdout/jsonl; Prometheus later):
  - [ ] data fetches: hit/miss/error
  - [ ] scans run
  - [ ] signals emitted by strategy
  - [ ] orders placed/rejected/filled
  - [ ] drift events
- [ ] Audit trail: write `decisions.jsonl` row per order decision (timestamp, signal, strategy, prices, validators, account snapshot).
- [ ] Build `health_check()` returning auth, data freshness, account sync age, open orders, last error.

**DoD:** "What did the system do in the last hour?" answerable from logs/metrics in one query.

---

## Phase 7 — Tool Layer (Weeks 10–11) ★ INFLECTION POINT

- [ ] **Decision:** MCP vs HTTP. ADR `docs/ADR-003-tool-protocol.md`.
- [ ] Scaffold `tools/` package with chosen protocol.
- [ ] Auto-generate tool schemas from Phase 3 Pydantic models.
- [ ] Implement read-only tools first:
  - [ ] `list_symbols`
  - [ ] `get_history`
  - [ ] `get_quote`
  - [ ] `compute_indicators`
  - [ ] `list_strategies`
  - [ ] `scan_market`
  - [ ] `run_backtest`
  - [ ] `walk_forward`
  - [ ] `get_account`
  - [ ] `get_positions`
  - [ ] `get_audit_log`
  - [ ] `health_check`
- [ ] Implement gated write tools:
  - [ ] `validate_order` (returns short-lived token)
  - [ ] `submit_order` (requires fresh `RiskCheckResult` token; idempotent on `client_order_id`)
  - [ ] `cancel_order`
- [ ] Tool framework rules:
  - [ ] Each tool marked `idempotent` or `side_effecting` in description.
  - [ ] Every response carries `correlation_id` + `data_freshness_seconds`.
  - [ ] Errors are structured `ToolError(code, message, retriable, details)`.
  - [ ] Order tools enforce 60s `RiskCheckResult` token freshness.
- [ ] Smoke test: drive scan → backtest → paper-trade entirely through tool calls in a chat session.

**DoD:** A human runs every workflow via tool calls only — no Python.

---

## Phase 8 — Agent Integration (Weeks 12–14)

Build agents in ascending risk order. Each soak-tests before next.

- [ ] **Research Agent (read-only)** — answers "best strategy for symbol X over window Y." Tools: history, indicators, backtest, walk-forward. Output: structured research note.
- [ ] **Scanner Agent (read-only)** — daily morning scan + signal summary; writes daily report.
- [ ] **Risk Agent (read-only, advisory)** — evaluates proposed orders vs portfolio; uses `validate_order` dry-run.
- [ ] **Paper Trader Agent** — full loop scan→research→risk→submit, paper account only (`EXECUTION_DISABLED=true` for live). ≥4-week soak.
- [ ] Paper-trader graduation review:
  - [ ] No risk-rule violations
  - [ ] Audit trail matches reasoning
  - [ ] Performance roughly tracks backtest expectations
- [ ] **Live Trader Agent** — only after graduation. Hard caps: max position size, max daily loss, max trades/day. Kill-switch wired.

**DoD:** Research agent answers "best strategy for HPG right now?" defensibly + auditably in one prompt.

---

## Phase 9 — Continuous Learning (Ongoing)

- [ ] Pipeline `decisions.jsonl` → research-agent input dataset.
- [ ] Periodic strategy-proposal agent run; output is a PR (code + backtest + walk-forward).
- [ ] Drift-detection agent: live PnL vs backtest expectation; alert on threshold breach.
- [ ] Tool-quality feedback loop: agent flags bad tool outputs → Phase 3 contract fixes.

---

## Cross-Cutting Standards (apply throughout)

- [ ] Type hints required on every public function; `mypy --strict` enforced in CI.
- [ ] Pydantic at every I/O boundary; no raw dicts cross modules.
- [ ] No silent failures: every `except` re-raises typed or returns typed error.
- [ ] No public function lands without ≥1 test.
- [ ] Side-effecting ops carry client-generated IDs (idempotency).
- [ ] New tools default read-only; write capability requires separate review.
- [ ] Docstrings written as agent-facing API docs.

---

## Order-of-Battle (next 5 weeks)

1. **Week 1** — Phase 0 complete; pytest + FakeDataProvider + 3-strategy regression seal.
2. **Week 2** — Phase 1 items 1+3 (OHLCVFrame schema + kill synthetic candle).
3. **Week 3** — Phase 2 item 1 (eliminate look-ahead) + `assert_no_lookahead` utility.
4. **Week 4** — Phase 3 items 1+2 (Pydantic schemas + typed exceptions).
5. **Week 5** — MCP-vs-HTTP decision + start writing Phase-3 docstrings in tool-spec form.
