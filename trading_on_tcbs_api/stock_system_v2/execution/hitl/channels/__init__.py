"""Confirmation channels (Phase 10).

A channel is the bridge between a queued `PendingSignal` and a human (or
auto-mode stand-in) who decides whether the order should be placed.

Built-in channels:

  - `TerminalChannel` — blocking stdin/stdout with async timeout, for
    local development and the first soak.
  - `TelegramChannel` — Telegram Bot API with inline keyboards (Chunk 7),
    the long-term primary channel for mobile-friendly approvals.

Channels are interchangeable behind the `ConfirmationChannel` Protocol;
the coordinator instantiates one per process based on `Settings.confirmation_channel`.
"""

from trading_on_tcbs_api.stock_system_v2.execution.hitl.channels.base import (
    ConfirmationChannel,
    ConfirmationResponse,
    Decision,
)
from trading_on_tcbs_api.stock_system_v2.execution.hitl.channels.terminal import (
    TerminalChannel,
)

try:
    from trading_on_tcbs_api.stock_system_v2.execution.hitl.channels.telegram import (
        TelegramChannel,
    )
    _TELEGRAM_AVAILABLE = True
except ImportError:  # python-telegram-bot not installed — channel unavailable.
    TelegramChannel = None  # type: ignore[assignment,misc]
    _TELEGRAM_AVAILABLE = False

__all__ = [
    "ConfirmationChannel",
    "ConfirmationResponse",
    "Decision",
    "TerminalChannel",
    "TelegramChannel",
]
