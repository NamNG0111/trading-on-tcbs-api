# Phase 10 — HITL Live Trader Runbook

Operator guide for the human-in-the-loop (HITL) live-trade path. The
default mode is `hitl`: every scanner signal queues for explicit
confirmation before any order is placed. `auto` mode is opt-in and
still re-validates strictly against fresh data — auto means "skip the
human", not "skip safety".

## Pre-flight

Before flipping on live trading, confirm:

1. **Phase 5 paper soak** (2 weeks, zero silent drift) has cleared.
   → `docs/PHASE5_SOAK_RUNBOOK.md`.
2. **Phase 8 paper-trader soak** (4 weeks) has cleared all graduation
   criteria. → `docs/PHASE8_PAPER_TRADER_RUNBOOK.md`.
3. Hard caps in `Settings.risk` reflect your tolerance:
   - `max_position_size_vnd` — single-name post-trade cap.
   - `max_daily_loss_vnd`    — realized-loss floor for one day.
   - `max_trades_per_day`    — sanity cap on order count.
4. `EXECUTION_DISABLED` env var is correctly set / unset for your
   intent. `true` is a global kill-switch that overrides every mode.

## Two confirmation channels

Pick one via `Settings.confirmation_channel`:

### Terminal

Simplest, no setup. Prompts on stdin; reply with `y` / `n` / Enter.

```python
from trading_on_tcbs_api.stock_system_v2.execution.hitl import TerminalChannel
chan = TerminalChannel()
```

Good for the first day or two of live testing while you're at the desk.

### Telegram (recommended for ongoing use)

Mobile-friendly. Each signal becomes a Telegram message with
✅ / ❌ inline buttons.

**One-time setup:**

1. In Telegram, message [@BotFather](https://t.me/BotFather) and create
   a bot with `/newbot`. Save the token.
2. Message your new bot once (so Telegram allows it to message you back).
3. Get your chat id — easiest: ping [@userinfobot](https://t.me/userinfobot).
4. Add the two values to `trading_on_tcbs_api/config/credentials.yaml`:

   ```yaml
   telegram_bot_token: "1234567:AAExampleBotToken"
   telegram_chat_id:   "987654321"
   ```

5. Verify the dep is installed:

   ```bash
   python -c "import telegram; print(telegram.__version__)"
   ```

**Wire it up:**

```python
from trading_on_tcbs_api.stock_system_v2.execution.hitl.channels import TelegramChannel
chan = TelegramChannel(
    token=settings.telegram_bot_token,
    chat_id=settings.telegram_chat_id,
)
await chan.start()
# ... build coordinator + live_trade_cycle ...
await chan.stop()
```

**Manual smoke (do this once before relying on it):**

1. Start the bot with `EXECUTION_DISABLED=true` and a fixture signal.
2. Watch the prompt arrive in your Telegram chat.
3. Tap ✅. Confirm the audit log shows revalidation ran and the order
   would have been placed (kill-switch records `REJECTED:kill_switch`).
4. Re-run, tap ❌. Confirm the audit log shows `rejected`.
5. Re-run, do nothing for the timeout (`Settings.confirmation_timeout_sec`).
   Confirm the audit log shows `expired`.

## Mode toggle

The coordinator stores `trading_mode` as an in-process attribute. Two
ways to flip it:

- **At process start:** set `Settings.trading_mode = "auto"` and restart.
- **At runtime, via MCP / chat:** call the `set_trading_mode` tool with
  `mode="auto", confirm=True`. The flag is intentional — a stray
  `set_trading_mode({"mode": "auto"})` without `confirm=True` is a
  no-op echo, so neither an LLM nor a fat-fingered keystroke can
  silently disable the human gate.

Restarts revert to `Settings.trading_mode` by design. A runtime flip to
`auto` cannot quietly outlive the session.

## What happens to a signal

```
scanner emits ScanResult
  │
  ▼
coordinator.handle_signal(...)
  ├─ PendingSignal appended to pending_signals.jsonl (status=awaiting)
  ├─ channel.request(pending)              [skipped in auto mode]
  │     ├─ yes      → coordinator advances
  │     ├─ no       → status=rejected, scanner moves on
  │     └─ timeout  → status=expired, scanner moves on
  ▼
revalidator.check(pending)                  [STRICT, always runs]
  ├─ freshness         (fresh fetch returned closed bars)
  ├─ new_bar           (a NEW bar has formed since the original signal)
  ├─ price_drift       (within max_price_drift_pct, default 2%)
  └─ signal_reemitted  (originating strategy STILL emits the same side
                        on the latest closed bar)
  ├─ any check fails → status=stale, scanner picks up next cycle
  ▼
PreTradeValidator.validate(req)             [hard caps, universe, etc.]
  ├─ any BLOCK → status=failed
  ▼
OrderManager.place_order(req, risk_check)
  ├─ EXECUTION_DISABLED → REJECTED
  ├─ broker error       → status=failed
  └─ accepted/filled    → status=submitted
```

Every transition is one new line in `pending_signals.jsonl`. State
recovery on restart reads `load_open()` and replays via the channel.

## MCP tools for out-of-band control

| Tool | Side-effecting | Use case |
|---|---|---|
| `list_pending_signals` | no | Inspect the queue. `include_terminal=True` returns the full audit. |
| `confirm_signal(id)` | yes | Approve from chat / MCP / web UI; runs same revalidator + placement path. |
| `reject_signal(id, reason)` | yes | Decline out-of-band. Idempotent on terminal rows. |
| `set_trading_mode(mode, confirm=True)` | yes | Runtime HITL ↔ auto toggle. |

These are intended for when you're driving the system from an MCP
client (e.g. Claude Code session). The channel-based flow (Telegram
buttons) and the MCP flow are independent — use whichever you have at
hand, not both simultaneously on the same signal.

## Stuck-signal recovery

A pending signal stuck in `awaiting` past its `expires_at` will be
swept to `expired` on the next coordinator startup (`resume_open_pending`
calls `expire_overdue` first). If you want to flush manually:

```python
store.expire_overdue()
```

A signal stuck in `confirmed` (rare — implies a crash between the
status write and the revalidator call) can be re-driven by calling
`coord.confirm_pending(id)` again. The store transitions are
idempotent, but the revalidator may now return `stale` because the
market moved on; that's the safe outcome.

## Emergency auto-off

Two layers:

1. **Process-level:** export `EXECUTION_DISABLED=true` and restart.
   Every order placement returns `REJECTED:kill_switch`. Mode does
   not matter.
2. **Runtime:** call `set_trading_mode({"mode": "hitl", "confirm": True})`
   via MCP. Subsequent signals re-enter the human gate immediately.

If both layers are in `auto` + `EXECUTION_DISABLED=false` and you want
to stop dispatching entirely: ctrl-C the live-trader process. Open
pending signals are durable; the next launch replays them via the
configured channel.

## Audit and observability

Three durable trails:

| File | Contents |
|---|---|
| `EXPORT_DIR/pending_signals.jsonl` | Every PendingSignal transition, one row per state change. |
| `EXPORT_DIR/ledger.csv` | Every order, one row per status change (Phase 5). |
| `EXPORT_DIR/decisions.jsonl` | Audit-quality record per order intent (Phase 6). |

Structured JSON logs from every component carry the per-cycle
`correlation_id`. To trace one signal:

```bash
grep '"correlation_id":"cycle_…"' logs/*.log
```

Metrics (counters in the metrics log):

- `hitl.signal.dispatched` / `confirmed` / `rejected` / `expired` /
  `stale` / `submitted` / `failed` — with `mode=hitl|auto` and
  occasionally `source=tool` labels.

## When to call it ready

Tick Phase-10 DoD only when ALL of the following hold:

- [ ] Real account, HITL mode: scanner fires a signal → channel prompt
      → operator taps ✅ → revalidator passes → live order placed →
      outcome notification arrives.
- [ ] Real account, HITL mode: same as above with ❌ → status=rejected,
      no order.
- [ ] Real account, HITL mode: signal allowed to time out → status=expired.
- [ ] Real account, HITL mode: signal where the market moved more than
      `max_price_drift_pct` between scan and confirm → status=stale,
      no order, scanner picks up next cycle cleanly.
- [ ] Restart in the middle of an `awaiting` signal → re-prompt arrives
      via channel; operator can still confirm.
- [ ] Each hard cap (position size, daily loss, trades/day) proven by
      a deliberate breach in a paper run; validator BLOCKs as expected.
- [ ] Auto-mode toggle exercised at least once. Reverted to HITL before
      the session ends.
