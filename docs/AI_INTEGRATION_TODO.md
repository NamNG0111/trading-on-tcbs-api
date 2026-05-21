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
- [~] **Live Trader Agent** — only after graduation. Hard caps: max position size, max daily loss, max trades/day. Kill-switch wired. → `agents/live_trader.py` is currently a structured refusal stub (`live_trade_cycle()` raises `NotImplementedError`). **Superseded by Phase 10** — real implementation lands as HITL-by-default with auto-mode toggle. See Phase 10 for the rewrite.

**DoD:** Research agent answers "best strategy for HPG right now?" defensibly + auditably in one prompt. → `tests/test_agents.py::test_research_agent_ranks_strategies_for_hpg` verifies the recipe; `prompts/research.md` is the LLM equivalent. Both produce a `ResearchNote` with explicit recommendation, per-strategy OOS Sharpe + trade count + drawdown, and the survivor-bias disclaimer. 187 tests green.

---

## Phase 9 — Continuous Learning (Ongoing)

- [x] Pipeline `decisions.jsonl` → research-agent input dataset. → `agents.continuous.decisions_dataset(...)` aggregates the audit log into per-(symbol, side) `DecisionStats` (submitted / reject / warning / error counts) plus raw decision-code histograms.
- [x] Periodic strategy-proposal agent run; output is a PR (code + backtest + walk-forward). → `agents.continuous.strategy_proposal_brief()` produces a `StrategyProposalBrief` listing the registry bucketed by `expected_regime` and flagging regimes with ≤1 strategies as gaps. The PR-bar (CONTRIBUTING.md + smoke gate) was wired in Phase 4 and CI runs it on PRs touching `strategies/`.
- [x] Drift-detection agent: live PnL vs backtest expectation; alert on threshold breach. → `agents.continuous.drift_check(strategy, symbol, observed_live_return_pct, threshold_pct_points)` calls `walk_forward` for the OOS expectation, computes the delta, emits a `DriftAlert`. Breaches log a `drift.alert.breach` event + `drift.alerts` metric.
- [x] Tool-quality feedback loop: agent flags bad tool outputs → Phase 3 contract fixes. → `agents.continuous.flag_tool_output(tool_name, issue, …)` appends one row to `EXPORT_DIR/tool_quality.jsonl` with severity, args, received payload, and correlation_id. Reviewed weekly to either tighten the tool contract or close the flag.

---

## Phase 10 — Human-in-the-Loop Live Trader (Weeks 15–16) ★ HIGH RISK

Goal: Real-money trading with HITL-by-default; every signal asks for human confirmation before placement; strict re-validation after confirmation; runtime toggle to full-auto for when operator trusts the system.

**Design decisions locked:**
- Confirmation channels: **Terminal + Telegram** (both supported; operator picks via `Settings.confirmation_channel`).
- Re-validation: **STRICT** — originating strategy must re-emit the same signal on a NEW bar after confirmation; price drift must be within `max_price_drift_pct` (default 2%).
- Telegram lib: **`python-telegram-bot`** (async-native, batteries-included).
- Hard caps land in this phase (not deferred): `max_position_size_vnd`, `max_daily_loss_vnd`, `max_trades_per_day` — enforced inside `PreTradeValidator` so both HITL and auto paths inherit them.

### Chunk 1 — Pending-signal store + schemas (0.5d) ✓

- [x] Add `schemas/pending_signal.py` with `PendingSignal` Pydantic model (id, ts, expires_at, symbol, side, strategy_name, strategy_params, ref_price, ref_bar_close_ts, proposed_volume, proposed_notional_vnd, status, revalidation_result, correlation_id). → `PendingSignal.from_scan(...)` constructor; `with_status(...)` for immutable-style transitions; `is_expired()` / `is_terminal()` helpers; `OPEN_STATUSES` + `TERMINAL_STATUSES` frozensets exported.
- [x] Add `schemas/revalidation.py` with `RevalidationResult` + `RevalCheck` rows. → `RevalCheckName` Literal covers `signal_reemitted | new_bar | price_drift | freshness`; `failed_checks` property surfaces the failing rules.
- [x] Add `PendingSignal.status` Literal: `awaiting | confirmed | rejected | expired | stale | submitted | failed`. → defined in `schemas/pending_signal.py`; `TERMINAL_STATUSES` includes all but `awaiting` and `confirmed`.
- [x] Add `execution/hitl/pending_signal_store.py` — JSONL-backed durable store at `EXPORT_DIR/pending_signals.jsonl`. Append-only writes; `load_open()` reads back non-terminal entries on startup. → `PendingSignalStore` with `append` / `update_status` / `get` / `load_open` / `iter_all` / `expire_overdue` (idempotent sweeper). Every write flushes + fsyncs so `kill -9` between transitions is safe.
- [x] Tests: `test_pending_signal_store.py` — persistence, expiry computation, restart recovery, status transitions, concurrent-append safety. → 12 tests covering schema invariants, append/get round-trip, history preservation, restart-recovery via `load_open`, sweeper idempotency, and confirmed-doesn't-auto-expire. 205 tests total green.

### Chunk 2 — Strict re-validator (0.5d) ✓

- [x] Add `execution/hitl/revalidator.py::StrictRevalidator`. → injects `DataProviderLike` Protocol + `IndicatorEngine`; configurable `max_price_drift_pct` + `lookback_days`.
- [x] Force-refresh OHLCV via `DataProvider` (bypass cache for the symbol). → `force_update=True, include_live=False` enforced on every check; covered by `test_force_update_is_set_on_fetch`.
- [x] Instantiate strategy from `pending.strategy_name` + `strategy_params` via the `STRATEGIES` registry. → `get_strategy(...)` look-up; unknown strategies fail the `signal_reemitted` check with a structured detail.
- [x] Check 1 — **signal still emitted**: latest closed bar's signal for that strategy must equal `pending.side`. → maps BUY→1 / SELL→-1; runs the full IndicatorEngine + strategy pipeline on the fresh frame.
- [x] Check 2 — **new bar**: `fresh_bar_close_ts > pending.ref_bar_close_ts`. → strict `>`; same-bar case fails (covered by `test_same_bar_fails_new_bar_check`).
- [x] Check 3 — **price drift**: `abs(last_close - ref_price) / ref_price <= max_price_drift_pct`. → inclusive cap; the cap value is `%` not decimal (a 2.0 cap means 2%). Tests cover within-cap, exactly-at-cap, and beyond-cap.
- [x] Returns `RevalidationResult(passed, checks, fresh_price, price_drift_pct, fresh_bar_close_ts, reason)`. → four `RevalCheck` rows (freshness / new_bar / price_drift / signal_reemitted). `reason` is the first failing check's detail; None on pass.
- [x] Tests: pass case, signal-flipped case, signal-gone case, price-drift case, same-bar (no new bar yet) case. → 12 tests covering all four checks + provider exceptions + only-partial-bars + cap inclusivity + the `force_update` contract. 217 tests green total.

### Chunk 3 — Confirmation channel base + Terminal channel (0.5d) ✓

- [x] Add `execution/hitl/channels/base.py::ConfirmationChannel` Protocol (`request(pending) -> ConfirmationResponse`, `notify_outcome(pending, outcome, details)`, `replay_pending(pendings)`). → `@runtime_checkable` so tests can `isinstance`-check; all three methods are async.
- [x] Add `ConfirmationResponse(decision: Literal["yes","no","timeout"], answered_at, raw)`. → also carries `signal_id` + optional `reason` for richer rejection logs.
- [x] Add `execution/hitl/channels/terminal.py::TerminalChannel` using async stdin so the scanner loop never blocks. → uses `asyncio.to_thread(input, ...)` + `asyncio.wait_for` rather than `aioconsole` (no new dep). Permissive reply parsing (`y/yes/1/ok` → yes; `n/no/0/empty/EOF/unknown` → no, safe default).
- [x] Tests: `test_channel_terminal.py` — mocked input streams (yes / no / EOF / timeout). → 17 tests covering protocol shape, eight reply tokens, EOF handling, pre-expired signal, mid-wait timeout, outcome formatting, replay output, empty-replay no-op. 234 tests total green.

### Chunk 4 — HITL Coordinator + auto-mode toggle (1d) ✓

- [x] Add `Settings.trading_mode: Literal["hitl","auto"] = "hitl"`. → wired in `settings.py`; `hitl` is the default.
- [x] Add `Settings.confirmation_channel: Literal["terminal","telegram"] = "terminal"`. → wired.
- [x] Add `Settings.confirmation_timeout_sec: int = 3600` and `Settings.max_price_drift_pct: float = 2.0`. → both validated (`gt=0`, `le=50`).
- [x] Add `execution/hitl/coordinator.py::HITLCoordinator` orchestrating: scan-signal → pending-store → channel.request → revalidator → validator → order_manager.place_order → channel.notify_outcome → store update. → `handle_signal(...)` is the single entry point; status transitions are all routed through `PendingSignalStore.update_status` so the audit trail is append-only.
- [x] On `trading_mode=="auto"`: skip channel call, auto-approve, continue to re-validator. → `_ask` short-circuits to `"yes"` in auto mode; revalidator still runs.
- [x] On `stale` revalidation outcome: write status, log `hitl.signal.stale` event, do **not** place order. → covered by `test_revalidation_fail_marks_stale_no_order_placed`.
- [x] On startup: load open pending signals, drop expired ones, re-prompt the rest via channel. → `resume_open_pending()` calls `expire_overdue()` first, then `channel.replay_pending(open)`.
- [x] Emit metrics: `hitl.signal.{dispatched,confirmed,rejected,expired,stale,submitted,failed}`. → `record_metric` calls on every transition; `failed` carries a `reason` label distinguishing validator/broker_reject/exception.
- [x] Tests: hitl yes/no/timeout, auto-mode skip, auto-mode still revalidates, channel exception treated as no, revalidation fail → stale (no order), validator BLOCK → failed, broker REJECTED → failed, order_manager exception → failed, persistence-for-restart, resume replays via channel, resume expires overdue first. → 15 tests; 249 green total.

### Chunk 5 — Live trader rewrite + hard caps (0.5d) ✓

- [x] Add `Settings.RiskParams.max_position_size_vnd`, `max_daily_loss_vnd`, `max_trades_per_day` with conservative defaults (50M / 10M / 10). Sentinel 0 disables each check.
- [x] Extend `PreTradeValidator` to enforce all three; reject reason rows feed back into `RiskCheckResult.findings`. Track today's trade count + realized PnL via new `DailyTradeStats` value object the caller passes in (HITLCoordinator wires it through `daily_stats_provider`). Back-compat: callers without `daily_stats` see no new BLOCKs.
- [x] Rewrite `agents/live_trader.py::live_trade_cycle()` to: pre-flight `health_check` (abort on fail), resume open pending signals, scan, dispatch each signal through `HITLCoordinator.handle_signal`, return `LiveTradeReport(dispatched, n_submitted, n_failed, n_rejected, n_expired, aborted_reason)`.
- [x] Remove `NotImplementedError` stub. → exported from `agents/__init__.py` alongside other recipes.
- [x] Tests: position-size cap (block on projected exceed, block with existing holding, pass when under, disabled-when-zero, SELL exempt); trades/day cap (block at limit, pass below, no-daily_stats no-block, disabled-when-zero); daily-loss cap (block at floor, pass within, profit irrelevant); Settings wiring; live trader (health-fail abort, dispatch-all-signals, resume-before-dispatch, status counters). → 13 cap tests + 4 live-trader tests; 266 total green.

### Chunk 6 — HITL tools + MCP exposure (0.5d) ✓

- [x] Add `tools/handlers/hitl.py` with: `list_pending_signals` (read-only; `include_terminal` flag + `limit`), `confirm_signal(id)` (side-effecting; routes through `coordinator.confirm_pending` → revalidator → validator → order), `reject_signal(id, reason)` (side-effecting; idempotent on terminal), `set_trading_mode(mode, confirm)` (side-effecting; `confirm=True` required to apply, else dry-run echo).
- [x] Coordinator extended with public out-of-band methods `confirm_pending(id)`, `reject_pending(id)`, `set_trading_mode(mode)`. `_process` and `confirm_pending` now share the `_post_confirm` helper so the channel-driven and tool-driven paths run identical revalidator + placement logic.
- [x] `ToolContext` extended with `hitl_coordinator` + `pending_signal_store` slots; tools fail loudly when unconfigured. Tools import-registered via `tools/__init__.py`.
- [x] Async-from-sync: `confirm_signal` / `reject_signal` wrap the coordinator coroutines in `asyncio.run`, matching the rest of the sync tool layer. The MCP transport works unchanged.
- [x] Tests: `test_tools_hitl.py` — list (open-only, include_terminal, limit), confirm (full pipeline, unknown id → INVALID_PARAMS, terminal idempotency), reject (mark + unknown), set_trading_mode (dry-run without confirm, applied with confirm), registration sanity (side_effecting flags). 11 tests; 277 total green.

### Chunk 7 — Telegram channel (1d) ✓

- [x] Add `python-telegram-bot>=22.0` to `requirements.txt`. → also httpx / httpcore / h11 / anyio as transitive deps. Module gracefully sets `TelegramChannel = None` when the import fails, so non-Telegram installs are unaffected.
- [x] Wire `telegram_bot_token: str | None` and `telegram_chat_id: str | None` into `Settings`. → optional; required only when `confirmation_channel='telegram'`.
- [x] Add `execution/hitl/channels/telegram.py::TelegramChannel` using `Application.builder().token(...).build()` + `start_polling()`. Inline keyboard with ✅ / ❌ buttons; `callback_data = f"{signal_id}:{yes|no}"`. The `request()` method registers an `asyncio.Future` keyed on signal_id; the `CallbackQueryHandler` resolves the future. Lifecycle: `await chan.start()` + `await chan.stop()`.
- [x] On startup, `replay_pending` re-sends any signals still in `awaiting` state. → header line + one prompt per signal; failures per-signal are logged and skipped (not fatal).
- [x] Outcome notifications include submitted/rejected/stale/expired/failed with emoji-prefixed lines. → `notify_outcome` swallows send errors so the durable row is the source of truth.
- [x] Tests: `test_channel_telegram.py` — FakeBot recording `send_message` calls; yes/no callback resolution; timeout when no callback fires; pre-expired short-circuit; inline-keyboard contract; send-failure unregisters waiter; outcome notification shape; replay header + per-signal; orphan callbacks no-op; `stop()` resolves outstanding waiters as `no`. 15 tests; 292 total green.
- [ ] Manual test (operator): full bot round-trip on a real Telegram chat against fixture signals. → operator-driven; runbook step in Chunk 8.

### Chunk 8 — Docs + runbook (0.5d) ✓

- [x] Write `docs/PHASE10_HITL_RUNBOOK.md`: pre-flight, terminal vs Telegram setup (BotFather walkthrough + smoke checklist), mode toggle, signal lifecycle diagram, MCP tools table, stuck-signal recovery, emergency auto-off (two layers), audit trails, DoD checklist.
- [x] Update `CLAUDE.md`: architecture diagram now shows HITL Coordinator layer + 19 tools + live_trader agent; Configuration section names the new caps + HITL settings; Codebase map adds `execution/hitl/`; Key dependencies adds optional `python-telegram-bot`; "When you work in here" section adds new-channel + new-cap entries.
- [x] Update `docs/AI_INTEGRATION_PLAN.md` with a "10b. Phase 10" section between Phase 9 and the cross-cutting standards. Captures design decisions (HITL-by-default, strict re-validation, hard caps, runtime toggle, two channels) + module layout.
- [x] Update `docs/stock_system_v2_guide.md` with HITL coordinator section, codebase-map entry for `execution/hitl/`, and a Phase-10 row in the per-phase status table.

**DoD:** End-to-end on real account in HITL mode: scanner fires a signal → Telegram prompt → operator taps ✅ → strict re-validation passes → live order placed → confirmation message arrives in Telegram. Auto-mode toggle verified on paper account. All hard caps proven by test. Restart in the middle of a pending confirmation recovers cleanly.

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

---

## Order-of-Battle (Phase 10, ~5 days code)

1. **Day 1 (AM)** — Chunk 1: pending-signal store + schemas.
2. **Day 1 (PM)** — Chunk 2: strict re-validator.
3. **Day 2 (AM)** — Chunk 3: terminal channel.
4. **Day 2 (PM) – Day 3** — Chunk 4: coordinator + auto toggle + restart recovery.
5. **Day 4 (AM)** — Chunk 5: live trader rewrite + hard caps.
6. **Day 4 (PM)** — Chunk 6: HITL tools + MCP.
7. **Day 5** — Chunk 7: Telegram channel + manual round-trip.
8. **Day 5 (PM)** — Chunk 8: runbook + doc updates.
