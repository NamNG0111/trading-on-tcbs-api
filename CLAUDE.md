# CLAUDE.md

Guidance for Claude Code (claude.ai/code) working in this repo.

## Project overview

Algorithmic trading system on the Vietnamese TCBS brokerage API. V2
(`trading_on_tcbs_api/stock_system_v2/`) is the production system —
typed schemas, Pydantic contracts, structured logs, idempotent
execution, 19 MCP-callable tools, agent recipes for
research/scanner/risk/paper-trading/live-trading. Live trading is
human-in-the-loop by default (Phase 10): every signal asks for
confirmation via terminal or Telegram before any order is placed.

**Read these for deeper context** (don't reload them every session):

- `docs/AI_INTEGRATION_PLAN.md` — master plan, per-phase rationale
- `docs/AI_INTEGRATION_TODO.md` — per-task status; Phase 5+8 paper-soak gates remain
- `docs/stock_system_v2_guide.md` — V2 walkthrough + internals reference
  (data flow, schemas, observability, tool layer, agent layer, full codebase map)
- `docs/ADR-001` / `ADR-002` / `ADR-003` — data source, execution path, tool protocol
- `docs/PHASE5_SOAK_RUNBOOK.md`, `docs/PHASE8_PAPER_TRADER_RUNBOOK.md`,
  `docs/PHASE10_HITL_RUNBOOK.md` — operator runbooks

## Common commands

```bash
# Tests (292+ green; full suite, network-free, ~7s)
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
`ws_clients/`) is in maintenance mode — patch in place, don't extend.

```
   Agents (Phase 8/9/10): research, scanner, risk, paper_trader, live_trader,
                          continuous-learning
        │  drives via tools.invoke(name, args) only — zero internal imports
        ▼
   Tools (Phase 7+10):  19 registered tools + ToolResponse / ToolError envelope
        │  thin wrappers over the production primitives below
        ▼
   HITL Coordinator     channel ↔ revalidator ↔ validator ↔ order_manager
   (Phase 10):          pending_signals.jsonl is the audit-grade source of truth
        │  hitl mode = ask the human; auto mode = skip the ask, keep revalidating
        ▼
   Production V2:       scanner / backtester / order_manager / account / data_provider
        │  Pydantic schemas, typed exceptions, structured logs, correlation IDs
        ▼
   TCBS / vnstock       external broker (TCBS REST) + market data (vnstock-KBS)
```

Read bottom-up for the safety story; top-down for how an agent uses it.
Full internals (data flow per cycle, schemas table, obs primitives, tool
list, agent recipes) are in `docs/stock_system_v2_guide.md`.

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
`stop_loss_pct=0.05`, `take_profit_pct=0.10`, `max_open_positions=5`,
`max_position_size_vnd=50_000_000`, `max_daily_loss_vnd=10_000_000`,
`max_trades_per_day=10`.

HITL (Phase 10): `trading_mode='hitl'` (default) routes every signal
through the configured `confirmation_channel` (`terminal` | `telegram`)
before any order is placed. Strict re-validation runs after confirm
regardless of mode. Telegram setup + emergency auto-off:
`docs/PHASE10_HITL_RUNBOOK.md`.

## Codebase map (top level)

```
trading_on_tcbs_api/stock_system_v2/        # ★ production system
├── main.py                                 # composition root → AutoTrader
├── settings.py / config.py / exceptions.py # Settings.load() + typed errors
├── schemas/                                # Pydantic cross-module contracts
├── obs/                                    # structured logs + metrics + audit
├── auth/                                   # JWT load/save + OTP renewal
├── data_ingest/                            # vnstock fetch + cache + reconciler
├── core/                                   # scanner, backtester, walk_forward, auto_trader, costs, sizers
├── strategies/                             # Phase-4 framework + CONTRIBUTING.md
├── execution/                              # order_manager, tracker, validator
│   └── hitl/                               # ★ Phase-10 HITL: coordinator, store, channels, revalidator
├── finance/                                # account_manager, reconciler, performance
├── tools/                                  # ★ Phase-7 tool layer (registry + handlers + MCP server)
├── agents/                                 # ★ Phase-8/9/10 agents + LLM prompts
└── scripts/                                # operator CLIs: scan_market, backtest_*

tests/                                      # 193+ tests, network-free
docs/                                       # plans, ADRs, runbooks, internals reference
```

Full per-file map: `docs/stock_system_v2_guide.md` → "Full codebase map".

**Legacy folders (patch-only, don't extend):** `stock_strategy/`,
`futures_strategy/`, `simple_wow/`, `indicators/`, top-level `core/`,
`ws_clients/`, `runners/`, `utils/`, `logger_utils/`.

## Cross-cutting standards (apply throughout)

- **Type hints on every public function.** `mypy --strict` passes on
  the typed core (schemas, exceptions, settings, costs, position_sizer).
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
- New confirmation channel → implement `ConfirmationChannel` Protocol
  under `execution/hitl/channels/` (see `terminal.py` for the minimal
  shape, `telegram.py` for the async-with-callback shape).
- New hard cap on orders → extend `ValidatorConfig` + add a rule in
  `PreTradeValidator.validate`; if it needs cross-order state, plumb
  through `DailyTradeStats`.
- API issue → `auth/auth.py` (token) → `core/stock_api_client.py`
  (REST) → `docs/tcbs_openapi.json` for the spec.
- Anything under "Legacy folders" above: patch only.

## Key dependencies

- `vnstock` — historical OHLCV (KBS source)
- `pandas-ta` — vectorized indicators (V2 standard; not TA-Lib)
- `pydantic` v2 — every cross-module contract; `pydantic.mypy` plugin wired
- `aiohttp`, `requests` — async + sync HTTP to TCBS
- `mcp` (optional) — only needed for the MCP server entry point;
  tests + handlers don't import it
- `python-telegram-bot>=22` (optional) — only needed when
  `confirmation_channel='telegram'`; module gracefully sets
  `TelegramChannel=None` when missing
