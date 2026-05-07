"""MCP server entry point (Phase 7).

Exposes every tool in the V2 registry over MCP stdio. Run as:

    python -m trading_on_tcbs_api.stock_system_v2.tools.mcp_server

…and configure your Claude client (Claude Code, Claude Desktop, …) to
spawn that command. The server walks `TOOLS`, registers each entry by
its name + JSON schema, and routes incoming `call_tool` requests
through the same `invoke()` dispatcher tests use — which means MCP
adds zero code paths beyond serialisation.

The `mcp` SDK is imported lazily so the rest of the V2 package
(handlers, smoke tests) does not pull it in. To run the server:

    pip install mcp

Tests do not need MCP installed; they call `invoke(...)` directly,
which is exactly what this entry point ends up doing.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from trading_on_tcbs_api.stock_system_v2.obs import get_logger, log_event
from trading_on_tcbs_api.stock_system_v2.tools import TOOLS, ToolError, invoke

_logger = get_logger("tools.mcp")


def _bootstrap_context() -> None:
    """Build a default `ToolContext` and install it.

    Production composition root. Tests build their own context with
    fakes and call `set_context` before invoking any tool.
    """
    from trading_on_tcbs_api.stock_system_v2.auth.auth import StockAuth
    from trading_on_tcbs_api.stock_system_v2.core.indicator_engine import IndicatorEngine
    from trading_on_tcbs_api.stock_system_v2.data_ingest.data_provider import DataProvider
    from trading_on_tcbs_api.stock_system_v2.execution.order_manager import OrderManager
    from trading_on_tcbs_api.stock_system_v2.execution.order_tracker import OrderTracker
    from trading_on_tcbs_api.stock_system_v2.execution.pre_trade_validator import (
        PreTradeValidator,
    )
    from trading_on_tcbs_api.stock_system_v2.finance.account_manager import AccountManager
    from trading_on_tcbs_api.stock_system_v2.settings import Settings
    from trading_on_tcbs_api.stock_system_v2.tools.context import (
        ToolContext,
        set_context,
    )

    settings = Settings.load()
    auth = StockAuth()
    auth.validate()  # best-effort; tools surface auth status via health_check

    tracker = OrderTracker()
    set_context(
        ToolContext(
            settings=settings,
            data_provider=DataProvider(auth=auth),
            indicator_engine=IndicatorEngine(),
            account=AccountManager(initial_cash=100_000_000),
            order_manager=OrderManager(
                auth=auth,
                safe_mode=True,
                execution_disabled=settings.execution_disabled,
                tracker=tracker,
            ),
            order_tracker=tracker,
            validator=PreTradeValidator(universe=tuple(settings.symbols)),
            auth=auth,
        )
    )


async def main() -> None:
    """Run the MCP stdio server.

    Imports `mcp` lazily so `python -m …mcp_server --help` and the
    rest of the V2 package don't pull in the SDK when it isn't needed.
    """
    try:
        from mcp.server import Server  # type: ignore[import-not-found]
        from mcp.server.stdio import stdio_server  # type: ignore[import-not-found]
        from mcp.types import TextContent, Tool  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover — runtime-only
        sys.stderr.write(
            "MCP SDK not installed. Run: pip install mcp\n"
            f"Underlying error: {exc}\n"
        )
        sys.exit(2)

    _bootstrap_context()
    server = Server("trading-on-tcbs-v2")

    @server.list_tools()  # type: ignore[misc]
    async def _list_tools() -> list[Tool]:
        return [
            Tool(
                name=spec.name,
                description=_with_metadata(spec.description, spec.side_effecting),
                inputSchema=spec.input_schema(),
            )
            for spec in TOOLS.values()
        ]

    @server.call_tool()  # type: ignore[misc]
    async def _call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        try:
            envelope = invoke(name, arguments)
            payload = envelope.model_dump(mode="json")
        except ToolError as exc:
            log_event(_logger, "tool.mcp.error", level=40, tool=name, code=exc.code)
            payload = {"error": exc.to_dict()}
        return [TextContent(type="text", text=json.dumps(payload, default=str))]

    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def _with_metadata(description: str, side_effecting: bool) -> str:
    marker = "side-effecting" if side_effecting else "read-only / idempotent"
    return f"[{marker}] {description}"


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(main())
