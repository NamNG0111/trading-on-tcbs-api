"""ToolResponse + ToolError — the envelope every tool returns / raises.

Phase-7 contract: every tool either returns a `ToolResponse[T]` (where
`T` is the tool's typed result Pydantic model) or raises a `ToolError`.
No bare exceptions, no plain dicts. The envelope carries the
`correlation_id` and `data_freshness_seconds` fields the plan calls
out, so an agent always knows *when* the data was captured and which
request triggered the work.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ToolError(Exception):
    """Typed failure envelope.

    Args:
        code: Stable string id (e.g. `"INVALID_PARAMS"`, `"DATA_STALE"`).
        message: One-line human-readable description.
        retriable: True when the agent can retry (network blips, rate
            limits). False for hard rejections (bad input, kill-switch).
        details: Free-form structured context. Surfaces the underlying
            exception's `details` attribute when wrapping a typed
            `StockSystemError`.

    The MCP server serialises this directly; tests assert on `code`.
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retriable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retriable = retriable
        self.details: dict[str, Any] = dict(details or {})

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "retriable": self.retriable,
            "details": self.details,
        }


class ToolResponse(BaseModel, Generic[T]):
    """Envelope every tool returns.

    Fields:
        result: Typed tool-specific payload (a Pydantic model).
        correlation_id: Active correlation id at the moment the tool
            ran. Always populated — the registry sets one before
            calling the handler.
        data_freshness_seconds: Age of the data the result is based on.
            None when the tool reports state independent of any cached
            mark (e.g. `list_strategies`).
        captured_at: UTC ISO-8601 timestamp the response was built.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    result: T
    correlation_id: str
    data_freshness_seconds: int | None = None
    captured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
