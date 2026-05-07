"""Observability primitives for V2 (Phase 6).

Every public surface in V2 emits structured JSON logs through `get_logger`.
Each request (scan, backtest, order placement) runs inside a
`with_correlation(...)` block; the contextvar-based correlation id is
attached automatically to every log line emitted in that scope.

Public API:

    get_logger(name)            → stdlib Logger configured with JSONFormatter
    log_event(logger, event, **fields)  → emit one structured event
    with_correlation(cid=None)  → context manager that sets correlation_id
    new_correlation_id(prefix)  → generate a fresh `<prefix>_<uuid>` id
    record_metric(name, value, **labels) → counter/timer event
    write_decision(payload)     → append one row to decisions.jsonl

The logger writes JSON to stdout by default. `configure_logging` is
idempotent and called automatically the first time `get_logger` is
invoked, but tests can call it explicitly to redirect output.
"""

from .correlation import (
    current_correlation_id,
    new_correlation_id,
    with_correlation,
)
from .decisions import write_decision
from .logger import (
    JSONFormatter,
    LogEvent,
    configure_logging,
    get_logger,
    log_event,
)
from .metrics import record_metric

__all__ = [
    "JSONFormatter",
    "LogEvent",
    "configure_logging",
    "current_correlation_id",
    "get_logger",
    "log_event",
    "new_correlation_id",
    "record_metric",
    "with_correlation",
    "write_decision",
]
