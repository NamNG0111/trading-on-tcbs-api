
# TCBS Automated Trading System - Final Walkthrough

## 1. System Overview
We have built a complete **Automated Trading System** for the TCBS platform. It covers the entire lifecycle of algorithmic trading:
1.  **Market Data**: Fetches historical data (vnstock) and real-time prices (TCBS).
2.  **Analysis**: Generating signals using MA, RSI, and Volume strategies.
3.  **Execution**: Placing orders via TCBS API (with Safe Mode).
4.  **Financials**: Tracking Cash, Positions, and Buying Power.
5.  **Analytics**: Calculating Realized P&L and Win Rates.

## 2. Key Components

### A. The "Brain": `auto_trader.py`
This is the main entry point. It runs the entire loop:
```bash
python3 -m trading_on_tcbs_api.stock_system_v2.core.auto_trader
```
*   **Startup**: Attempts to sync with your **Real TCBS Account**.
    *   *If Permission Denied*: Falls back to **Mock Mode** (100M VND Virtual Cash).
*   **Scan**: Checks `config.SYMBOLS` (e.g., HPG, VIC, VNM) for signals.
*   **Execute**: Places orders (Safe Mode by default requires confirmation).
*   **Log**: Saves every trade to `data/ledger.csv`.

### B. The "Eyes": `scan_market.py`
Use this for a quick manual check of the market without trading.
```bash
python3 -m trading_on_tcbs_api.stock_system_v2.scripts.scan_market
```

### C. The "Scoreboard": `analyze_performance.py`
View your trading performance (P&L, Win Rate) based on your ledger.
```bash
python3 -m trading_on_tcbs_api.stock_system_v2.scripts.analyze_performance
```
*   Uses **FIFO** matching logic to calculate realized gains/losses.
*   Reports Win Rate, Profit Factor, and Drawdown.

### D. The "Probe": `fetch_real_assets.py`
A diagnostic tool to check your connection to real TCBS holdings.
```bash
python3 -m trading_on_tcbs_api.stock_system_v2.scripts.fetch_real_assets
```
*   Configured to assume your specific Account IDs (`0001262203` Normal, `0001262204` Margin).
*   *Note*: Currently returns Empty Data due to Token Scope limitations.

---

## 3. Configuration & Security

*   **Credentials**: Stored in `config/credentials.yaml`. We updated this with your correct Sub-Account IDs found via the Profile endpoint.
*   **Token**: `token.json` (Auto-renewing).
*   **Safe Mode**: `config.py` sets strict limits (max order value, prohibited stocks).

## 4. How to Use

1.  **Start the Bot**: Run `auto_trader.py`.
2.  **Monitor**: Watch the logs. It will print "[Account] Sync Warning" if using Mock Mode.
3.  **Trade**: If a signal is found, it will ask for confirmation (in Safe Mode) or trade automatically (if disabled).
4.  **Review**: Run `analyze_performance.py` after a few days of trading to see your P&L.

## 5. Future Step: Real Money
To switch from Mock to Real Money fully:
1.  Obtain a **TCBS Token with `account.view` scope** (contact TCBS or check Wealth API docs).
2.  Once the token allows reading assets, `auto_trader.py` will automatically switch to **Real Mode** at startup.
3.  No code changes needed!

**Enjoy your trading robot!**

---

# V2 Internals Reference

This section was moved out of `CLAUDE.md` to keep the project memory file
concise. It captures the architectural detail that's useful when you need to
*reason about* V2, but isn't needed at session-start.

## Data flow (a daily scan, end to end)

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

## Strategy framework (Phase 4)

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

## Schemas package (Phase 3)

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

## Settings (Phase 3)

Replaces the old global `from … import config` pattern. `Settings.load()`
is a frozen Pydantic value object that reads `config/local_config.json`
+ `EXECUTION_DISABLED` env. Per-call overrides via
`settings.model_copy(update={...})`. The legacy `config.py` is now a
back-compat shim sourced from `Settings.load()` so existing imports
keep resolving.

## Observability (Phase 6)

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

## Tool layer (Phase 7)

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

## Agent layer (Phases 8 + 9)

`agents/` has both a Python recipe and an LLM system prompt for each
agent. Recipes drive `tools.invoke(...)` only — no internal V2 imports
inside the workflow body.

| Agent | Recipe | Prompt |
|---|---|---|
| Research | `research_strategy_for_symbol(symbol, …) → ResearchNote` | `agents/prompts/research.md` |
| Scanner | `daily_scan(...) → ScannerReport` | `agents/prompts/scanner.md` |
| Risk | `evaluate_proposed_order(req) → RiskOpinion` | `agents/prompts/risk.md` |
| Paper Trader | `paper_trade_cycle(...) → PaperTradeReport` | `agents/prompts/paper_trader.md` |
| Live Trader (Phase 10) | `live_trade_cycle(coord, ...) → LiveTradeReport` — HITL-by-default | (operator-driven, see PHASE10_HITL_RUNBOOK.md) |

Phase-9 continuous-learning primitives in `agents/continuous.py`:
`decisions_dataset(...)` aggregates the audit log; `strategy_proposal_brief()`
flags coverage gaps for a strategy-proposal PR; `drift_check(...)`
compares live PnL against walk-forward expectation; `flag_tool_output(...)`
appends to `EXPORT_DIR/tool_quality.jsonl` for the operator's weekly
review.

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
| 10 | HITL live trader | code-side done; **first live trade is operator-driven** (see PHASE10_HITL_RUNBOOK.md); coordinator + revalidator + 2 channels + 3 hard caps + 4 MCP tools |

Three operator-driven gates remain (the two paper soaks + the first
real-money HITL trade). Everything that needs to compile and pass
tests does — 292+ tests green.

## HITL coordinator (Phase 10)

The live-trade path is human-in-the-loop by default. `HITLCoordinator`
(in `execution/hitl/coordinator.py`) is the single orchestrator that
sits between the scanner and the order manager. Per signal:

1. Build a `PendingSignal` with the proposed order's intent (symbol,
   side, ref_price, strategy_name, strategy_params, volume, notional,
   timeout). Append to `EXPORT_DIR/pending_signals.jsonl`.
2. Ask the channel (`TerminalChannel` or `TelegramChannel`) for a
   yes/no. In `auto` mode this step is skipped — but only this step.
3. On yes, run `StrictRevalidator` against fresh OHLCV. Four checks
   (freshness, new_bar, price_drift, signal_reemitted) must all pass
   or the signal terminates as `stale`.
4. Run `PreTradeValidator` with the freshly-built `OrderRequest`,
   `AccountSnapshot`, `MarketContext`, and `DailyTradeStats`. Hard
   caps live here, not in the coordinator.
5. Call `OrderManager.place_order(request, risk_check)`. Status
   transitions to `submitted` (or `failed` on broker rejection).

Every transition writes a new JSONL row to the store. Restart recovery
calls `resume_open_pending()` which `expire_overdue` first, then
`channel.replay_pending(open_signals)` — the operator sees a fresh
prompt for anything still alive.

Out-of-band control via MCP: `list_pending_signals`, `confirm_signal`,
`reject_signal`, `set_trading_mode` (the last requires `confirm=True`).

## Full codebase map

```
trading_on_tcbs_api/stock_system_v2/        # production system
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
│   ├── pre_trade_validator.py              # 8-rule validator + DailyTradeStats + RiskCheckResult
│   ├── trade_manager.py                    # DEPRECATED (ADR-002); DeprecationWarning on import
│   └── hitl/                               # ★ Phase 10
│       ├── coordinator.py                  # HITLCoordinator — scan→channel→reval→validate→place
│       ├── revalidator.py                  # StrictRevalidator (4 checks, force-refresh OHLCV)
│       ├── pending_signal_store.py         # append-only JSONL store
│       └── channels/                       # ConfirmationChannel + Terminal + Telegram
│
├── finance/
│   ├── account_manager.py                  # cash + positions; sync_from_api with drift gate
│   ├── reconciler.py                       # assert_no_drift; PositionDriftError
│   └── performance_analyzer.py             # PnL / drawdown / win-rate
│
├── tools/                                  # Phase-7 tool layer
│   ├── registry.py, response.py, context.py, mcp_server.py
│   └── handlers/                           # data/strategies/scanner/backtest/account/health/orders
│
├── agents/                                 # Phase-8 + Phase-9 agents
│   ├── research.py, scanner.py, risk.py
│   ├── paper_trader.py, live_trader.py
│   ├── continuous.py
│   └── prompts/                            # LLM system prompts for each agent
│
└── scripts/                                # operator-facing CLIs
    ├── scan_market.py                      # daily live signal scan
    ├── backtest_market.py                  # full-universe backtest
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
```
