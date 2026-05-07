"""Structured JSON logger (Phase 6).

`get_logger(name)` returns a stdlib logger pre-configured with
`JSONFormatter` and a stdout `StreamHandler`. Every call to
`log_event(logger, event, **fields)` produces one JSON line shaped like:

    {
      "ts": "2026-05-08T14:23:01.123Z",
      "level": "INFO",
      "logger": "v2.scanner",
      "event": "scan.signal",
      "correlation_id": "scan_a1b2c3d4",
      "symbol": "HPG",
      "strategy": "RSI Reversal",
      "signal": "BUY"
    }

The `event` field is the grep handle — use stable, dotted names. The
free-form kwargs become top-level keys (numeric, string, bool, list,
dict). Anything non-JSON-serialisable is `repr()`'d.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, TypedDict

from .correlation import current_correlation_id

_CONFIGURED = False


class LogEvent(TypedDict, total=False):
    """Wire shape of one JSON log line."""

    ts: str
    level: str
    logger: str
    event: str
    correlation_id: str | None


class JSONFormatter(logging.Formatter):
    """Renders one log record as a single JSON line.

    The `event` and any structured fields are pulled from the record's
    `extra` dict (set via `logger.info(msg, extra=...)` or via
    `log_event`). The legacy `msg` is used as the `event` when no
    explicit event is supplied.
    """

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event", record.getMessage()),
        }
        cid = getattr(record, "correlation_id", None) or current_correlation_id()
        if cid is not None:
            payload["correlation_id"] = cid

        # Merge structured extra fields. We skip stdlib internals (`args`,
        # `msg`, `created`, etc.) by inspecting `__dict__` against the
        # default record attributes captured once below.
        for key, value in record.__dict__.items():
            if key in _RESERVED_KEYS or key in payload:
                continue
            payload[key] = _safe(value)

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=_safe, ensure_ascii=False)


def _safe(value: Any) -> Any:
    """Best-effort JSON-coerce arbitrary objects."""
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in value.items()}
    if hasattr(value, "model_dump"):
        try:
            return value.model_dump()
        except Exception:  # noqa: BLE001
            return repr(value)
    return repr(value)


_RESERVED_KEYS = frozenset(
    vars(
        logging.LogRecord(
            "x",
            logging.INFO,
            "x",
            0,
            "x",
            None,
            None,
        )
    )
) | {"event", "correlation_id"}


def configure_logging(
    *,
    stream: Any = None,
    level: int = logging.INFO,
    force: bool = False,
) -> None:
    """Wire `JSONFormatter` onto the V2 root logger.

    Args:
        stream: Where to write. Default: `sys.stdout`. Tests pass an
            in-memory `StringIO` to capture lines.
        level: Minimum level. INFO by default; set to DEBUG via
            `LOG_LEVEL=DEBUG` env.
        force: When True, drop existing handlers and reconfigure. Used
            by tests that need to swap streams between cases.
    """
    global _CONFIGURED
    if _CONFIGURED and not force:
        return
    root = logging.getLogger("v2")
    if force:
        for h in list(root.handlers):
            root.removeHandler(h)
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(JSONFormatter())
    root.addHandler(handler)
    env_level = os.environ.get("LOG_LEVEL", "").upper()
    if env_level in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        root.setLevel(getattr(logging, env_level))
    else:
        root.setLevel(level)
    root.propagate = False
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a `v2.<name>` logger, configuring on first call."""
    if not _CONFIGURED:
        configure_logging()
    return logging.getLogger(f"v2.{name}")


_LOGRECORD_RESERVED = frozenset({
    "message", "asctime", "msg", "args", "levelname", "levelno", "pathname",
    "filename", "module", "exc_info", "exc_text", "stack_info", "lineno",
    "funcName", "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "name",
})


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    """Emit one structured log line.

    `event` is the stable grep handle; `fields` flows into the JSON as
    top-level keys. Reserved `LogRecord` attributes (`message`, `args`,
    etc.) are silently renamed with a `field_` prefix so callers don't
    have to memorise the stdlib's namespace.
    """
    safe_fields: dict[str, Any] = {}
    for k, v in fields.items():
        if k in _LOGRECORD_RESERVED:
            safe_fields[f"field_{k}"] = v
        else:
            safe_fields[k] = v
    extra = {"event": event, **safe_fields}
    logger.log(level, event, extra=extra)
