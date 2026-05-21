# Road to 100% — Step-by-Step Path to a Live AI Trading System

You're not coding anymore. The remaining work is **operating** the
system, watching it for a few weeks in safe modes, and only then
letting it touch real money. This document is the only thing you need
to follow to get there.

---

## TL;DR — where you are right now

- **Code is done.** 292 tests pass. Every safety primitive is wired:
  HITL human-confirmation, strict re-validation, hard caps, kill-switch,
  idempotency, restart recovery.
- **What's left is calendar time** — three soaks where the system runs
  in progressively riskier modes while you watch.
- **Total time to 100%:** ~6 weeks (mostly waiting), plus ~2 evenings
  of operator setup.

The three gates, in order:

| # | Gate | Mode | Risk | Duration |
|---|---|---|---|---|
| 1 | Paper soak | safe-mode, fake fills | None | 2 weeks |
| 2 | Paper-trader soak | safe-mode, agent-driven | None | 4 weeks |
| 3 | First live HITL trade | live, human-confirms every order | Real money, your veto | 1 trade |
| 4 | Steady-state HITL | live, human-confirms every order | Real money, your veto | Indefinite |
| 5 | (Optional) Auto mode | live, agent auto-confirms | Real money, no veto | Only when YOU are ready |

**You never have to advance.** If you want to stay in HITL forever,
the system is designed for that. Auto mode is opt-in by design.

---

## Setup (one-time, ~30 minutes)

Do this once before starting any soak.

### Step 1. Confirm the system runs

```bash
cd /Users/namng/PycharmProjects/PythonProject/trading-on-tcbs-api
make test
```

Expect: `292 passed`. If not, stop and fix. Don't proceed with failing tests.

### Step 2. Confirm credentials

```bash
ls trading_on_tcbs_api/config/credentials.yaml
```

Should exist. If missing:

```bash
python trading_on_tcbs_api/runners/setup_credentials.py
```

### Step 3. Set up Telegram (for HITL, recommended)

You'll use Telegram to approve trades from your phone. Skip if you
plan to sit at the terminal during market hours every day.

1. Open Telegram on your phone.
2. Search for **@BotFather** → tap **Start** → type `/newbot`.
3. Give it a name (e.g., "TCBS HITL"). Save the token it gives you,
   it looks like `1234567:AAExampleBotToken`.
4. Search for **@userinfobot** → tap **Start**. It will reply with
   your chat ID (a long integer).
5. Open Telegram, find your new bot, send it any message (this is
   required — Telegram blocks bots from messaging users first).
6. Add both to `trading_on_tcbs_api/config/credentials.yaml`:

   ```yaml
   telegram_bot_token: "1234567:AAExampleBotToken"
   telegram_chat_id:   "987654321"
   ```

7. Verify the Python library is installed:

   ```bash
   python -c "import telegram; print(telegram.__version__)"
   ```

   Should print a version number ≥ 22.

### Step 4. Tune your hard caps

Open `trading_on_tcbs_api/stock_system_v2/settings.py`, find the
`RiskParams` class. Defaults are:

```python
max_position_size_vnd = 50_000_000   # 50M VND per name
max_daily_loss_vnd    = 10_000_000   # 10M VND realized loss / day → stop
max_trades_per_day    = 10           # max orders / day
```

**Recommendation for your first month live:** halve these.

```python
max_position_size_vnd = 25_000_000   # 25M VND
max_daily_loss_vnd    = 5_000_000    # 5M VND
max_trades_per_day    = 5
```

The caps are belt-and-suspenders — even if the AI goes haywire, the
validator blocks orders past these limits.

### Step 5. Pick where logs go

By default logs land in `logs/` next to the project. If you want them
on Google Drive (so you can read them from your phone), edit
`trading_on_tcbs_api/config/local_config.json`:

```json
{
  "DATA_DIR":   "/path/to/Google Drive/tcbs-data/stocks",
  "EXPORT_DIR": "/path/to/Google Drive/tcbs-data/exports"
}
```

That's it for setup.

---

## Gate 1 — Phase 5 Paper Soak (2 weeks, ZERO risk)

**Goal:** prove the system can run for two weeks against live market
data without making mistakes a human would notice. **No real orders
are placed** — the kill-switch is on the whole time.

### What you'll run

Every trading day (Mon–Fri, when the Vietnam market is open):

```bash
# Morning, before market open (or any time during the day)
EXECUTION_DISABLED=true python trading_on_tcbs_api/stock_system_v2/main.py
```

The flag `EXECUTION_DISABLED=true` is the absolute kill-switch.
Every order placement returns "REJECTED:kill_switch" — guaranteed.

### What you watch for

At the end of each day, check:

```bash
# Did anything error out?
grep '"level":"ERROR"' logs/*.log | wc -l

# Did the data layer disagree with TCBS prices?
grep "drift" logs/*.log

# Did any unexpected exceptions crash a cycle?
grep '"event":"order.rejected.kill_switch"' logs/*.log | wc -l
```

Write a one-line journal each evening:
- Date
- Errors? (count)
- Drift warnings? (count)
- Notes (e.g., "system caught a real BUY signal on HPG that I would've taken")

### When to advance

After 14 trading days, you can advance to Gate 2 if:

- [ ] Zero unhandled exceptions in the logs
- [ ] Zero "silent" failures (every error has a clear typed reason)
- [ ] Drift warnings stayed below 1% of bars (some are normal)
- [ ] You feel comfortable reading the daily journal

If anything looks weird, **don't advance**. Open it as an issue and
fix it. The point of this soak is to surface problems before money is
involved.

Full details: `docs/PHASE5_SOAK_RUNBOOK.md`.

---

## Gate 2 — Phase 8 Paper-Trader Soak (4 weeks, ZERO risk)

**Goal:** prove the **agent loop** (research → scan → risk → submit)
makes sane decisions over a full month, against live data, with the
kill-switch on.

This is the same code as Gate 1, except it now runs the full agent
loop end-to-end instead of just the scanner.

### What you'll run

Every trading day:

```bash
EXECUTION_DISABLED=true python -c "
from trading_on_tcbs_api.stock_system_v2.agents import paper_trade_cycle
report = paper_trade_cycle()
print(report.model_dump_json(indent=2))
" > logs/paper_$(date +%Y-%m-%d).json
```

This prints a JSON report with every signal, what the risk agent
thought of it, and whether (in a real-money world) it would have
been submitted.

### What you watch for

Each evening, open today's JSON:

```bash
cat logs/paper_$(date +%Y-%m-%d).json | jq '.actions[] | {symbol: .signal.symbol, verdict: .opinion.verdict, action: .action}'
```

You want to see:
- Risk agent rejecting orders that obviously shouldn't go through
  (e.g., over-cap, missing universe membership).
- Submitted orders matching what a sober human trader would do.
- No "agreed-to-but-bad" trades — i.e., risk approving an order you'd
  veto in person.

Keep a weekly tally:

| Week | n_signals | n_submitted | n_rejected | "I'd've vetoed" |
|---|---|---|---|---|
| 1 | _ | _ | _ | _ |
| 2 | _ | _ | _ | _ |
| 3 | _ | _ | _ | _ |
| 4 | _ | _ | _ | _ |

### When to advance

After 4 weeks, you can advance to Gate 3 if:

- [ ] Zero risk-rule violations slipped through
- [ ] Audit trail (in `decisions.jsonl`) matches what the agent said it did
- [ ] The "I'd've vetoed" count is small and trending down
- [ ] Performance roughly tracks the backtest expectation (no wild surprises)

This is where you build **trust**. Don't rush it. The whole point of
HITL is that you're not surrendering trust until you have it.

Full details: `docs/PHASE8_PAPER_TRADER_RUNBOOK.md`.

---

## Gate 3 — First Live HITL Trade (~30 minutes attention)

**Goal:** one real-money trade, confirmed by you via Telegram, end-to-end.
Tiny size. The point isn't profit — it's proving the live path works.

### Pre-flight checklist

- [ ] Gate 1 complete (2-week paper soak passed)
- [ ] Gate 2 complete (4-week paper-trader soak passed)
- [ ] Telegram bot tested (you got a manual ping from it)
- [ ] Hard caps set to **half** their normal values for this first day
- [ ] You have 1–2 hours of free attention during market hours

### Run the system

```bash
# Note: EXECUTION_DISABLED is NOT set — this is live.
# trading_mode defaults to 'hitl' so every signal still asks you.
python trading_on_tcbs_api/stock_system_v2/main.py
```

### What happens

1. Scanner runs, finds signals (or doesn't — that's fine, just wait).
2. For each signal, your Telegram chat gets a message:

   ```
   🔔 SIGNAL ps_abc123def456
   rsi BUY HPG
   @ 27,500 × 100 = 2,750,000 VND
   expires 11:32:05 UTC
   [✅ Confirm]  [❌ Reject]
   ```

3. **Decide what you want.** Read the signal carefully. Look at the
   stock on your own terms. If you're not sure → tap ❌. If you're
   genuinely OK → tap ✅.

4. After tapping ✅, the system re-validates against fresh data
   (price might've moved). Three outcomes:
   - **Confirmed and placed:** you get a follow-up message:
     `✅ HPG BUY ps_abc → submitted (broker_order_id=… status=ACCEPTED)`.
   - **Stale:** the price moved >2% or the signal vanished:
     `🌫 HPG BUY ps_abc → stale (price drift 2.4%)`.
     **No order is placed.** Scanner picks up the symbol next cycle.
   - **Failed:** validator blocked it (hit a cap, etc):
     `🚫 HPG BUY ps_abc → failed (max_position_size)`.

5. If you ignore the message, it expires after `confirmation_timeout_sec`
   (default 1 hour). No order is placed.

### What to do if something feels wrong

- **Stop dispatching:** ctrl-C the running process. Open pending
  signals survive on disk; the next launch replays them.
- **Hard kill-switch:** open a new terminal, set
  `EXECUTION_DISABLED=true` in your shell, restart the process.
  Every order placement returns rejected for the rest of the session.

### When to call Gate 3 done

You're ready to declare the live path working when you've done all of:

- [ ] One signal tapped ✅, order placed, real fill in your TCBS account
- [ ] One signal tapped ❌, no order placed, status `rejected`
- [ ] One signal allowed to time out, status `expired`
- [ ] One signal where the price moved enough to flip it to `stale`
- [ ] Restarted the process mid-pending — got the prompt again

You can collect these over a week. No rush.

---

## Gate 4 — Steady-state HITL (indefinite, your call)

Once Gate 3 is done, this is just "Gate 3 forever". Every signal
asks you. You can be at the terminal, on your phone, away from the
desk — Telegram doesn't care.

Daily routine:

1. **Morning:** launch the system. Glance at any replayed pending
   signals from yesterday (most will have expired overnight; the
   coordinator sweeps them on startup).
2. **During market:** when a Telegram message arrives, decide and tap.
3. **Evening:** read the day's `pending_signals.jsonl`. Look for
   patterns — strategies that fire too often, symbols that always
   stale, caps you should adjust.

Adjust hard caps and `max_price_drift_pct` over time as you learn
what's normal.

---

## Gate 5 — Optional: Auto Mode (only when YOU are ready)

After weeks or months of HITL where you tapped ✅ on basically
everything the system asked, you may decide auto-mode is OK. Two
ways to flip the switch:

### Permanent (next restart)

Open `settings.py`, change:

```python
trading_mode: Literal["hitl", "auto"] = "auto"   # was "hitl"
```

Restart the system.

### Temporary (this session only)

If you're driving via an MCP client / Claude Code session:

```python
tools.invoke("set_trading_mode", {"mode": "auto", "confirm": True})
```

Note: `confirm=True` is mandatory. Without it, the call is a no-op.
This prevents an LLM (or your sleepy finger) from silently disabling
the human gate.

**To revert in an emergency:** call the same tool with `mode="hitl"`,
or set `EXECUTION_DISABLED=true` and restart.

Restarts always read `Settings.trading_mode` from disk. Runtime
auto-mode cannot quietly outlive your session.

---

## The big-red-button page

When something is going wrong, in order of severity:

| Severity | What to do | Effect |
|---|---|---|
| Need a moment to think | Ignore Telegram message | Signal expires in 1h, no order |
| Stop dispatching new signals | ctrl-C the process | Open signals durable; restart replays |
| Stop placing orders entirely | `export EXECUTION_DISABLED=true && restart` | Every order returns REJECTED |
| Stop everything | Close the terminal / kill the process | Same as ctrl-C |
| Cancel an order already at broker | Use the TCBS app | Out of our system |

---

## Daily journal template

Copy this to a note (or use `docs/journal/YYYY-MM-DD.md`) each evening:

```
Date: 2026-05-21
Gate: 1 / 2 / 3 / 4
Trading mode: hitl / auto

Cycles run:           ___
Signals dispatched:   ___
  Confirmed:          ___
  Rejected by me:     ___
  Expired:            ___
  Stale on revalidate: ___
  Submitted:          ___
  Failed validator:   ___

Errors in logs?      none / [count]
Drift warnings?      none / [count]
Anything I'd change tomorrow?

Notes:
```

Five minutes a day. After 6 weeks you'll have a journal that tells you
whether to advance, hold, or step back.

---

## What "100% ready" means

You are at 100% when:

1. Gates 1–3 are complete.
2. You have **at least 1 month** of HITL live trading where you tapped
   ✅ on the things that worked and ❌ on the things that didn't, and
   you can describe in one sentence what kind of mistakes the system
   makes.
3. Your daily journal shows the system isn't surprising you.

At that point you can decide whether to flip to auto. Or stay in HITL
forever — that's also "100% ready", just with a different sliding
slider between "AI" and "human".

The system is built so you never *have* to advance. The toggle is the
feature.

---

## Where to look when stuck

- **Operator-facing:** `docs/PHASE5_SOAK_RUNBOOK.md`,
  `docs/PHASE8_PAPER_TRADER_RUNBOOK.md`, `docs/PHASE10_HITL_RUNBOOK.md`.
- **Tech detail:** `docs/stock_system_v2_guide.md` (architecture
  walkthrough), `CLAUDE.md` (codebase map).
- **Plan + history:** `docs/AI_INTEGRATION_PLAN.md`,
  `docs/AI_INTEGRATION_TODO.md` (every box is ticked except the soaks).
- **When something breaks:** `grep '"level":"ERROR"' logs/*.log` —
  every error in V2 is a typed `StockSystemError` with a stable code
  you can search for in the source.

Good luck. Take it slow. The system isn't going anywhere — the only
way to lose is to skip a gate.
