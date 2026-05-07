"""Decisions audit trail (Phase 6).

`write_decision(payload)` appends one JSON line to `EXPORT_DIR/decisions.jsonl`.
Each row captures the full context an auditor (or future research agent)
needs to replay an order decision: the strategy that fired, the price
used, the validator findings, the account snapshot at decision time.

Append-only by design. The audit trail is the system's memory of what
it actually did; never edit existing rows.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trading_on_tcbs_api.stock_system_v2 import config

from .correlation import current_correlation_id


def _decisions_path() -> Path:
    return Path(config.EXPORT_DIR) / "decisions.jsonl"


def write_decision(payload: dict[str, Any], *, path: str | os.PathLike[str] | None = None) -> None:
    """Append one decision row to the audit log.

    Args:
        payload: Structured decision context. Common keys: `decision`
            (e.g. `"submit"`, `"skip:cash"`, `"skip:risk"`), `symbol`,
            `signal`, `strategy`, `request`, `risk_check`, `account`.
        path: Override the default `EXPORT_DIR/decisions.jsonl` location.

    The row gains a `ts` (UTC ISO 8601) and the active `correlation_id`
    automatically — callers don't need to populate them.
    """
    target = Path(path) if path is not None else _decisions_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "correlation_id": current_correlation_id(),
        **payload,
    }
    line = json.dumps(row, default=_repr_fallback, ensure_ascii=False)
    with open(target, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _repr_fallback(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        try:
            return value.model_dump()
        except Exception:  # noqa: BLE001
            pass
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:  # noqa: BLE001
            pass
    return repr(value)
