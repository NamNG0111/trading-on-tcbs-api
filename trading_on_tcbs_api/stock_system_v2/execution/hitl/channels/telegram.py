"""Telegram confirmation channel (Phase 10).

Mobile-friendly HITL channel backed by `python-telegram-bot` v20+. Sends
each `PendingSignal` as a message with ✅ / ❌ inline-keyboard buttons.
The operator's tap resolves an `asyncio.Future` that `request()` is
awaiting; the same `Application` keeps long-polling for further updates.

Wiring (production):

    chan = TelegramChannel(token=settings.telegram_bot_token, chat_id=settings.telegram_chat_id)
    await chan.start()
    coordinator = HITLCoordinator(channel=chan, ...)

Wiring (tests):

    chan = TelegramChannel(bot=FakeBot(), chat_id=42)
    # Skip `chan.start()` — no polling. Resolve callbacks manually via
    # `await chan._dispatch_callback(signal_id, "yes")`.

The module imports `telegram` at the top; install `python-telegram-bot>=20`
or treat the import error as "Telegram channel not available".
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler

from trading_on_tcbs_api.stock_system_v2.execution.hitl.channels.base import (
    ConfirmationChannel,
    ConfirmationResponse,
    Decision,
)
from trading_on_tcbs_api.stock_system_v2.obs import get_logger, log_event
from trading_on_tcbs_api.stock_system_v2.schemas import PendingSignal

_logger = get_logger("hitl.channel.telegram")


def _callback_data(signal_id: str, decision: str) -> str:
    """Stable callback_data payload — `<signal_id>:<yes|no>`.

    Telegram limits this string to 64 bytes; our `ps_<12 hex>` ids plus
    suffix sit comfortably below that.
    """
    return f"{signal_id}:{decision}"


def _parse_callback(data: str) -> tuple[str, Decision] | None:
    try:
        sid, dec = data.split(":", 1)
    except ValueError:
        return None
    if dec not in ("yes", "no"):
        return None
    return sid, dec  # type: ignore[return-value]


class TelegramChannel(ConfirmationChannel):
    """Telegram-backed confirmation channel.

    Args:
        token: Bot token from @BotFather. Either this or `bot` must be set.
        chat_id: Target chat id (int or str). Same operator inbox for
            both prompts and outcome notifications.
        bot: Pre-built `telegram.Bot` (or compatible duck) for tests.
            When provided, `start()` skips application construction.
        application: Pre-built `Application` (advanced). When omitted
            and `bot` is None, `start()` builds one from `token`.
        min_timeout_seconds: Floor on the asyncio timeout. Default 0.

    Lifecycle:
      1. `await chan.start()` once per process (builds + starts polling).
      2. `request` / `notify_outcome` / `replay_pending` as needed.
      3. `await chan.stop()` for clean shutdown.
    """

    def __init__(
        self,
        *,
        token: str | None = None,
        chat_id: int | str,
        bot: Any = None,
        application: Application | None = None,
        min_timeout_seconds: float = 0.0,
    ) -> None:
        if token is None and bot is None and application is None:
            raise ValueError("TelegramChannel requires `token`, `bot`, or `application`.")
        self._token = token
        self.chat_id = chat_id
        self._bot = bot
        self._app = application
        self._min_timeout = max(0.0, min_timeout_seconds)
        self._waiters: dict[str, asyncio.Future[Decision]] = {}

    # — lifecycle —

    async def start(self) -> None:
        """Initialize the bot + start long-polling.

        No-op when the channel was constructed with a pre-built bot
        (test path). Idempotent: calling twice is harmless.
        """
        if self._app is None and self._bot is None:
            assert self._token is not None
            self._app = Application.builder().token(self._token).build()
        if self._app is not None:
            self._app.add_handler(CallbackQueryHandler(self._on_callback))
            await self._app.initialize()
            await self._app.start()
            if self._app.updater is not None:
                await self._app.updater.start_polling()
            self._bot = self._app.bot
        log_event(_logger, "hitl.channel.telegram.started", chat_id=str(self.chat_id))

    async def stop(self) -> None:
        """Stop polling + shut the application down. Cancels any waiter."""
        # Resolve any outstanding waiters as `no` so the coordinator
        # unblocks rather than hanging on shutdown.
        for sid, fut in list(self._waiters.items()):
            if not fut.done():
                fut.set_result("no")
            self._waiters.pop(sid, None)
        if self._app is not None:
            if self._app.updater is not None:
                await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
        log_event(_logger, "hitl.channel.telegram.stopped")

    # — ConfirmationChannel —

    async def request(self, pending: PendingSignal) -> ConfirmationResponse:
        if self._bot is None:
            raise RuntimeError("TelegramChannel.start() must be awaited before request().")

        remaining = max(
            self._min_timeout,
            (pending.expires_at - datetime.now(timezone.utc)).total_seconds(),
        )
        if remaining <= 0:
            return ConfirmationResponse(signal_id=pending.id, decision="timeout", raw=None)

        loop = asyncio.get_event_loop()
        future: asyncio.Future[Decision] = loop.create_future()
        self._waiters[pending.id] = future

        try:
            await self._bot.send_message(
                chat_id=self.chat_id,
                text=_format_prompt(pending),
                reply_markup=_keyboard(pending.id),
            )
        except Exception as exc:
            self._waiters.pop(pending.id, None)
            log_event(
                _logger, "hitl.channel.telegram.send_failed",
                signal_id=pending.id, error=str(exc),
            )
            raise

        try:
            decision = await asyncio.wait_for(future, timeout=remaining)
        except asyncio.TimeoutError:
            return ConfirmationResponse(signal_id=pending.id, decision="timeout", raw=None)
        finally:
            self._waiters.pop(pending.id, None)

        return ConfirmationResponse(signal_id=pending.id, decision=decision, raw=decision)

    async def notify_outcome(
        self,
        pending: PendingSignal,
        outcome: str,
        details: str | None = None,
    ) -> None:
        if self._bot is None:
            return
        line = f"{_emoji_for(outcome)} *{pending.symbol}* {pending.side} `{pending.id}` → *{outcome}*"
        if details:
            line += f"\n{details}"
        try:
            await self._bot.send_message(chat_id=self.chat_id, text=line)
        except Exception as exc:  # transient network — already recorded on disk
            log_event(
                _logger, "hitl.channel.telegram.notify_failed",
                signal_id=pending.id, error=str(exc),
            )

    async def replay_pending(self, pendings: list[PendingSignal]) -> None:
        if self._bot is None or not pendings:
            return
        header = f"[replay] {len(pendings)} pending signal(s) recovered from disk:"
        try:
            await self._bot.send_message(chat_id=self.chat_id, text=header)
        except Exception as exc:
            log_event(_logger, "hitl.channel.telegram.replay_failed", error=str(exc))
            return
        for sig in pendings:
            try:
                await self._bot.send_message(
                    chat_id=self.chat_id,
                    text=_format_prompt(sig),
                    reply_markup=_keyboard(sig.id),
                )
            except Exception as exc:
                log_event(
                    _logger, "hitl.channel.telegram.replay_msg_failed",
                    signal_id=sig.id, error=str(exc),
                )

    # — internals —

    async def _on_callback(self, update: Any, _context: Any) -> None:
        """Telegram callback handler — resolves the awaiting `request`."""
        q = update.callback_query
        if q is None or q.data is None:
            return
        parsed = _parse_callback(q.data)
        try:
            await q.answer()
        except Exception:  # noqa: BLE001 — answer() is best-effort
            pass
        if parsed is None:
            return
        await self._dispatch_callback(parsed[0], parsed[1])

    async def _dispatch_callback(self, signal_id: str, decision: Decision) -> None:
        """Resolve the future for `signal_id`. Public for tests.

        No-op when the signal isn't being awaited (e.g. the operator
        tapped an old button after the signal already timed out).
        """
        fut = self._waiters.get(signal_id)
        if fut is None or fut.done():
            log_event(
                _logger, "hitl.channel.telegram.callback_orphan",
                signal_id=signal_id, decision=decision,
            )
            return
        fut.set_result(decision)


# — formatting helpers —


def _keyboard(signal_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("✅ Confirm", callback_data=_callback_data(signal_id, "yes")),
            InlineKeyboardButton("❌ Reject", callback_data=_callback_data(signal_id, "no")),
        ]]
    )


def _format_prompt(pending: PendingSignal) -> str:
    return (
        f"🔔 SIGNAL {pending.id}\n"
        f"{pending.strategy_name} {pending.side} {pending.symbol}\n"
        f"@ {pending.ref_price:,.0f} × {pending.proposed_volume} "
        f"= {pending.proposed_notional_vnd:,} VND\n"
        f"expires {pending.expires_at.strftime('%H:%M:%S')} UTC"
    )


def _emoji_for(outcome: str) -> str:
    return {
        "submitted": "✅",
        "rejected": "❌",
        "expired": "⏰",
        "stale": "🌫",
        "failed": "🚫",
    }.get(outcome, "ℹ️")
