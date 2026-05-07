"""Correlation-id contextvar (Phase 6).

A correlation id is a short string that ties together every log/metric
line emitted while serving one logical request. The autotrader generates
one per scan; backtests get one per `Backtester.run`; orders get one per
`place_order`. The id flows through `contextvars.ContextVar` so any code
called inside a `with_correlation(...)` block can read the active id
without explicit threading.

Outside any `with_correlation` block, `current_correlation_id()` returns
`None` and log lines simply omit the field.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def current_correlation_id() -> str | None:
    """Return the active correlation id, or `None` if not in a scope."""
    return _correlation_id.get()


def new_correlation_id(prefix: str = "req") -> str:
    """Generate a fresh `<prefix>_<hex8>` id without setting it."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


@contextmanager
def with_correlation(cid: str | None = None, *, prefix: str = "req") -> Iterator[str]:
    """Set the correlation id for the duration of a `with` block.

    Args:
        cid: Use an explicit id (e.g. agent-supplied request id). When
            `None`, a fresh `new_correlation_id(prefix)` is generated.
        prefix: Prefix for the auto-generated id. Helps grep — use
            `scan`, `backtest`, `order`, etc.

    Yields:
        The active correlation id (the same one log lines will carry).

    Example:
        >>> with with_correlation(prefix="scan") as cid:
        ...     scanner.scan(symbols)   # every log inside carries `cid`
    """
    resolved = cid or new_correlation_id(prefix=prefix)
    token = _correlation_id.set(resolved)
    try:
        yield resolved
    finally:
        _correlation_id.reset(token)
