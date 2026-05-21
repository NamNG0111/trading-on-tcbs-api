"""Terminal confirmation channel (Phase 10).

Stdin/stdout channel for local development and the initial soak. Uses
`asyncio.to_thread` to wrap the blocking `input()` call so the scanner
loop never blocks on a single prompt. `asyncio.wait_for` enforces the
`PendingSignal.expires_at` deadline.

Replies are interpreted permissively:
  - `y`, `yes`, `1`, `ok`, `confirm` → yes
  - `n`, `no`, `0`, `cancel`, `reject`, empty line, EOF → no
  - timeout while waiting → timeout

Outputs are plain text. Operators wanting a richer experience should use
the Telegram channel (Chunk 7).
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from typing import Callable, IO

from trading_on_tcbs_api.stock_system_v2.execution.hitl.channels.base import (
    ConfirmationChannel,
    ConfirmationResponse,
)
from trading_on_tcbs_api.stock_system_v2.obs import get_logger, log_event
from trading_on_tcbs_api.stock_system_v2.schemas import PendingSignal

_logger = get_logger("hitl.channel.terminal")

_YES_TOKENS = frozenset({"y", "yes", "1", "ok", "confirm"})
_NO_TOKENS = frozenset({"n", "no", "0", "cancel", "reject", ""})


class TerminalChannel(ConfirmationChannel):
    """ConfirmationChannel that reads from stdin and writes to stdout.

    Args:
        reader: Callable invoked once per `request` to fetch the operator's
            line. Defaults to the builtin `input`. Tests inject a stub.
        writer: Stream to print prompts and outcome notifications to.
            Defaults to `sys.stdout`.
        min_timeout_seconds: Floor on the asyncio timeout passed through
            from `PendingSignal.expires_at` (a non-positive remaining
            window collapses to immediate timeout). Defaults to 0.
    """

    def __init__(
        self,
        *,
        reader: Callable[[str], str] | None = None,
        writer: IO[str] | None = None,
        min_timeout_seconds: float = 0.0,
    ) -> None:
        self._reader = reader or input
        self._writer = writer or sys.stdout
        self._min_timeout = max(0.0, min_timeout_seconds)

    # — ConfirmationChannel —

    async def request(self, pending: PendingSignal) -> ConfirmationResponse:
        prompt = _format_prompt(pending)
        remaining = max(
            self._min_timeout,
            (pending.expires_at - datetime.now(timezone.utc)).total_seconds(),
        )
        if remaining <= 0:
            self._write(f"{prompt}\n[expired before prompt could fire]\n")
            return ConfirmationResponse(signal_id=pending.id, decision="timeout", raw=None)

        try:
            raw = await asyncio.wait_for(
                asyncio.to_thread(self._reader, prompt),
                timeout=remaining,
            )
        except asyncio.TimeoutError:
            self._write(f"\n[timeout — signal {pending.id} expired before reply]\n")
            log_event(
                _logger,
                "hitl.channel.terminal.timeout",
                signal_id=pending.id,
                correlation_id=pending.correlation_id,
            )
            return ConfirmationResponse(signal_id=pending.id, decision="timeout", raw=None)
        except EOFError:
            # Treat EOF as `no` — operator closed the prompt without answering.
            log_event(
                _logger,
                "hitl.channel.terminal.eof",
                signal_id=pending.id,
                correlation_id=pending.correlation_id,
            )
            return ConfirmationResponse(signal_id=pending.id, decision="no", raw=None)

        decision = _interpret(raw)
        log_event(
            _logger,
            "hitl.channel.terminal.replied",
            signal_id=pending.id,
            decision=decision,
            correlation_id=pending.correlation_id,
        )
        return ConfirmationResponse(signal_id=pending.id, decision=decision, raw=raw)

    async def notify_outcome(
        self,
        pending: PendingSignal,
        outcome: str,
        details: str | None = None,
    ) -> None:
        line = f"[outcome] {pending.symbol} {pending.side} {pending.id} → {outcome}"
        if details:
            line += f" ({details})"
        self._write(line + "\n")

    async def replay_pending(self, pendings: list[PendingSignal]) -> None:
        if not pendings:
            return
        self._write(f"[replay] {len(pendings)} pending signal(s) recovered from disk:\n")
        for sig in pendings:
            self._write(f"  - {sig.id} {sig.symbol} {sig.side} expires_at={sig.expires_at.isoformat()}\n")

    # — internals —

    def _write(self, text: str) -> None:
        try:
            self._writer.write(text)
            self._writer.flush()
        except (BrokenPipeError, ValueError):
            # Stdout closed; nothing to do — fall back to log.
            log_event(_logger, "hitl.channel.terminal.write_failed", text=text[:200])


def _format_prompt(pending: PendingSignal) -> str:
    return (
        f"[{pending.created_at.strftime('%H:%M:%S')}] SIGNAL {pending.id} — "
        f"{pending.strategy_name} {pending.side} {pending.symbol} "
        f"@ {pending.ref_price:,.0f} × {pending.proposed_volume} "
        f"= {pending.proposed_notional_vnd:,} VND; "
        f"expires {pending.expires_at.strftime('%H:%M:%S')}. Confirm? [y/N]: "
    )


def _interpret(raw: str) -> str:
    token = (raw or "").strip().lower()
    if token in _YES_TOKENS:
        return "yes"
    if token in _NO_TOKENS:
        return "no"
    # Anything else: default to safe path (no).
    return "no"
