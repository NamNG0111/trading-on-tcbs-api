# CLAUDE.md

Guidance for Claude Code (claude.ai/code) working in this repo.

## Project overview

Algorithmic trading system integrated with the Vietnamese TCBS brokerage
API. Originally a script-shaped backtester + scanner; the V2 package
(`trading_on_tcbs_api/stock_system_v2/`) has been transformed across nine
phases into an **agent-callable toolbelt**: typed schemas, Pydantic
contracts, structured logs, idempotent execution, an MCP server, and
agent recipes that drive everything end-to-end.

If you've stepped away for a while: the codebase you remember was Python
scripts. What's there now is a tool layer with 15 typed tools, four
agent recipes (research / scanner / risk / paper trader), and a
production-grade safety stack around order placement.

**The integration plan + checklist live in `docs/AI_INTEGRATION_PLAN.md`
and `docs/AI_INTEGRATION_TODO.md` — read those for the per-phase
rationale.**

## Common commands

```bash
# Tests (193+ green; full suite, network-free, ~3s)
make test                          # or: python -m pytest tests/

# Lint + typecheck + tests bundle
make ci

# Strategy smoke gates (Phase-4 CI gate; runs on PRs touching strategies/)
make strategy-smoke NAME=rsi
make strategy-smoke-all

# Regenerate test fixtures + expected-signal CSVs
make fixtures

# Daily live market scan (requires creds)
python trading_on_tcbs_api/stock_system_v2/scripts/scan_market.py

# Backtest entry points
python trading_on_tcbs_api/stock_system_v2/scripts/backtest_market.py
python trading_on_tcbs_api/stock_system_v2/scripts/backtest_top3_phase2_rebaseline.py

# AutoTrader (paper-trading loop; safe-mode default)
EXECUTION_DISABLED=true python trading_on_tcbs_api/stock_system_v2/main.py

# MCP server — exposes every tool over stdio (requires `pip install mcp`)
python -m trading_on_tcbs_api.stock_system_v2.tools.mcp_server

# Setup creds (first-time)
python trading_on_tcbs_api/runners/setup_credentials.py
```

## Architecture (V2)

V2 is the production system. Legacy code (`stock_strategy/`,
`futures_strategy/`, `simple_wow/`, `indicators/`, top-level `core/` and
`ws_clients/`) is in maintenance mode — patch in place but don't extend.

### Layered design

```
   Agents (Phase 8/9): research, scanner, risk, paper_trader, continuous-learning
        │  drives via tools.invoke(name, args) only — zero internal imports
        ▼
   Tools (Phase 7):   15 registered tools + ToolResponse / ToolError envelope
        │  thin wrappers over the production primitives below
        ▼
   Production V2:     scanner / backtester / order_manager / account / data_provider
        │  Pydantic schemas, typed exceptions, structured logs, correlation IDs
        ▼
   TCBS / vnstock     external broker (TCBS REST) + market data (vnstock-KBS)
```

Read it bottom-up if you want to understand the safety story; top-down
if you want to understand how an agent uses it.

### Data flow (a daily scan, end to end)

1. `data_ingest/data_provider.py` — fetches historical OHLCV from
   vnstock (KBS source), validates against the `OHLCVFrame` schema,
   caches to CSV. Today's still-forming bar is marked `is_partial=True`
   with `volume=NaN` so volume strategies don't silently misfire.
   Cross-source reconciler compares vnstock close vs TCBS `refPrice`.
2. `core/indicator_engine.py` — single pass through pandas-ta producing
   SMA / EMA / RSI / MACD / ROC / VOL_SMA columns. Audited for
   look-ahead; closed-bars-only (the partial bar is dropped before
   computation).
3. `core/market_scanner.py` — iterates symbols × strategies, returns
   today's signals as typed `ScanResult` objects. Uses each strategy's
   `extract_signal_context(row)` accessor to attach typed context.
4. `execution/pre_trade_validator.py` — five rules (universe, lot size,
   price band, notional, cash/cover) emit a `RiskCheckResult` token
   bound to the order via SHA-256 hash, 60-second TTL.
5. `execution/order_manager.py` — only places orders when the kill-switch
   is off, the token is fresh + hash-matching (live mode), and the
   tracker hasn't seen the `client_order_id` before. Real TCBS path is
   wired but reachable only with explicit live-mode construction.
6. `execution/order_tracker.py` — append-only ledger; `register_pending`
   writes a row before the wire call so a crash between submit and log
   leaves a recoverable breadcrumb. `recover_open_orders()` reads it
   back on startup.
7. `obs/` — every step emits structured JSON with the active
   correlation id; metrics go to `v2.metrics` logger; order decisions
   append to `EXPORT_DIR/decisions.jsonl`.

### Strategy framework (Phase 4)

Every strategy lives in `stock_system_v2/strategies/<name>_strategy.py`.
The base class `SignalStrategy` is concrete now — subclasses override
`_compute_signals(df)`, not `generate_signals`, and the base masks any
non-zero signal in `[0, min_bars_required)`.

Each strategy declares:

- A nested `Params(StrategyParams)` Pydantic model (frozen,
  `extra='forbid'`). Bad params raise at construction.
- `min_bars_required` — set in `__init__` after `super().__init__`.
- `describe() -> StrategyDescription` — agent-readable rationale,
  expected regime, known failure modes, indicators, params schema.
- Optional `context_columns` for `extract_signal_context()`.

`STRATEGIES` registry in `strategies/registry.py` is the single source
of truth: `get_strategy(name)` raises `KeyError` listing available ids.
`CombinedStrategy` precedence is codified — sell wins on conflict, AND =
unanimous, OR = any.

Adding a strategy = `strategies/CONTRIBUTING.md` checklist + a passing
`make strategy-smoke NAME=<id>`. CI runs the smoke gates on any PR
touching `strategies/`.

### Schemas package (Phase 3)

`schemas/` is the cross-module contract. Every public return type is a
Pydantic model:

| Module | Models |
|--------|--------|
| `ohlcv.py` | `OHLCVFrame`, `validate_ohlcv`, `closed_bars`, `OHLCVSchemaError` |
| `signals.py` | `Signal`, `SignalAction`, `ScanResult` |
| `orders.py` | `OrderRequest`, `OrderResponse`, `OrderSide`, `OrderType`, `OrderStatus`, `Position`, `AccountSnapshot` |
| `risk.py` | `RiskCheckResult`, `RiskCheckFinding`, `CheckSeverity`, `MarketContext` |
| `backtest.py` | `BacktestResult`, `WalkForwardResult`, `WalkForwardWindow`, `to_backtest_results` |
| `health.py` | `HealthStatus`, `HealthCheck` |
| `strategy_meta.py` | `StrategyParams`, `StrategyDescription` |

`exceptions.py` is the typed error hierarchy: `StockSystemError` →
`DataFetchError` (+ `StaleCacheError`, `InsufficientHistoryError`),
`InvalidParameterError`, `AuthExpiredError`, `OrderRejectedError` (+
`DuplicateOrderError`), `RiskLimitViolatedError`, `PositionDriftError`.

### Settings (Phase 3)

Replaces the old global `from … import config` pattern. `Settings.load()`
is a frozen Pydantic value object that reads `config/local_config.json`
+ `EXECUTION_DISABLED` env. Per-call overrides via
`settings.model_copy(update={...})`. The legacy `config.py` is now a
back-compat shim sourced from `Settings.load()` so existing imports
keep resolving.

### Observability (Phase 6)

`stock_system_v2/obs/` is the observability primitive box:

- `obs/logger.py` — `JSONFormatter`; `get_logger("module")` returns a
  configured `v2.<module>` logger; `log_event(logger, "stable.event",
  **fields)` is the call shape.
- `obs/correlation.py` — `with_correlation(prefix="cycle")` context
  manager; the formatter auto-attaches the active id.
- `obs/metrics.py` — `record_metric(name, value, **labels)` and
  `timed(name)`; metrics are JSON log events on `v2.metrics`.
- `obs/decisions.py` — `write_decision(payload)` appends to
  `EXPORT_DIR/decisions.jsonl`.

The reserved-key kwargs (`message`, `args`, …) are auto-renamed with
`field_` prefix so callers don't have to remember the stdlib
`LogRecord` namespace.

### Tool layer (Phase 7)

`tools/` is the agent-callable surface. ADR-003 picked MCP as canonical
transport; handlers stay pure Python so tests + smoke runs don't need
the SDK.

- `tools/registry.py` — `@tool(name, input_model, output_model,
  side_effecting=…)` decorator + `invoke(name, args)` dispatcher.
  Typed `StockSystemError` → stable `ToolError` codes.
- `tools/response.py` — `ToolResponse[T]` envelope (`correlation_id`,
  `data_freshness_seconds`); `ToolError(code, message, retriable, details)`.
- `tools/context.py` — `ToolContext` value object; `set_context(ctx)`
  installs a process-wide instance (composition root).
- `tools/mcp_server.py` — lazy MCP imports; `python -m
  …tools.mcp_server` exposes every tool over stdio.

15 tools registered:

| Tool | Side-effecting? |
|------|---|
| `list_symbols`, `list_strategies`, `get_history`, `get_quote`, `compute_indicators` | no |
| `scan_market`, `run_backtest`, `walk_forward` | no |
| `get_account`, `get_positions`, `get_audit_log`, `health_check` | no |
| `validate_order` | no (caches token) |
| `submit_order`, `cancel_order` | yes |

### Agent layer (Phases 8 + 9)

`agents/` has both a Python recipe and an LLM system prompt for each
agent. Recipes drive `tools.invoke(...)` only — no internal V2 imports
inside the workflow body.

| Agent | Recipe | Prompt |
|---|---|---|
| Research | `research_strategy_for_symbol(symbol, …) → ResearchNote` | `agents/prompts/research.md` |
| Scanner | `daily_scan(...) → ScannerReport` | `agents/prompts/scanner.md` |
| Risk | `evaluate_proposed_order(req) → RiskOpinion` | `agents/prompts/risk.md` |
| Paper Trader | `paper_trade_cycle(...) → PaperTradeReport` | `agents/prompts/paper_trader.md` |
| Live Trader | `live_trade_cycle(...)` — refusal stub | (gated until graduation) |

Phase-9 continuous-learning primitives in `agents/continuous.py`:
`decisions_dataset(...)` aggregates the audit log; `strategy_proposal_brief()`
flags coverage gaps for a strategy-proposal PR; `drift_check(...)`
compares live PnL against walk-forward expectation; `flag_tool_output(...)`
appends to `EXPORT_DIR/tool_quality.jsonl` for the operator's weekly
review.

## Configuration

- `trading_on_tcbs_api/config/credentials.yaml` — TCBS API key + account
  ids. Copy from `credentials.yaml.example`.
- `trading_on_tcbs_api/config/local_config.json` — machine-specific
  override of `DATA_DIR` + `EXPORT_DIR`. Not committed; create per
  machine. On the dev box both paths point at Google Drive so cached
  CSVs are accessible from anywhere.
- `Settings.load()` reads both at process start. `EXECUTION_DISABLED=true`
  in the environment hard-blocks every order regardless of safe-mode.

Risk caps default to `max_capital_per_trade_pct=0.10`,
`stop_loss_pct=0.05`, `take_profit_pct=0.10`, `max_open_positions=5`.

## Codebase map

```
trading_on_tcbs_api/stock_system_v2/        # ★ production system
├── main.py                                 # composition root → AutoTrader
├── config.py                               # back-compat shim over Settings
├── settings.py                             # Pydantic Settings.load()
├── exceptions.py                           # typed StockSystemError hierarchy
│
├── schemas/                                # Pydantic cross-module contracts
│   ├── ohlcv.py, signals.py, orders.py, risk.py
│   ├── backtest.py, health.py, strategy_meta.py
│   └── __init__.py                         # re-exports everything
│
├── obs/                                    # structured logging + metrics + audit
│   ├── logger.py                           # JSONFormatter, log_event
│   ├── correlation.py                      # with_correlation contextvar
│   ├── metrics.py                          # record_metric, timed
│   └── decisions.py                        # write_decision → decisions.jsonl
│
├── auth/auth.py                            # JWT load/save + OTP renewal
│
├── data_ingest/
│   ├── data_provider.py                    # vnstock fetch + cache + live merge
│   ├── reconciler.py                       # vnstock vs TCBS refPrice check
│   └── symbol_metadata.py                  # per-symbol price-scale table
│
├── core/
│   ├── indicator_engine.py                 # pandas-ta single-pass; lookahead-audited
│   ├── market_scanner.py                   # DI: data_provider+engine+strategies
│   ├── backtester.py                       # native + fixed-hold; costs-aware
│   ├── walk_forward.py                     # rolling train/test windows; OOS-only
│   ├── auto_trader.py                      # canonical execution path (ADR-002)
│   ├── costs.py                            # TransactionCosts (TCBS defaults)
│   ├── position_sizer.py                   # FixedFraction / EqualWeight / VolTargeted
│   ├── health.py                           # health_check() orchestrator
│   ├── stock_api_client.py                 # TCBS REST client
│   └── backtest_result.py                  # back-compat shim → schemas.backtest
│
├── strategies/                             # Phase-4 framework
│   ├── strategy.py                         # SignalStrategy base (concrete + warmup mask)
│   ├── registry.py                         # STRATEGIES dict + get_strategy
│   ├── ma_strategy.py, rsi_strategy.py, rsi_divergence_strategy.py
│   ├── volume_strategy.py, dip_buy_strategy.py
│   ├── cumulative_drop_strategy.py, intraday_dip_strategy.py
│   ├── combined_strategy.py                # AND/OR + sell-wins precedence
│   └── CONTRIBUTING.md                     # PR bar (code/tests/smoke/docs)
│
├── execution/
│   ├── order_manager.py                    # kill-switch + token gate + tracker
│   ├── order_tracker.py                    # idempotent ledger + crash recovery
│   ├── pre_trade_validator.py              # 5-rule validator + RiskCheckResult
│   └── trade_manager.py                    # DEPRECATED (ADR-002); DeprecationWarning on import
│
├── finance/
│   ├── account_manager.py                  # cash + positions; sync_from_api with drift gate
│   ├── reconciler.py                       # assert_no_drift; PositionDriftError
│   └── performance_analyzer.py             # PnL / drawdown / win-rate
│
├── tools/                                  # ★ Phase-7 tool layer
│   ├── registry.py                         # @tool decorator + invoke()
│   ├── response.py                         # ToolResponse + ToolError
│   ├── context.py                          # ToolContext value object
│   ├── mcp_server.py                       # MCP stdio entry point
│   └── handlers/
│       ├── data.py                         # list_symbols, get_history, get_quote, compute_indicators
│       ├── strategies.py                   # list_strategies
│       ├── scanner.py                      # scan_market
│       ├── backtest.py                     # run_backtest, walk_forward
│       ├── account.py                      # get_account, get_positions, get_audit_log
│       ├── health.py                       # health_check
│       └── orders.py                       # validate_order, submit_order, cancel_order
│
├── agents/                                 # ★ Phase-8 + Phase-9 agents
│   ├── research.py                         # research_strategy_for_symbol → ResearchNote
│   ├── scanner.py                          # daily_scan → ScannerReport
│   ├── risk.py                             # evaluate_proposed_order → RiskOpinion
│   ├── paper_trader.py                     # paper_trade_cycle → PaperTradeReport
│   ├── live_trader.py                      # refusal stub until graduation
│   ├── continuous.py                       # decisions_dataset, strategy_proposal_brief, drift_check, flag_tool_output
│   └── prompts/                            # LLM system prompts for each agent
│
└── scripts/                                # operator-facing CLIs
    ├── scan_market.py                      # ★ daily live signal scan
    ├── backtest_market.py                  # ★ full-universe backtest
    ├── backtest_top3_phase2_rebaseline.py  # Phase-2 rebaseline (cost delta proof)
    ├── strategy_smoke.py                   # invoked by `make strategy-smoke`
    └── …probes/verify scripts

tests/                                      # 193+ tests, network-free
├── conftest.py                             # ohlcv_factory fixture
├── fakes/                                  # FakeStockApiClient, FakeDataProvider
├── fixtures/                               # HPG/TCB/FPT 500-bar CSVs + expected signals
├── strategies/                             # regression seal + no-lookahead per strategy
├── utils/lookahead.py                      # assert_no_lookahead utility
├── test_obs.py, test_health.py             # Phase-6
├── test_pre_trade_validator.py, test_order_manager.py, test_order_tracker.py,
│   test_position_reconciler.py, test_crash_recovery.py    # Phase-5
├── test_walk_forward.py, test_backtest_result.py, test_costs.py    # Phase-2
├── test_settings.py, test_schemas.py, test_exceptions.py            # Phase-3
├── test_tools_smoke.py                     # Phase-7 end-to-end via invoke()
├── test_agents.py                          # Phase-8 agent recipes
└── test_continuous.py                      # Phase-9 primitives

docs/
├── AI_INTEGRATION_PLAN.md                  # ★ master plan (read this first)
├── AI_INTEGRATION_TODO.md                  # ★ checklist with per-item status
├── ADR-001-data-source.md                  # vnstock-only vs both+reconciler (Option B)
├── ADR-002-execution-path.md               # AutoTrader canonical, TradeManager deprecated
├── ADR-003-tool-protocol.md                # MCP picked over HTTP
├── PHASE2_TOP3_REBASELINE.md               # cost-impact rebaseline report
├── PHASE5_SOAK_RUNBOOK.md                  # operator runbook for paper soak + first live trade
├── PHASE8_PAPER_TRADER_RUNBOOK.md          # operator runbook for 4-week paper-trader soak
└── …existing playbooks/glossaries
```

## Per-phase landing notes

The full per-task status is in `docs/AI_INTEGRATION_TODO.md`. Quick map:

| Phase | Theme | Status |
|---|---|---|
| 0 | Test harness foundation | done; pytest + CI + 56-test seal |
| 1 | Data correctness | done; OHLCVFrame + reconciler + partial-bar fix |
| 2 | Backtesting rigor | done; costs + sizers + walk-forward + survivor-bias disclaimer |
| 3 | Public-API contracts | done; schemas + exceptions + DI + Settings + strict-mypy core |
| 4 | Strategy framework v2 | done; Params + warmup mask + describe + registry + CONTRIBUTING + smoke CI |
| 5 | Execution safety | code-side done; **2-week paper soak + first live trade are operator-driven** (see PHASE5_SOAK_RUNBOOK.md) |
| 6 | Observability | done; structured logs + correlation + metrics + decisions.jsonl + health_check |
| 7 | Tool layer | done; 15 MCP-ready tools + handlers + smoke test |
| 8 | Agent integration | code-side done; **4-week paper-trader soak is operator-driven** (see PHASE8_PAPER_TRADER_RUNBOOK.md) |
| 9 | Continuous learning | done; decisions dataset + proposal brief + drift check + tool-quality flagging |

Two operator-driven gates remain (the paper soaks). Everything that
needs to compile and pass tests does.

## Cross-cutting standards (apply throughout)

- **Type hints on every public function.** `mypy --strict` passes on
  the typed core (schemas, exceptions, settings, costs, position_sizer).
  Rest of V2 has 97 known issues that Phase-6/7 rewrites cleared up
  the surfaces that mattered.
- **Pydantic at every I/O boundary.** No raw dicts cross modules.
- **No silent failures.** Every `except` re-raises a typed
  `StockSystemError` subclass or returns a typed object. No bare
  `except Exception:` in non-script V2 code (intentional `print()`
  remains in operator-UX-only paths: scan results table, OTP prompts,
  sub-account selection).
- **Idempotency by default.** Side-effecting ops carry
  client-generated `client_order_id`s; the tracker rejects duplicates
  and survives `kill -9`.
- **Read-only first.** New tools default to read-only;
  `side_effecting=True` is a deliberate flag.
- **Docstrings as tool specs.** Public docstrings are what an LLM
  reads — write them like API docs, not internal commentary.

## When you (Claude) work in here

- New strategy → `strategies/CONTRIBUTING.md` checklist; CI runs
  `make strategy-smoke-all` on any PR touching `strategies/`.
- New indicator → extend `core/indicator_engine.py`; the audit table
  in the engine class docstring documents the lookback window.
- New tool → put a handler in `tools/handlers/<group>.py` decorated
  with `@tool(...)`; MCP picks it up automatically.
- New agent recipe → `agents/<name>.py` driving `tools.invoke(...)`
  only. Add an `agents/prompts/<name>.md` for the LLM equivalent.
- API issue → `auth/auth.py` (token) → `core/stock_api_client.py`
  (REST) → `docs/tcbs_openapi.json` for the spec.
- Anything in `stock_strategy/`, `futures_strategy/`, `simple_wow/`,
  `indicators/`, top-level `core/`, `ws_clients/`, `runners/`,
  `utils/`, `logger_utils/` is **legacy** — patch only.

## Key dependencies

- `vnstock` — historical OHLCV (KBS source)
- `pandas-ta` — vectorized indicators (V2 standard; not TA-Lib)
- `pydantic` v2 — every cross-module contract; `pydantic.mypy` plugin wired
- `aiohttp`, `requests` — async + sync HTTP to TCBS
- `mcp` (optional) — only needed for the MCP server entry point;
  tests + handlers don't import it
