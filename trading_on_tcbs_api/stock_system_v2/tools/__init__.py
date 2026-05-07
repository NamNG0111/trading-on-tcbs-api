"""Agent-callable tool layer (Phase 7).

Public API:
    tool(...)                — decorator that registers a handler
    TOOLS                    — registry mapping name → ToolDefinition
    ToolResponse             — envelope every tool returns
    ToolError                — raise-typed failure with structured `details`
    invoke(name, **kwargs)   — dispatch by name (used by the MCP server + tests)

The handlers themselves live in `tools.handlers.*`. Importing this
package is enough to register every tool — handler modules pull
themselves into `TOOLS` by side-effect on import.
"""

from .registry import TOOLS, ToolDefinition, invoke, list_tools, tool
from .response import ToolError, ToolResponse

# Eager import every handler so the registry is populated.
from .handlers import (  # noqa: F401  (registration side-effects)
    account as _account,
    backtest as _backtest,
    data as _data,
    health as _health,
    orders as _orders,
    scanner as _scanner,
    strategies as _strategies,
)

__all__ = [
    "TOOLS",
    "ToolDefinition",
    "ToolError",
    "ToolResponse",
    "invoke",
    "list_tools",
    "tool",
]
