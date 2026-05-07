"""Tool registry + invocation dispatcher.

Each handler module decorates one or more functions with `@tool(...)`.
The decorator wraps the function so that:

  - Input kwargs are validated through the declared `input_model`.
  - The active correlation id (auto-generated when absent) is attached
    to the response.
  - Typed `StockSystemError` subclasses convert into matching
    `ToolError` codes; everything else becomes `INTERNAL`.
  - The output is wrapped in `ToolResponse[OutputModel]`.

Handlers stay pure: they receive a typed Pydantic input, return a
typed Pydantic result. The protocol-level concerns (correlation,
errors, freshness) are owned by this registry.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable, Type

from pydantic import BaseModel, ValidationError

from trading_on_tcbs_api.stock_system_v2.exceptions import (
    AuthExpiredError,
    DataFetchError,
    DuplicateOrderError,
    InsufficientHistoryError,
    InvalidParameterError,
    OrderRejectedError,
    PositionDriftError,
    RiskLimitViolatedError,
    StaleCacheError,
    StockSystemError,
)
from trading_on_tcbs_api.stock_system_v2.obs import (
    current_correlation_id,
    log_event,
    record_metric,
    with_correlation,
)
from trading_on_tcbs_api.stock_system_v2.obs.logger import get_logger

from .response import ToolError, ToolResponse

_logger = get_logger("tools")

Handler = Callable[..., Any]

_EXCEPTION_TO_CODE: dict[type[Exception], str] = {
    InvalidParameterError: "INVALID_PARAMS",
    InsufficientHistoryError: "INSUFFICIENT_HISTORY",
    StaleCacheError: "DATA_STALE",
    DataFetchError: "DATA_FETCH_FAILED",
    AuthExpiredError: "AUTH_EXPIRED",
    DuplicateOrderError: "DUPLICATE_ORDER",
    OrderRejectedError: "ORDER_REJECTED",
    RiskLimitViolatedError: "RISK_VIOLATED",
    PositionDriftError: "POSITION_DRIFT",
    StockSystemError: "INTERNAL",
}

_RETRIABLE_CODES = frozenset({"DATA_FETCH_FAILED", "DATA_STALE"})


@dataclass(frozen=True)
class ToolDefinition:
    """Static metadata for one registered tool."""

    name: str
    description: str
    input_model: Type[BaseModel]
    output_model: Type[BaseModel]
    side_effecting: bool
    handler: Handler

    @property
    def idempotent(self) -> bool:
        """Convenience: read-only tools are idempotent by definition.

        Side-effecting tools may also be idempotent (e.g. `submit_order`
        keyed on `client_order_id`). Today we conservatively flag every
        side-effecting tool as non-idempotent for the agent prompt.
        """
        return not self.side_effecting

    def input_schema(self) -> dict[str, Any]:
        """JSON Schema for the input arguments (used by the MCP adapter)."""
        return self.input_model.model_json_schema()


TOOLS: dict[str, ToolDefinition] = {}


def tool(
    name: str,
    *,
    input_model: Type[BaseModel],
    output_model: Type[BaseModel],
    side_effecting: bool = False,
    description: str | None = None,
) -> Callable[[Handler], Handler]:
    """Decorator that registers a handler in `TOOLS`.

    Args:
        name: Stable tool id used by clients. Lowercase + underscores.
        input_model: Pydantic model the kwargs validate against.
        output_model: Pydantic model the handler returns. The decorator
            wraps the return value in `ToolResponse[output_model]`.
        side_effecting: True for write tools (`submit_order`, etc.).
            Read-only tools default to False; the agent prompt uses
            this flag to know whether to double-check before calling.
        description: Override the tool's docstring as the description.

    Example:
        >>> class GetQuoteIn(BaseModel):
        ...     symbol: str
        >>> class GetQuoteOut(BaseModel):
        ...     symbol: str
        ...     price: float
        >>> @tool("get_quote", input_model=GetQuoteIn, output_model=GetQuoteOut)
        ... def get_quote(req: GetQuoteIn) -> GetQuoteOut:
        ...     return GetQuoteOut(symbol=req.symbol, price=…)
    """

    def decorator(fn: Handler) -> Handler:
        doc = description or (inspect.getdoc(fn) or f"Tool {name}")
        definition = ToolDefinition(
            name=name,
            description=doc,
            input_model=input_model,
            output_model=output_model,
            side_effecting=side_effecting,
            handler=fn,
        )
        if name in TOOLS:
            raise ValueError(f"Tool {name!r} already registered.")
        TOOLS[name] = definition
        return fn

    return decorator


def list_tools() -> list[ToolDefinition]:
    """Return every registered tool sorted by name (stable for the MCP listing)."""
    return [TOOLS[k] for k in sorted(TOOLS)]


def invoke(
    name: str,
    arguments: dict[str, Any] | None = None,
    *,
    correlation_id: str | None = None,
) -> ToolResponse[Any]:
    """Run a tool by name, wrapping the call in protocol concerns.

    Args:
        name: Registered tool id.
        arguments: Raw kwargs (typically from a JSON envelope). Validated
            by the tool's `input_model`.
        correlation_id: Use a caller-supplied id (e.g. the MCP request
            id). When None a fresh one is generated for this call.

    Returns:
        `ToolResponse[output_model]`.

    Raises:
        ToolError: with `code="UNKNOWN_TOOL"` when `name` isn't
            registered, `INVALID_PARAMS` on Pydantic validation
            failure, or a protocol-mapped code for typed
            `StockSystemError` subclasses.
    """
    if name not in TOOLS:
        raise ToolError(
            "UNKNOWN_TOOL",
            f"Tool {name!r} is not registered.",
            details={"available": sorted(TOOLS)},
        )
    spec = TOOLS[name]

    with with_correlation(correlation_id, prefix="tool") as cid:
        log_event(_logger, "tool.invoke", tool=name, side_effecting=spec.side_effecting)
        record_metric("tools.invoked", 1.0, tool=name, side_effecting=spec.side_effecting)

        try:
            req = spec.input_model.model_validate(arguments or {})
        except ValidationError as exc:
            raise ToolError(
                "INVALID_PARAMS",
                f"Input validation failed for {name}: {exc.errors()[0]['msg']}",
                details={"errors": exc.errors()},
            ) from exc

        try:
            result = spec.handler(req)
        except ToolError:
            record_metric("tools.error", 1.0, tool=name, code="ToolError")
            raise
        except StockSystemError as exc:
            code = _code_for(exc)
            log_event(_logger, "tool.error", tool=name, code=code, level=40, cause=str(exc))
            record_metric("tools.error", 1.0, tool=name, code=code)
            raise ToolError(
                code,
                str(exc),
                retriable=code in _RETRIABLE_CODES,
                details=exc.details,
            ) from exc
        except (ValueError, TypeError) as exc:
            log_event(_logger, "tool.error", tool=name, code="INVALID_PARAMS", level=40)
            record_metric("tools.error", 1.0, tool=name, code="INVALID_PARAMS")
            raise ToolError("INVALID_PARAMS", str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 — translate to typed envelope
            log_event(_logger, "tool.error", tool=name, code="INTERNAL", level=50, cause=repr(exc))
            record_metric("tools.error", 1.0, tool=name, code="INTERNAL")
            raise ToolError("INTERNAL", repr(exc)) from exc

        if not isinstance(result, spec.output_model):
            raise ToolError(
                "INTERNAL",
                f"Tool {name} returned {type(result).__name__}, expected {spec.output_model.__name__}",
            )

        envelope: ToolResponse[Any] = ToolResponse(
            result=result,
            correlation_id=cid or current_correlation_id() or "",
            data_freshness_seconds=getattr(result, "data_freshness_seconds", None),
        )
        log_event(_logger, "tool.complete", tool=name)
        return envelope


def _code_for(exc: Exception) -> str:
    for cls, code in _EXCEPTION_TO_CODE.items():
        if isinstance(exc, cls):
            return code
    return "INTERNAL"
