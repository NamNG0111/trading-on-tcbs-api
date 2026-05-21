"""Append-only durable store for `PendingSignal` rows (Phase 10).

Mirrors the safety story `OrderTracker` uses for orders: every state
transition is one JSONL line; the live status of a signal is "the last
row whose `id` matches". A `kill -9` between transitions cannot corrupt
state — at worst the operator sees a duplicate prompt on restart, which
is the safe failure mode for a HITL system.

Storage location: `EXPORT_DIR/pending_signals.jsonl`. Override via the
`path` constructor arg for tests.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from trading_on_tcbs_api.stock_system_v2 import config
from trading_on_tcbs_api.stock_system_v2.obs import get_logger, log_event
from trading_on_tcbs_api.stock_system_v2.schemas import (
    OPEN_STATUSES,
    PendingSignal,
    PendingSignalStatus,
)

_logger = get_logger("hitl.store")


class PendingSignalStore:
    """JSONL-backed pending-signal store.

    Public API:
      - `append(signal)` — write one row (signal in current status).
      - `update_status(signal_id, status, **kwargs)` — load latest row by
        id, append a new row with the new status; returns the new signal.
      - `get(signal_id)` — return latest row for an id, or None.
      - `load_open()` — rows whose latest status is still `awaiting` /
        `confirmed`; used on startup to resume HITL.
      - `expire_overdue(now=None)` — sweep `awaiting` rows whose
        `expires_at` has passed; appends `expired` rows; returns the
        signals that were just expired.
      - `iter_all()` — every row ever written, in append order.

    The store is intentionally not thread-safe across processes; the
    coordinator owns the only writer.
    """

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self.path = Path(path) if path is not None else Path(config.EXPORT_DIR) / "pending_signals.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()
            log_event(_logger, "hitl.store.created", path=str(self.path))

    # — writes —

    def append(self, signal: PendingSignal) -> None:
        """Append `signal` as a JSON line. Caller owns the status field."""
        payload = signal.model_dump(mode="json")
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, separators=(",", ":")) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        log_event(
            _logger,
            "hitl.store.append",
            signal_id=signal.id,
            symbol=signal.symbol,
            side=signal.side,
            status=signal.status,
            correlation_id=signal.correlation_id,
        )

    def update_status(
        self,
        signal_id: str,
        status: PendingSignalStatus,
        *,
        revalidation_result=None,
        notes: str | None = None,
    ) -> PendingSignal:
        """Append a new row reflecting the new status; return the new signal.

        Raises:
            KeyError: if `signal_id` has never been written to the store.
        """
        current = self.get(signal_id)
        if current is None:
            raise KeyError(f"unknown pending signal id: {signal_id}")
        updated = current.with_status(status, revalidation_result=revalidation_result, notes=notes)
        self.append(updated)
        return updated

    # — reads —

    def get(self, signal_id: str) -> PendingSignal | None:
        """Return the latest row for `signal_id`, or None if absent."""
        latest: PendingSignal | None = None
        for row in self.iter_all():
            if row.id == signal_id:
                latest = row
        return latest

    def load_open(self) -> list[PendingSignal]:
        """Return latest-per-id rows whose status is still in OPEN_STATUSES."""
        by_id = self._latest_by_id()
        return [sig for sig in by_id.values() if sig.status in OPEN_STATUSES]

    def iter_all(self) -> Iterable[PendingSignal]:
        """Yield every row in the JSONL file in append order."""
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                yield PendingSignal.model_validate_json(line)

    # — sweeper —

    def expire_overdue(self, now: datetime | None = None) -> list[PendingSignal]:
        """Mark every `awaiting` signal whose deadline has passed as `expired`.

        Returns the list of signals that were just transitioned. Idempotent:
        re-running after all overdue rows are already expired is a no-op.
        """
        ref = now or datetime.now(timezone.utc)
        expired: list[PendingSignal] = []
        for sig in self.load_open():
            if sig.status == "awaiting" and sig.is_expired(ref):
                new = self.update_status(sig.id, "expired", notes="timeout reached before reply")
                expired.append(new)
                log_event(
                    _logger,
                    "hitl.store.expired",
                    signal_id=sig.id,
                    symbol=sig.symbol,
                    correlation_id=sig.correlation_id,
                )
        return expired

    # — internals —

    def _latest_by_id(self) -> dict[str, PendingSignal]:
        by_id: dict[str, PendingSignal] = {}
        for row in self.iter_all():
            by_id[row.id] = row
        return by_id
