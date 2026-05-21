"""TelegramChannel tests (Phase 10 chunk 7).

Uses a FakeBot that records `send_message` calls and exposes a method
to simulate operator button presses. The real `Application` / polling
loop is never instantiated — we inject `bot=...` directly so the channel
skips `start()`-time application construction.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

# Skip the entire module when python-telegram-bot isn't installed.
ptb = pytest.importorskip("telegram")

from trading_on_tcbs_api.stock_system_v2.execution.hitl.channels import (
    ConfirmationChannel,
    ConfirmationResponse,
    TelegramChannel,
)
from trading_on_tcbs_api.stock_system_v2.schemas import PendingSignal


# — fake bot —


class FakeBot:
    def __init__(self, *, raise_on_send: Exception | None = None):
        self.sends: list[dict[str, Any]] = []
        self.raise_on_send = raise_on_send

    async def send_message(self, *, chat_id, text, reply_markup=None, **_kw):
        self.sends.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})
        if self.raise_on_send is not None:
            raise self.raise_on_send


def _pending(*, signal_id: str | None = None, timeout: int = 3600) -> PendingSignal:
    sig = PendingSignal.from_scan(
        symbol="HPG", side="BUY", strategy_name="rsi",
        ref_price=27_500.0,
        ref_bar_close_ts=datetime(2026, 5, 19, 7, 30, tzinfo=timezone.utc),
        proposed_volume=100, proposed_notional_vnd=2_750_000,
        correlation_id="cycle_tg", timeout_seconds=timeout,
    )
    if signal_id is not None:
        sig = sig.model_copy(update={"id": signal_id})
    return sig


def _run(coro):
    return asyncio.run(coro)


# — construction —


def test_requires_token_or_bot_or_application():
    with pytest.raises(ValueError):
        TelegramChannel(chat_id=42)


def test_satisfies_protocol():
    chan = TelegramChannel(bot=FakeBot(), chat_id=42)
    assert isinstance(chan, ConfirmationChannel)


# — request: yes / no via callback —


def test_request_resolves_on_yes_callback():
    chan = TelegramChannel(bot=FakeBot(), chat_id=42)
    pending = _pending(signal_id="ps_yes")

    async def scenario():
        # Start the request, then simulate the operator tap.
        request_task = asyncio.create_task(chan.request(pending))
        await asyncio.sleep(0)  # let request register its waiter
        await chan._dispatch_callback("ps_yes", "yes")
        return await request_task

    resp = _run(scenario())
    assert isinstance(resp, ConfirmationResponse)
    assert resp.decision == "yes"


def test_request_resolves_on_no_callback():
    chan = TelegramChannel(bot=FakeBot(), chat_id=42)
    pending = _pending(signal_id="ps_no")

    async def scenario():
        request_task = asyncio.create_task(chan.request(pending))
        await asyncio.sleep(0)
        await chan._dispatch_callback("ps_no", "no")
        return await request_task

    resp = _run(scenario())
    assert resp.decision == "no"


# — request: timeout —


def test_request_times_out_when_no_callback_fires():
    chan = TelegramChannel(bot=FakeBot(), chat_id=42)
    pending = _pending(signal_id="ps_to").model_copy(
        update={"expires_at": datetime.now(timezone.utc) + timedelta(seconds=0.2)},
    )

    async def scenario():
        return await chan.request(pending)

    resp = _run(scenario())
    assert resp.decision == "timeout"


def test_request_returns_timeout_when_already_expired():
    chan = TelegramChannel(bot=FakeBot(), chat_id=42)
    pending = _pending(signal_id="ps_past").model_copy(
        update={"expires_at": datetime.now(timezone.utc) - timedelta(seconds=10)},
    )
    resp = _run(chan.request(pending))
    assert resp.decision == "timeout"


# — request: send call shape —


def test_request_sends_message_with_inline_keyboard():
    bot = FakeBot()
    chan = TelegramChannel(bot=bot, chat_id=42)
    pending = _pending(signal_id="ps_keyboard")

    async def scenario():
        task = asyncio.create_task(chan.request(pending))
        await asyncio.sleep(0)
        await chan._dispatch_callback("ps_keyboard", "yes")
        await task

    _run(scenario())
    assert len(bot.sends) == 1
    sent = bot.sends[0]
    assert sent["chat_id"] == 42
    assert "ps_keyboard" in sent["text"]
    assert "HPG" in sent["text"]
    # Inline keyboard has yes/no buttons with stable callback_data.
    kb = sent["reply_markup"]
    assert kb is not None
    rows = kb.inline_keyboard
    assert len(rows) == 1 and len(rows[0]) == 2
    callback_payloads = sorted(b.callback_data for b in rows[0])
    assert callback_payloads == ["ps_keyboard:no", "ps_keyboard:yes"]


def test_request_without_start_raises():
    chan = TelegramChannel(token="dummy", chat_id=42)  # bot is None until start()
    with pytest.raises(RuntimeError):
        _run(chan.request(_pending()))


def test_send_failure_propagates_and_unregisters_waiter():
    bot = FakeBot(raise_on_send=RuntimeError("net down"))
    chan = TelegramChannel(bot=bot, chat_id=42)
    with pytest.raises(RuntimeError):
        _run(chan.request(_pending(signal_id="ps_fail")))
    assert chan._waiters == {}


# — notify_outcome —


def test_notify_outcome_sends_one_message():
    bot = FakeBot()
    chan = TelegramChannel(bot=bot, chat_id=42)
    _run(chan.notify_outcome(_pending(signal_id="ps_outcome"), "submitted", "bo_42"))
    assert len(bot.sends) == 1
    text = bot.sends[0]["text"]
    assert "ps_outcome" in text
    assert "submitted" in text
    assert "bo_42" in text


def test_notify_outcome_swallows_send_errors():
    """Outcome notifications must never re-raise — the disk row already won."""
    bot = FakeBot(raise_on_send=RuntimeError("net down"))
    chan = TelegramChannel(bot=bot, chat_id=42)
    # Does not raise.
    _run(chan.notify_outcome(_pending(), "submitted"))


# — replay_pending —


def test_replay_pending_sends_header_plus_one_message_per_signal():
    bot = FakeBot()
    chan = TelegramChannel(bot=bot, chat_id=42)
    a = _pending(signal_id="ps_a")
    b = _pending(signal_id="ps_b")
    _run(chan.replay_pending([a, b]))
    # 1 header + 2 signal prompts.
    assert len(bot.sends) == 3
    assert "2 pending" in bot.sends[0]["text"]
    assert "ps_a" in bot.sends[1]["text"]
    assert "ps_b" in bot.sends[2]["text"]


def test_replay_pending_no_op_on_empty_list():
    bot = FakeBot()
    chan = TelegramChannel(bot=bot, chat_id=42)
    _run(chan.replay_pending([]))
    assert bot.sends == []


# — orphan callback —


def test_orphan_callback_does_not_crash():
    """A button press for a signal not currently in waiters is a no-op."""
    chan = TelegramChannel(bot=FakeBot(), chat_id=42)
    _run(chan._dispatch_callback("ps_never_seen", "yes"))


# — stop cleans up —


def test_stop_resolves_pending_waiters_as_no():
    """If the operator shuts down mid-prompt, the future must unblock."""
    chan = TelegramChannel(bot=FakeBot(), chat_id=42)

    async def scenario():
        task = asyncio.create_task(chan.request(_pending(signal_id="ps_during_stop")))
        await asyncio.sleep(0)  # let the waiter register
        await chan.stop()
        return await task

    resp = _run(scenario())
    assert resp.decision == "no"
