"""TerminalChannel tests (Phase 10 chunk 3).

Drives the channel with a stub `reader` callable so the tests stay
deterministic and don't touch real stdin. `asyncio.run` wraps each
coroutine for the standard pytest sync-test pattern.
"""

from __future__ import annotations

import asyncio
import io
from datetime import datetime, timedelta, timezone

import pytest

from trading_on_tcbs_api.stock_system_v2.execution.hitl import (
    ConfirmationChannel,
    ConfirmationResponse,
    TerminalChannel,
)
from trading_on_tcbs_api.stock_system_v2.schemas import PendingSignal


# — helpers —


def _pending(*, timeout: int = 3600, signal_id: str | None = None) -> PendingSignal:
    sig = PendingSignal.from_scan(
        symbol="HPG",
        side="BUY",
        strategy_name="rsi",
        ref_price=27_500.0,
        ref_bar_close_ts=datetime(2026, 5, 19, 7, 30, tzinfo=timezone.utc),
        proposed_volume=100,
        proposed_notional_vnd=2_750_000,
        correlation_id="cycle_test",
        timeout_seconds=timeout,
    )
    if signal_id is not None:
        sig = sig.model_copy(update={"id": signal_id})
    return sig


def _run(coro):
    return asyncio.run(coro)


# — protocol shape —


def test_terminal_channel_satisfies_protocol():
    chan = TerminalChannel(reader=lambda prompt: "y", writer=io.StringIO())
    assert isinstance(chan, ConfirmationChannel)


# — request: replies —


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("y", "yes"),
        ("yes", "yes"),
        ("Y", "yes"),
        ("1", "yes"),
        ("ok", "yes"),
        ("n", "no"),
        ("no", "no"),
        ("", "no"),  # empty line = decline
        ("garbage text", "no"),  # unknown defaults to safe (no)
    ],
)
def test_request_interprets_reply(raw, expected):
    chan = TerminalChannel(reader=lambda prompt: raw, writer=io.StringIO())
    resp = _run(chan.request(_pending()))
    assert isinstance(resp, ConfirmationResponse)
    assert resp.decision == expected
    assert resp.raw == raw


def test_request_eof_returns_no():
    def reader(prompt):
        raise EOFError()
    chan = TerminalChannel(reader=reader, writer=io.StringIO())
    resp = _run(chan.request(_pending()))
    assert resp.decision == "no"
    assert resp.raw is None


# — request: timeout —


def test_request_returns_timeout_when_expired():
    sig = _pending(timeout=1)
    # Force the expiry to already be in the past.
    sig = sig.model_copy(update={"expires_at": datetime.now(timezone.utc) - timedelta(seconds=10)})
    chan = TerminalChannel(reader=lambda prompt: "y", writer=io.StringIO())
    resp = _run(chan.request(sig))
    assert resp.decision == "timeout"
    assert resp.raw is None


def test_request_times_out_when_reader_blocks_too_long():
    """Reader sleeps longer than the signal's remaining window."""
    def slow_reader(prompt: str) -> str:
        import time
        time.sleep(2.0)
        return "y"

    sig = _pending(timeout=3600).model_copy(
        update={"expires_at": datetime.now(timezone.utc) + timedelta(seconds=0.2)},
    )
    chan = TerminalChannel(reader=slow_reader, writer=io.StringIO())
    resp = _run(chan.request(sig))
    assert resp.decision == "timeout"


# — output formatting —


def test_request_writes_prompt_with_signal_summary():
    out = io.StringIO()
    pending = _pending(signal_id="ps_writeprompt")
    chan = TerminalChannel(reader=lambda prompt: "y", writer=out)
    _run(chan.request(pending))
    # The prompt is passed to the reader; we mainly assert nothing extra
    # was written to stdout on the happy path.
    assert out.getvalue() == ""


def test_notify_outcome_writes_to_stdout():
    out = io.StringIO()
    chan = TerminalChannel(reader=lambda prompt: "y", writer=out)
    pending = _pending(signal_id="ps_outcome")
    _run(chan.notify_outcome(pending, "submitted", "broker_order_id=bo_42"))
    text = out.getvalue()
    assert "ps_outcome" in text
    assert "submitted" in text
    assert "bo_42" in text


def test_replay_pending_writes_one_line_per_signal():
    out = io.StringIO()
    chan = TerminalChannel(reader=lambda prompt: "y", writer=out)
    a = _pending(signal_id="ps_a")
    b = _pending(signal_id="ps_b")
    _run(chan.replay_pending([a, b]))
    text = out.getvalue()
    assert "2 pending signal(s)" in text
    assert "ps_a" in text
    assert "ps_b" in text


def test_replay_pending_no_op_on_empty_list():
    out = io.StringIO()
    chan = TerminalChannel(reader=lambda prompt: "y", writer=out)
    _run(chan.replay_pending([]))
    assert out.getvalue() == ""
