# Quickstart — using the V2 system from scratch

You've built a lot. This file is the user manual: how to actually get
value out of it day-to-day, especially the workflow that takes you
from **"I have an idea"** to **"it's running paper-trades"** without
needing to remember the internals.

There are three usage modes, in increasing order of capability:

  1. **Scripts** (no chat, no Claude) — `python …/scan_market.py`.
  2. **Direct Python** (importing tools) — quick experiments.
  3. **Claude over MCP** (the real value) — chat about ideas, the
     toolbelt does the work.

Mode 3 is the one Phases 0–9 were built for. The rest of this doc
focuses there.

---

## Part A — One-time setup (≈15 min)

### A.1 Install the MCP SDK

```bash
pip install mcp
```

(Tests + scripts don't need this; only the chat-with-Claude path does.)

### A.2 Verify TCBS credentials

```bash
ls trading_on_tcbs_api/config/credentials.yaml      # should exist
cat trading_on_tcbs_api/config/local_config.json    # DATA_DIR + EXPORT_DIR pointing at Google Drive
```

If credentials are stale, refresh the JWT:

```bash
python trading_on_tcbs_api/runners/setup_credentials.py
```

### A.3 Set the kill-switch and confirm the test suite is green

```bash
export EXECUTION_DISABLED=true     # belt and braces — defaults safe-mode anyway
make test                          # 193 tests, ~4 seconds
```

If anything is red, stop and fix before going further.

### A.4 Wire the MCP server into your Claude client

Find your Claude client's MCP config (Claude Desktop:
`~/Library/Application Support/Claude/claude_desktop_config.json`;
Claude Code: `~/.claude/mcp.json`). Add:

```json
{
  "mcpServers": {
    "trading-tcbs": {
      "command": "python",
      "args": [
        "-m",
        "trading_on_tcbs_api.stock_system_v2.tools.mcp_server"
      ],
      "env": {
        "EXECUTION_DISABLED": "true",
        "PYTHONPATH": "/Users/namng/PycharmProjects/PythonProject/trading-on-tcbs-api"
      }
    }
  }
}
```

Restart Claude. In a fresh chat, ask:

> List the trading tools you have access to.

You should see 15 tools: `list_symbols`, `list_strategies`,
`scan_market`, `run_backtest`, `walk_forward`, `validate_order`,
`submit_order`, etc. If you see them, you're ready.

---

## Part B — The everyday chat patterns

These are the prompts that pay back the build. Each one is one
message; the agent makes the right tool calls.

### B.1 "What's signalling today?"

> Run a daily scan across the universe with RSI Reversal, SMA 20/50,
> Volume Boom, and Dip Buy. Tell me what fired and which names look
> most interesting.

Tool path: `scan_market`. Output: a `ScannerReport` grouped by
`(strategy, side)` with a one-paragraph headline.

### B.2 "Is HPG a BUY today?"

> Scan HPG with every strategy in the registry and tell me what they
> say.

Tool path: `list_strategies` then `scan_market` with `symbols=["HPG"]`.

### B.3 "Which existing strategy is best for HPG over 2 years?"

This is the §14 example from the plan. Use the research agent.

> Use the research agent to find the best strategy for HPG over the
> last 2 years. Show the walk-forward stats and tell me whether to
> trust the recommendation.

Tool path: `list_strategies` → `walk_forward` for each candidate →
ranked `ResearchNote`. The agent **will not** recommend a strategy
with zero OOS trades, will flag inconclusive results plainly, and
always attaches the survivor-bias disclaimer.

### B.4 "What if I tweaked the parameters?"

For *parameter sweeps on existing strategies* you stay in chat — no
code.

> Backtest RSIStrategy on HPG over 3 years with these param sets:
> oversold=25, oversold=30, oversold=35. Compare results.

The agent calls `run_backtest` three times with different `params`,
returns a table, and explains tradeoffs.

### B.5 "Evaluate this order before I submit"

> I'm thinking of buying 100 HPG at 28,000 VND. Run a pre-trade check
> and tell me if you'd approve it.

Tool path: `validate_order` + `get_account` → `RiskOpinion` with
verdict ∈ {approve, approve_with_warnings, reject}.

### B.6 "Submit it" (paper)

> Submit the trade. We're in safe mode so it's a mock fill — log it
> for the audit trail.

Tool path: `submit_order` with the `risk_check_id` from the
validation step. Returns FILLED with `broker_order_id` starting with
`mock_`.

---

## Part C — The big one: idea → backtest → paper → live

This is the workflow you specifically asked about. There are two
flavours depending on whether your idea fits in the existing
primitives or needs a new strategy class.

### Decision tree

```
Does your idea boil down to "use existing strategy X with different params"?
    YES → Path 1 (chat-only; ≈5 minutes)
    NO  → Path 2 (Claude writes a new strategy class; ≈30 minutes)
```

### Path 1 — Parameter sweep, chat only

Example idea: *"What if RSI Reversal triggered earlier — at oversold=25 instead of 30?"*

Step 1 — describe it:

> RSIStrategy with `oversold=25, overbought=75, is_reversal=true`. I
> want to know if this version holds up out-of-sample on at least 5
> of our 8 universe symbols over 2 years.

Step 2 — let the agent run the gate:

The agent calls `walk_forward` for each universe symbol with your
params, applies the §14 "held up on ≥5 of 8" gate, and tells you
yes/no with the per-symbol stats.

Step 3 — if it passed:

> If it held up on ≥5 symbols with avg Sharpe > 0.3, propose a
> paper-trade plan: which symbols to scan, lot size, validator caps.

Step 4 — paper soak (you, in the terminal):

```bash
# Set this once per shell — every order rejects in live mode regardless of safe_mode.
export EXECUTION_DISABLED=true

# Run the demo daily for a week to feel the rhythm:
python trading_on_tcbs_api/stock_system_v2/scripts/demo_done_looks_like.py
```

The script picks up your params automatically because they live in
the strategy's registered defaults. **If you want to experiment with
non-default params daily**, drop them in a `params.yaml` and run the
agent prompt that loads it.

### Path 2 — New strategy class

Example idea: *"Buy when MACD crosses up AND price is above SMA50.
Sell on RSI > 70."*

This isn't a parameter tweak — it's new logic. You need a Python
file under `strategies/`. The good news: Claude Code does this for
you, and CI catches mistakes.

Step 1 — describe it precisely. Be specific about what triggers each
side.

> I want a new strategy: BUY when MACD line crosses above its signal
> line AND today's close > 50-day SMA. SELL when RSI(14) > 70. Call
> it `macd_above_sma`. Indicators needed: `macd_12_26_9`,
> `macds_12_26_9`, `sma_50`, `rsi_14`. Add it following
> strategies/CONTRIBUTING.md.

Step 2 — Claude (in Claude Code, *not* the chat client; this needs
file-edit access) does the following without further prompting:

1. Reads `strategies/CONTRIBUTING.md` — the bar.
2. Writes `strategies/macd_above_sma_strategy.py`:
   - `Params(StrategyParams)` with the tunable knobs + `Field(ge=…, le=…)`.
   - `min_bars_required = 50` (longest lookback).
   - `_compute_signals(df)` that reads the indicator columns.
   - `describe()` returning the rationale.
3. Adds a row to `IndicatorEngine` defaults if your indicators
   aren't already there (MACD probably isn't — Claude extends the
   engine).
4. Registers the strategy in `strategies/registry.py`.
5. Adds `tests/strategies/test_macd_above_sma.py` with the 5
   required tests (regression seal, no-lookahead, warmup,
   param-validation, determinism).
6. Runs `make test` and `make strategy-smoke NAME=macd_above_sma`.

If smoke gates fail (zero trades, infinite drawdown, etc.), Claude
iterates. If they pass, you're ready for the §14 gate.

Step 3 — universe-wide gate:

```bash
python trading_on_tcbs_api/stock_system_v2/scripts/evaluate_strategy.py macd_above_sma
```

This runs the same "held up on ≥5 of 8 with avg Sharpe > 0.3" gate.
Output is a per-symbol WF table + verdict + (if passed) today's
validator-approved order list.

Step 4 — if the gate passed, run the paper soak. Same as Path 1.

Step 5 — graduation review (after 4 weeks). See
`docs/PHASE8_PAPER_TRADER_RUNBOOK.md`. Three checks: zero risk-rule
violations, audit trail matches reasoning, performance roughly
tracks backtest.

Step 6 — first live trade. See `docs/PHASE5_SOAK_RUNBOOK.md`. Single
symbol, single round lot, kill-switch flipped per-session.

---

## Part D — When things go wrong

### "I'm seeing a `PositionDriftError`"

The autotrader's local position book disagrees with the broker
beyond the threshold. **Halt the soak.** Inspect:

```bash
python -c "
from trading_on_tcbs_api.stock_system_v2.execution.order_tracker import OrderTracker
print(OrderTracker().recover_open_orders())
"
```

Reconcile manually before resuming. The error's `details["diff"]`
field has the per-symbol delta.

### "Tests are red after I added a strategy"

The regression seals likely shifted because your strategy now exists.
If the change is intentional:

```bash
make fixtures        # regenerates expected signal CSVs; review the diff
make test
```

If the change is unintentional, your strategy is leaking future data
into a past signal. The `assert_no_lookahead` test in
`tests/strategies/test_no_lookahead.py` catches this; read its
output and fix.

### "Live PnL is way off from backtest"

Run drift detection:

> Run drift_check for `<strategy>` on `<symbol>` with my observed
> live return of `<X>%`.

The threshold is 30 percentage points. A breach logs `drift.alerts`
and tells you to investigate.

### "I want to see what the system did in the last hour"

```bash
# All structured log lines for one trade cycle:
grep '"correlation_id":"cycle_<id>"' logs/*.log

# All metric events:
grep '"event":"metric"' logs/*.log

# Decision audit trail (one row per order intent):
tail -n 50 "$(python -c 'from trading_on_tcbs_api.stock_system_v2 import config; print(config.EXPORT_DIR)')/decisions.jsonl"
```

### "I want to flag a tool that returned garbage"

In code or via Claude:

> Use the agents.flag_tool_output helper to record that
> `compute_indicators` returned NaN for sma_20 on every bar of HPG
> with default args. Severity: major.

Adds one row to `EXPORT_DIR/tool_quality.jsonl` for the operator's
weekly review (Phase-3 contract fix candidates).

---

## Part E — Mental model

If you remember nothing else:

  - **Tools are the surface.** Anything an agent should be able to
    do is exposed as a tool in `tools/handlers/`. If you find
    yourself wanting to write Python to do something, ask first
    whether a tool should exist instead.

  - **Schemas are the contract.** Every cross-module return is a
    Pydantic model in `schemas/`. No raw dicts crossing module
    borders.

  - **Validate before you submit.** Live orders require a fresh,
    hash-bound `RiskCheckResult` token. The validator is not
    negotiable — there is no "approve anyway" path.

  - **Survivor bias is uncorrected.** Every backtest report says so.
    Treat headline numbers as upper bounds, not forecasts.

  - **Two operator-driven gates remain.** The 2-week paper soak
    (Phase 5) and the 4-week paper-trader soak (Phase 8). Calendar
    time, not code time. See the two PHASE\*\_RUNBOOK.md files.

---

## Part F — Cheat sheet

| Want to… | Do this |
|---|---|
| See today's signals | `python …/scripts/scan_market.py` or chat: *"daily scan"* |
| Find the best strategy for one symbol | Chat: *"research the best strategy for HPG"* |
| Test a parameter tweak | Chat: *"backtest RSI with oversold=25 on HPG"* |
| Add a brand-new strategy | Claude Code: *"new strategy `<name>` per CONTRIBUTING.md"* |
| Validate a single order | Chat: *"evaluate buying 100 HPG at 28000"* |
| Run the §14 gate end-to-end | `python …/scripts/demo_done_looks_like.py` |
| Run the gate on one strategy | `python …/scripts/evaluate_strategy.py <name>` |
| Start the paper soak | `EXECUTION_DISABLED=true python …/main.py` |
| Read the audit trail | `tail decisions.jsonl` |
| Flip the kill-switch | `export EXECUTION_DISABLED=true` |
