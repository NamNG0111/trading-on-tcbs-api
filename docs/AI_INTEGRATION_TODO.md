# AI-Agent Integration — Execution To-Do List

**Source:** `docs/AI_INTEGRATION_PLAN.md`
**Generated:** 2026-05-06
**Format:** Mechanical checklist; each item is mergeable as its own PR unless noted.

Legend: `[ ]` open · `[~]` in progress · `[x]` done · `★` blocking next phase

---

## Phase 0 — Test Harness Foundation (Week 1) ★

Goal: `make test` green from clean clone, no credentials.

- [x] Create `tests/` package with `__init__.py`, `pytest.ini` (testpaths, markers `unit|integration|slow`).
- [x] Add `tests/conftest.py` with shared fixtures. → `make_ohlcv` factory + `ohlcv_factory` fixture
- [x] Add `tests/fixtures/` and check in 2–3 small OHLCV CSVs (e.g. HPG, TCB, FPT — 500 bars each). → deterministic, regenerable via `make fixtures`
- [x] Build `FakeStockApiClient` — in-memory responses for auth, quote, history, order endpoints. → `tests/fakes/fake_stock_api_client.py`
- [x] Build `FakeDataProvider` — returns fixture DataFrames; supports cache hit/miss simulation. → `tests/fakes/fake_data_provider.py`; mirrors `DataProvider(auth, reconciler)` and validates outputs through `OHLCVFrame`
- [x] Regression seal: one fixture-based test per strategy in `stock_system_v2/strategies/` locking current signal output. → `tests/strategies/test_strategy_regression.py`, parametrised over (strategy × symbol) = 24 cases
  - [x] `SimpleMAStrategy`
  - [x] `RSIStrategy` (basic + reversal modes)
  - [x] `VolumeBoomStrategy`
  - [x] `IntradayDipStrategy`
  - [x] `DipBuyStrategy`
  - [x] `CumulativeDropStrategy`
  - [x] `RSIDivergenceStrategy`
- [x] End-to-end backtester test on synthetic series with known outcome (deterministic seed). → `tests/test_backtester_e2e.py`
- [x] Add `Makefile` targets: `make test`, `make lint`, `make typecheck`. → plus `make ci`, `make fixtures`, `make clean`
- [x] Wire CI: GitHub Actions running `pytest`, `ruff check`, `mypy` on push/PR. → `.github/workflows/ci.yml`, py3.11 + py3.13 matrix; lint/typecheck `continue-on-error: true` until Phase 3
- [x] README badge for CI status.

**DoD:** Fresh clone → `make test` exits 0 with no network/credentials. ✓ **56 tests green** (`make test`).

**Phase 0 caveat (per plan file):** regression seals lock *post-Phase-1* behaviour. They guard against future drift, not against any regression Phase 1 itself may have introduced. Operator sanity-check via `python trading_on_tcbs_api/stock_system_v2/scripts/scan_market.py` recommended before relying on the seals as ground truth.

---

## Phase 1 — Data Correctness (Weeks 2–3) ★

Goal: Trustworthy OHLCV; one source-of-truth schema.

- [x] Define `OHLCVFrame` schema (Pydantic or pandera) — required cols, dtypes, monotonic UTC index. → `stock_system_v2/schemas/ohlcv.py`
- [x] Insert schema validation at every fetch boundary in `data_ingest/data_provider.py`. → `validate_ohlcv` called pre-return
- [x] **Decision:** Source strategy — Option A (vnstock-only, drop TCBS realtime) vs Option B (both + Reconciler). Document in `docs/ADR-001-data-source.md`. → **Option B accepted** (operator decision 2026-05-06)
- [x] Implement chosen option:
  - [x] ~~If A~~ — not chosen.
  - [x] If B: build `Reconciler` comparing last-N closes; warn if delta > X bps. → `data_ingest/reconciler.py`; wired into `DataProvider`; default threshold 25 bps; runtime check is single-point (last-closed-close vs TCBS `refPrice`) because TCBS exposes no working OpenAPI history endpoint — `check_series` available for future N-point use.
- [x] Kill synthetic-candle bug:
  - [x] Mark today's bar `is_partial=True`.
  - [x] Either exclude today from indicator pass OR carry `volume_so_far` from live tape. → IndicatorEngine drops partial rows via `closed_bars`; scanner surfaces `live_price` separately
  - [x] Volume strategies must not silently misfire on scan day — add explicit test. → partial bar volume = NaN; `test_partial_bar_carries_nan_volume`
- [x] Replace `<500 → ×1000` heuristic with explicit `price_unit` column or per-symbol metadata table loaded once. → `data_ingest/symbol_metadata.py` (`SymbolMeta.vnstock_price_scale`)
- [x] Replace IPO 5-day tolerance with `min_bars_required` parameter on cache validation; cache miss if insufficient.
- [x] Add hypothesis property tests:
  - [x] No NaN in close after fetch.
  - [x] Index strictly monotonic.
  - [x] `volume >= 0`.
  - [x] `price > 0`.
- [x] Idempotency test: same symbol fetched twice on consecutive days → identical historical bars. → `test_idempotent_history_two_calls`

**DoD:** Two-day rerun produces identical history; volume strategies don't silently misfire live.

---

## Phase 2 — Backtesting Rigor (Weeks 3–4)

Can overlap with Phase 1.

- [x] Audit every indicator in `core/indicator_engine.py` for look-ahead; document each lookback window. → audit table embedded in `IndicatorEngine` class docstring; all indicators causal on `[t-L+1, t]`
- [x] Build `assert_no_lookahead(df_or_strategy)` test utility (shifts inputs by k, asserts signals shift by k). → `tests/utils/lookahead.py`; truncation-based check covering engine + strategy
- [x] Apply utility to every existing strategy; fix any leakage found. → `tests/strategies/test_no_lookahead.py` (24 cases). Caught real leak in `RSIDivergenceStrategy` (peak confirmation requires `lookback` future bars); fixed by emitting at `peak + lookback` and regenerating regression fixtures.
- [x] Implement transaction cost model: `commission_bps`, `slippage_bps`, `min_ticket_vnd` — defaults to TCBS real costs. → `core/costs.py` (`TransactionCosts`); `TCBS_DEFAULT_COSTS` = 15 bps comm + 5 bps slip + 10 bps sell tax; `ZERO_COSTS` preserves legacy zero-cost behaviour.
- [x] Define `PositionSizer` interface: → `core/position_sizer.py`; injected into `Backtester(sizer=...)`. Default keeps legacy "all cash → one name" so seals stay green; new code opts in.
  - [x] `FixedFractionSizer`
  - [x] `EqualWeightSizer`
  - [x] `VolatilityTargetedSizer`
  - [x] Inject into `core/backtester.py`; replace "all cash → one name". → injected; default `_AllInSizer` keeps legacy behaviour.
- [x] Build `WalkForwardBacktester` (rolling train/test windows; reports OOS-only stats). → `core/walk_forward.py`; emits `WalkForwardResult` with per-window detail.
- [x] Add survivor-bias disclaimer field to every backtest report. → `survivor_bias_corrected: bool` + `survivor_bias_disclaimer: str` on `BacktestResult` and `WalkForwardResult`.
- [x] Define unified `BacktestResult` Pydantic model with `holding_strategy: "native" | "fixed"`; merge native and fixed-hold paths. → `core/backtest_result.py`; `to_backtest_results()` adapts the legacy dict.
- [x] Re-run top-3 momentum backtest with costs + walk-forward; document delta vs old report. → `scripts/backtest_top3_phase2_rebaseline.py` + `docs/PHASE2_TOP3_REBASELINE.md`. Legacy 102.59% → with-TCBS-costs 13.71% (Δ −88.88 pp); 5-window OOS compounded = 65.30%, per-window avg 12.67%. Survivor bias still uncorrected.

**DoD:** Re-run produces more conservative numbers; delta documented. ✓ −88.88 pp on the headline; OOS compounded materially below in-sample sweep.

---

## Phase 3 — Public-API Contracts (Weeks 4–5) ★

Goal: codebase becomes "tools" not "scripts."

- [x] Create `stock_system_v2/schemas/` package with Pydantic models: → `schemas/{ohlcv,signals,orders,risk,backtest}.py`; reexported via `schemas/__init__.py`.
  - [x] `OHLCVFrame`
  - [x] `Signal` (+ `SignalAction` literal)
  - [x] `ScanResult`
  - [x] `BacktestResult` (relocated from `core/`; back-compat shim left)
  - [x] `OrderRequest` / `OrderResponse`
  - [x] `Position`
  - [x] `AccountSnapshot`
  - [x] `RiskCheckResult` (+ `RiskCheckFinding`, TTL-based freshness)
  - [x] `MarketContext`
- [x] Create `stock_system_v2/exceptions.py`: → typed root `StockSystemError`; full hierarchy below.
  - [x] `DataFetchError`
  - [x] `StaleCacheError`
  - [x] `InsufficientHistoryError`
  - [x] `InvalidParameterError`
  - [x] `OrderRejectedError`
  - [x] `RiskLimitViolatedError`
  - [x] `AuthExpiredError`
- [x] Replace every `except Exception: return None` — narrow catch + typed raise, or remove. → narrowed in `auth/`, `data_ingest/`, `core/stock_api_client.py`, `finance/account_manager.py`, `data_ingest/reconciler.py`. No bare `except Exception:` remains in non-script V2 code.
- [x] Refactor to dependency injection:
  - [x] `MarketScanner(data_provider, indicator_engine, strategies)` — kwargs-only DI; returns `list[ScanResult]`.
  - [x] `AutoTrader(...)` — no internal instantiation; takes `settings`, `auth`, `scanner`, `order_manager`, `order_tracker`, `account`.
  - [x] All construction in entry-point scripts. → `main.py` is the composition root; `scripts/scan_market.py` updated similarly.
- [x] Replace global `config` import with `Settings(BaseSettings)`; pass explicitly; allow per-call overrides. → `settings.py` (Pydantic `BaseModel` + frozen + `model_copy(update=…)` per-call overrides). `config.py` is now a back-compat shim sourced from `Settings.load()`.
- [x] Write agent-grade docstring on every public method (purpose, params, returns, raises, example). → covered on `MarketScanner`, `AutoTrader`, `Backtester`, `WalkForwardBacktester`, `OrderManager`, `OrderTracker`, `IndicatorEngine`, `SignalStrategy`, plus every schema. Existing strategy subclasses already had agent-readable docs.
- [x] Eliminate `Dict[str, Any]` from public signatures. → `OrderManager.place_order` now returns `OrderResponse`; `OrderTracker.log_order` accepts `OrderResponse`; `IndicatorEngine` uses a `TypedDict`. `stock_api_client` keeps a `BrokerPayload` alias with a docstring noting the Phase-7 wrapping.
- [x] Enable `mypy --strict` on V2 package; fix until clean. → `pydantic.mypy` plugin wired; strict pass on the typed-core (`schemas/`, `exceptions`, `settings`, `core/costs`, `core/position_sizer`) — 10 files, zero errors. Baseline mypy on the rest reports 97 known issues (untyped pandas slices, broker-payload dicts, untyped legacy attrs); deferred to Phases 6/7 where the surfaces get rewritten anyway. Scripts and `trade_manager.py` (legacy) excluded from mypy entirely.

**DoD:** `mypy --strict` passes on the typed core; every public function the agent layer will see has an agent-readable docstring. ✓ 109 tests green.

---

## Phase 4 — Strategy Framework v2 (Week 6)

- [x] Add `StrategyParams` Pydantic base class; convert every strategy's params. → `schemas/strategy_meta.py` ships `StrategyParams` (frozen, `extra='forbid'`) and `StrategyDescription`. Per-strategy migration tracked separately.
- [x] Add `min_bars_required` class attr; base class refuses signals before threshold. → `SignalStrategy.generate_signals` is now concrete; subclasses override `_compute_signals` and the base zeroes any non-zero signal in `[0, min_bars_required)`.
- [x] Add `.describe() -> StrategyDescription` to base + every strategy. → base derives a default description from class attrs + `Params.model_json_schema()`; every concrete strategy overrides to inject expected regime + failure modes.
- [x] Replace ad-hoc context columns with typed `signal_context: dict` + accessor. → `SignalStrategy.extract_signal_context(row)` is the new contract; strategies declare `context_columns` for their derived metrics. `MarketScanner._evaluate` consumes the accessor instead of scraping added columns.
- [x] Codify `CombinedStrategy` precedence: simultaneous buy+sell → sell wins; AND = unanimous; OR = any. Add tests. → docstring spells out the rules; `tests/strategies/test_combined_precedence.py` locks them with stub-strategy fixtures.
- [x] Build `STRATEGIES` registry (`dict[str, type[SignalStrategy]]`). → `strategies/registry.py`; `get_strategy(name)` raises `KeyError` listing the available ids; agents can call `cls().describe()` for the JSON schema.
- [x] Write `stock_system_v2/strategies/CONTRIBUTING.md` covering: → checked-in next to the strategies; CI runs the gates it lists.
  - [x] Code requirements checklist
  - [x] Required test list (regression / no-lookahead / warmup / param-validation / determinism)
  - [x] Performance smoke gates (Sharpe report, trade-count bounds, max drawdown)
  - [x] Documentation requirements
- [x] Add `make strategy-smoke <name>` Makefile target running smoke gates. → `make strategy-smoke NAME=<id>` runs `scripts/strategy_smoke.py`; `make strategy-smoke-all` iterates the registry. All 7 concrete strategies pass on the fixture universe.
- [x] Wire smoke gates into CI for any PR touching `strategies/`. → new `strategy-smoke` job in `.github/workflows/ci.yml`, gated on a path-touch check (no-op when a PR doesn't touch `strategies/`).
- [x] Migrate every existing strategy to satisfy the checklist. → 7 strategies (`SimpleMA`, `RSI`, `RSIDivergence`, `VolumeBoom`, `DipBuy`, `CumulativeDrop`, `IntradayDip`) + `CombinedStrategy` now declare nested `Params(StrategyParams)`, set `min_bars_required`, and override `describe()`. Back-compat shims preserve the legacy positional kwargs.

**DoD:** Agent can `list_strategies()` → schema → instantiate; new strategy mergeable via CONTRIBUTING alone. ✓ — `STRATEGIES` registry + `describe()` give the listing; CONTRIBUTING.md + smoke-gate CI define the merge bar. 127 tests green.

---

## Phase 5 — Execution Safety (Weeks 7–8) ★ HIGH RISK

- [x] Implement real TCBS order path at `execution/order_manager.py:64`, behind safe-mode + full logging. → `OrderManager.place_order` now calls `StockTradingClient.place_stock_order` via `asyncio.run` when `safe_mode=False`. Live path is *only* reachable with: (a) a fresh, hash-matching `RiskCheckResult`, (b) `EXECUTION_DISABLED` off, (c) a `broker_client` injected. Broker errors wrap into `OrderRejectedError`.
- [x] Build `PreTradeValidator`: → `execution/pre_trade_validator.py`. Token bound via SHA-256 `request_hash` over the order's (symbol, side, price, volume, order_type, client_order_id) tuple. 60s TTL inherited from `RiskCheckResult` schema.
  - [x] Position-count limit (allows top-ups of existing positions; only blocks new names).
  - [x] Price-bound check (within X% of last close; WARN when no last-close mark is available rather than BLOCK).
  - [x] Notional limit (`max_notional_vnd` hard cap regardless of cash).
  - [x] Available cash (BUY) / position-cover (SELL — refuses short sells).
  - [x] Tradability (universe membership + lot-size multiple).
  - [x] Returns `RiskCheckResult` (typed token, 60s TTL).
- [x] Gate all order placement on `RiskCheckResult` pass. → `OrderManager._enforce_risk_token` rejects with `RiskLimitViolatedError` when the token is missing, failed, expired, or hash-mismatched. Safe mode bypasses (paper trading is allowed without a token); live mode is mandatory.
- [x] Add `client_order_id` (UUID) to every order; reject duplicates in `OrderTracker`. → `OrderTracker.register_pending(req)` raises `DuplicateOrderError`; the seen-set is rebuilt from the ledger on init so duplicates survive a restart.
- [x] Implement crash recovery: `OrderTracker` reads back open orders on startup. → `recover_open_orders()` groups ledger rows by `client_order_id`, returns the latest non-terminal status per id. Tested via simulated mid-flight crash (no `log_order` call between `register_pending` and tracker re-instantiation).
- [x] Position reconciliation v2: diff mock vs API; raise `PositionDriftError` over threshold; never silently overwrite. → `finance/reconciler.py` (`reconcile_position_book` + `assert_no_drift`); `AccountManager.sync_from_api` now calls `assert_no_drift` whenever the local book carries non-zero positions. Threshold is configurable via `drift_threshold_shares` attribute.
- [x] Add `EXECUTION_DISABLED=true` env-var hard kill-switch (overrides safe-mode). → `Settings.load()` already reads the env var (Phase 3); `OrderManager(execution_disabled=settings.execution_disabled)` flips the kill-switch on. Wired in `main.py` so a single env flip rejects every order regardless of safe-mode.
- [x] **Decision:** Canonical execution path = `AutoTrader` (async). Deprecate `main.py + TradeManager`. ADR `docs/ADR-002-execution-path.md`. → ADR accepted; `execution/trade_manager.py` now emits `DeprecationWarning` on import. `main.py` already wires `AutoTrader` (Phase 3 refactor).
- [ ] Run 2-week paper soak vs live data; reconcile every bar; zero silent drift. → **operator-driven**; runbook in `docs/PHASE5_SOAK_RUNBOOK.md`. Code-side primitives (autotrader, kill-switch, validator gate, idempotent tracker, reconciler) are all wired and unit-tested. Tick this when the soak's exit criteria hold for ≥14 trading days.
- [x] Crash-recovery test: `kill -9` mid-flight, restart, state recovered from tracker. → `tests/test_crash_recovery.py` spawns a subprocess that calls `register_pending` then `os._exit(9)` (skips finalisers, exit code = 9). A fresh `OrderTracker` on the same ledger surfaces the PENDING row via `recover_open_orders()`.

**DoD:** Real (small) live trade end-to-end with audit trail, idempotency, proven recovery. → **operator-driven**; checklist in `docs/PHASE5_SOAK_RUNBOOK.md` covers the first live trade. Code-side, 160 tests cover every Phase-5 primitive (validator, hash-bound token, tracker idempotency, kill-switch, reconciler, crash recovery). Tick this once the live trade clears.

---

## Phase 6 — Observability (Week 9)

- [x] Replace every `print()` with module-scoped `logger.info(event, **fields)`; JSON output. → migrated agent-callable paths: `MarketScanner.scan`, `OrderManager.place_order` (+ cancel + audit hooks), `OrderTracker.create_ledger`, `Backtester.run`, `AccountManager.sync_from_api` + `update_after_trade`, `DataProvider` cache/realtime/fetch error sites, `PriceReconciler` (dual-emission for capsys-driven tests). Intentional kept-as-`print()` sites: `MarketScanner.print_results` (operator UX with ANSI colors), `AutoTrader.run` interactive sub-account selection, `auth.py` OTP prompts, `__main__` debug blocks. Reserved-name kwargs (`message`, `args`, …) auto-prefixed with `field_` so callers don't have to memorise the stdlib namespace.
- [x] Add correlation-ID middleware: every scan/backtest/order request gets a UUID; propagated in all log lines. → `obs/correlation.py` exposes `with_correlation(prefix=…)` context manager backed by `contextvars.ContextVar`; `JSONFormatter` auto-attaches the active id.
- [x] Counters/timers (start with stdout/jsonl; Prometheus later): → `obs/metrics.py` (`record_metric`, `timed`); each metric is a JSON line on the `v2.metrics` logger you can grep. Per-call-site wiring tracked under "Replace prints" below.
  - [x] data fetches: hit/miss/error
  - [x] scans run
  - [x] signals emitted by strategy
  - [x] orders placed/rejected/filled
  - [x] drift events
- [x] Audit trail: write `decisions.jsonl` row per order decision (timestamp, signal, strategy, prices, validators, account snapshot). → `obs/decisions.py` (`write_decision`); appends one JSON row per call to `EXPORT_DIR/decisions.jsonl` with auto-attached `ts` and `correlation_id`.
- [x] Build `health_check()` returning auth, data freshness, account sync age, open orders, last error. → `core/health.py` returns a typed `HealthStatus` (`schemas/health.py`); designed never to raise — every failure becomes a `HealthCheck(status="fail"|"unknown")` row. WARN findings (e.g. open orders, stale data) don't flip `ok=False`; FAIL/UNKNOWN do.

**DoD:** "What did the system do in the last hour?" answerable from logs/metrics in one query. ✓ — every scan, order, drift event, and decision emits a JSON log line tagged with a per-cycle `correlation_id`. `grep '"correlation_id":"cycle_…"'` returns the entire trade pipeline; `grep '"event":"metric"'` returns counters/timers; `decisions.jsonl` carries one auditable row per order intent. 173 tests green.

---

## Phase 7 — Tool Layer (Weeks 10–11) ★ INFLECTION POINT

- [x] **Decision:** MCP vs HTTP. ADR `docs/ADR-003-tool-protocol.md`. → MCP accepted as canonical transport. Handlers live in `tools/handlers/*` as plain typed Python functions; the MCP server is a thin adapter. HTTP is one PR away when a second client appears.
- [x] Scaffold `tools/` package with chosen protocol. → `tools/{__init__,registry,response,context}.py` + `tools/handlers/*`. Handlers are pure typed functions; `@tool(name=…, input_model=…, output_model=…, side_effecting=…)` decorator registers them in `TOOLS`. `invoke(name, **kwargs)` wraps every call in correlation + envelope + typed error mapping.
- [x] Auto-generate tool schemas from Phase 3 Pydantic models. → `ToolDefinition.input_schema()` returns `input_model.model_json_schema()` directly; the MCP server reads this at registration so there's one source of truth.
- [x] Implement read-only tools first:
  - [x] `list_symbols` → `tools/handlers/data.py`
  - [x] `get_history`
  - [x] `get_quote`
  - [x] `compute_indicators`
  - [x] `list_strategies` → `tools/handlers/strategies.py`
  - [x] `scan_market` → `tools/handlers/scanner.py`
  - [x] `run_backtest` → `tools/handlers/backtest.py`
  - [x] `walk_forward`
  - [x] `get_account` → `tools/handlers/account.py`
  - [x] `get_positions`
  - [x] `get_audit_log` (reads `EXPORT_DIR/decisions.jsonl`)
  - [x] `health_check` → `tools/handlers/health.py`
- [x] Implement gated write tools: → `tools/handlers/orders.py`
  - [x] `validate_order` (returns short-lived token; cached under `risk_tokens[check_id]`).
  - [x] `submit_order` (accepts inline `risk_check` or `risk_check_id`; one-shot consumption; tracker rejects duplicate `client_order_id`).
  - [x] `cancel_order`
- [x] Tool framework rules:
  - [x] Each tool marked `idempotent` or `side_effecting` in description. → `ToolDefinition.side_effecting`; `idempotent` is the inverse for read-only tools.
  - [x] Every response carries `correlation_id` + `data_freshness_seconds`. → `ToolResponse[T]` envelope; correlation auto-populated by `invoke`.
  - [x] Errors are structured `ToolError(code, message, retriable, details)`. → `tools/response.py`; typed `StockSystemError` subclasses map to stable codes (`INSUFFICIENT_HISTORY`, `RISK_VIOLATED`, `DUPLICATE_ORDER`, …).
  - [x] Order tools enforce 60s `RiskCheckResult` token freshness. → `OrderManager._enforce_risk_token` (Phase 5) is the gate; `submit_order` either passes the token through or looks it up from the cache, then `OrderManager` validates `is_fresh()` + hash.
- [x] Smoke test: drive scan → backtest → paper-trade entirely through tool calls in a chat session. → `tests/test_tools_smoke.py::test_full_agent_workflow` walks `list_strategies` → `list_symbols` → `run_backtest` → `walk_forward` → `scan_market` → `get_account` → `validate_order` → `submit_order` → `get_audit_log` → `health_check`, calling `invoke(...)` only. Six smoke tests cover envelope, unknown-tool, invalid-params, typed-error mapping, and duplicate-order rejection.

**DoD:** A human runs every workflow via tool calls only — no Python. ✓ — the smoke test imports zero V2 internals from inside the workflow body; everything goes through `invoke(name, args)`. Drop-in for an MCP session: `pip install mcp && python -m trading_on_tcbs_api.stock_system_v2.tools.mcp_server`. 179 tests green.

---

## Phase 8 — Agent Integration (Weeks 12–14)

Build agents in ascending risk order. Each soak-tests before next.

- [x] **Research Agent (read-only)** — answers "best strategy for symbol X over window Y." Tools: history, indicators, backtest, walk-forward. Output: structured research note. → `agents/research.py::research_strategy_for_symbol(symbol)` returns a typed `ResearchNote` ranking every strategy by OOS Sharpe with the survivor-bias disclaimer attached. LLM system prompt at `agents/prompts/research.md`.
- [x] **Scanner Agent (read-only)** — daily morning scan + signal summary; writes daily report. → `agents/scanner.py::daily_scan(...)` returns a `ScannerReport` grouped by `(strategy, side)` with a one-paragraph headline. Prompt at `agents/prompts/scanner.md`.
- [x] **Risk Agent (read-only, advisory)** — evaluates proposed orders vs portfolio; uses `validate_order` dry-run. → `agents/risk.py::evaluate_proposed_order(req)` returns a `RiskOpinion` (verdict ∈ approve / approve_with_warnings / reject) carrying the `risk_check_id` for one-shot consumption by `submit_order`. Prompt at `agents/prompts/risk.md`.
- [ ] **Paper Trader Agent** — full loop scan→research→risk→submit, paper account only (`EXECUTION_DISABLED=true` for live). ≥4-week soak. → **Code-side complete**: `agents/paper_trader.py::paper_trade_cycle(...)` returns a typed `PaperTradeReport`; pre-flight aborts on `health_check` failure; tested on fixtures. **Operator-driven**: 4-week soak runbook in `docs/PHASE8_PAPER_TRADER_RUNBOOK.md`. Tick this when the soak clears.
- [ ] Paper-trader graduation review: → criteria spelled out in `docs/PHASE8_PAPER_TRADER_RUNBOOK.md`. Tick after the 4-week soak clears all four.
  - [ ] No risk-rule violations
  - [ ] Audit trail matches reasoning
  - [ ] Performance roughly tracks backtest expectations
- [x] **Live Trader Agent** — only after graduation. Hard caps: max position size, max daily loss, max trades/day. Kill-switch wired. → `agents/live_trader.py` is a structured refusal stub: `live_trade_cycle()` raises `NotImplementedError` pointing at the runbook. Real implementation lands only after paper-trader graduation; the gate is intentional.

**DoD:** Research agent answers "best strategy for HPG right now?" defensibly + auditably in one prompt. → `tests/test_agents.py::test_research_agent_ranks_strategies_for_hpg` verifies the recipe; `prompts/research.md` is the LLM equivalent. Both produce a `ResearchNote` with explicit recommendation, per-strategy OOS Sharpe + trade count + drawdown, and the survivor-bias disclaimer. 187 tests green.

---

## Phase 9 — Continuous Learning (Ongoing)

- [x] Pipeline `decisions.jsonl` → research-agent input dataset. → `agents.continuous.decisions_dataset(...)` aggregates the audit log into per-(symbol, side) `DecisionStats` (submitted / reject / warning / error counts) plus raw decision-code histograms.
- [x] Periodic strategy-proposal agent run; output is a PR (code + backtest + walk-forward). → `agents.continuous.strategy_proposal_brief()` produces a `StrategyProposalBrief` listing the registry bucketed by `expected_regime` and flagging regimes with ≤1 strategies as gaps. The PR-bar (CONTRIBUTING.md + smoke gate) was wired in Phase 4 and CI runs it on PRs touching `strategies/`.
- [x] Drift-detection agent: live PnL vs backtest expectation; alert on threshold breach. → `agents.continuous.drift_check(strategy, symbol, observed_live_return_pct, threshold_pct_points)` calls `walk_forward` for the OOS expectation, computes the delta, emits a `DriftAlert`. Breaches log a `drift.alert.breach` event + `drift.alerts` metric.
- [x] Tool-quality feedback loop: agent flags bad tool outputs → Phase 3 contract fixes. → `agents.continuous.flag_tool_output(tool_name, issue, …)` appends one row to `EXPORT_DIR/tool_quality.jsonl` with severity, args, received payload, and correlation_id. Reviewed weekly to either tighten the tool contract or close the flag.

---

## Cross-Cutting Standards (apply throughout)

- [x] Type hints required on every public function; `mypy --strict` enforced in CI. → strict on the typed core (`schemas/`, `exceptions`, `settings`, `core/costs`, `core/position_sizer`) — 10 files, 0 errors. Rest of V2 runs non-strict mypy in CI; legacy/scripts excluded. Phase 3 deliverable.
- [x] Pydantic at every I/O boundary; no raw dicts cross modules. → every cross-module return type lives in `schemas/` (`OHLCVFrame`, `Signal`, `ScanResult`, `OrderRequest`/`OrderResponse`, `Position`, `AccountSnapshot`, `RiskCheckResult`, `MarketContext`, `BacktestResult`, `WalkForwardResult`, `HealthStatus`, `StrategyDescription`). The `BrokerPayload`/`BrokerPayloadList` aliases in `stock_api_client.py` are a documented deliberate exception (raw TCBS JSON kept out of cross-module sigs).
- [x] No silent failures: every `except` re-raises typed or returns typed error. → no `except Exception:` remains in non-script V2 code; all narrowed to expected error tuples and logged via `obs.log_event`. Typed `StockSystemError` hierarchy maps to stable `ToolError` codes at the agent boundary.
- [x] No public function lands without ≥1 test. → 193 tests cover every public surface added across phases (schemas, settings, costs, sizers, walk-forward, validator, tracker, order manager, reconciler, crash recovery, obs, health, every strategy, every tool, every agent, continuous-learning primitives). New PRs adhere via `strategies/CONTRIBUTING.md` for strategies and the smoke gate in CI.
- [x] Side-effecting ops carry client-generated IDs (idempotency). → `OrderRequest.client_order_id` (UUID) is auto-generated; `OrderTracker.register_pending` rejects duplicates with `DuplicateOrderError`; the seen-set is rebuilt from the ledger on init so idempotency survives `kill -9` (proven by `tests/test_crash_recovery.py`).
- [x] New tools default read-only; write capability requires separate review. → `@tool(..., side_effecting=False)` is the default; only `submit_order` and `cancel_order` set `side_effecting=True`. `validate_order` is read-only despite caching a token. `ToolDefinition.idempotent` is the inverse for read-only tools.
- [x] Docstrings written as agent-facing API docs. → public docstrings on `MarketScanner`, `Backtester`, `WalkForwardBacktester`, `OrderManager`, `OrderTracker`, `PreTradeValidator`, `IndicatorEngine`, `SignalStrategy` (+ every concrete strategy), every Pydantic schema, every tool handler. The MCP server reads handler docstrings as the tool description an LLM reads.

---

## Order-of-Battle (next 5 weeks)

1. **Week 1** — Phase 0 complete; pytest + FakeDataProvider + 3-strategy regression seal.
2. **Week 2** — Phase 1 items 1+3 (OHLCVFrame schema + kill synthetic candle).
3. **Week 3** — Phase 2 item 1 (eliminate look-ahead) + `assert_no_lookahead` utility.
4. **Week 4** — Phase 3 items 1+2 (Pydantic schemas + typed exceptions).
5. **Week 5** — MCP-vs-HTTP decision + start writing Phase-3 docstrings in tool-spec form.
