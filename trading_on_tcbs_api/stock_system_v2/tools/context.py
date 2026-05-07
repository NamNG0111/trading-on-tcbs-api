"""Tool context — shared dependencies the handlers read from.

Handlers stay pure: they read deps from a single `ToolContext` value
object. The MCP server populates one at startup via `set_context(...)`;
tests build their own with fakes and pass it directly.

Why a context object instead of constructor-injection per handler?
Handlers are *functions* registered with `@tool`. They don't have
constructors. A process-wide context is the smallest surface that
keeps them pure (no globals reaching into modules) and still makes
the MCP transport a one-line `set_context(prod_context())`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from trading_on_tcbs_api.stock_system_v2.core.indicator_engine import IndicatorEngine
from trading_on_tcbs_api.stock_system_v2.data_ingest.data_provider import DataProvider
from trading_on_tcbs_api.stock_system_v2.execution.order_manager import OrderManager
from trading_on_tcbs_api.stock_system_v2.execution.order_tracker import OrderTracker
from trading_on_tcbs_api.stock_system_v2.execution.pre_trade_validator import (
    PreTradeValidator,
)
from trading_on_tcbs_api.stock_system_v2.finance.account_manager import AccountManager
from trading_on_tcbs_api.stock_system_v2.settings import Settings


@dataclass
class ToolContext:
    """Shared dependencies the handlers read at call time."""

    settings: Settings
    data_provider: DataProvider
    indicator_engine: IndicatorEngine
    account: AccountManager
    order_manager: OrderManager
    order_tracker: OrderTracker
    validator: PreTradeValidator
    auth: Any = None
    risk_tokens: dict[str, Any] = field(default_factory=dict)
    """In-memory cache of valid `RiskCheckResult`s keyed by `check_id`.

    `submit_order` looks up the token here when the agent supplies just
    a `check_id` instead of the full `RiskCheckResult`. Tokens are
    cleaned up in `submit_order` (one-shot use) but a daemon could also
    sweep expired ones periodically.
    """


_active: Optional[ToolContext] = None


def set_context(ctx: ToolContext) -> None:
    """Install a process-wide context. Last writer wins."""
    global _active
    _active = ctx


def get_context() -> ToolContext:
    """Return the active context. Raises if `set_context` hasn't been called."""
    if _active is None:
        raise RuntimeError(
            "ToolContext is not set; call tools.context.set_context(...) before invoking any tool."
        )
    return _active


def clear_context() -> None:
    """Reset the global slot. Used by tests between cases."""
    global _active
    _active = None
