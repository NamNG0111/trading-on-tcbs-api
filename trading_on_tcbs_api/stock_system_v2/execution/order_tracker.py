"""OrderTracker — append-only audit ledger + idempotency + crash recovery.

Phase-5 contract:

  - Every order has a caller-generated `client_order_id` (UUID). The
    tracker rejects a second `register_pending` for the same id with
    `DuplicateOrderError`, so even retried submits stay idempotent.
  - The ledger is append-only; every state change (PENDING / ACCEPTED /
    REJECTED / FILLED / PARTIALLY_FILLED / CANCELLED) becomes one row.
    `recover_open_orders()` reads the ledger back on startup, groups by
    `client_order_id`, and returns the rows that haven't reached a
    terminal state — the recovery primitive the autotrader uses after a
    crash.
  - Writes flush immediately so a `kill -9` between submit and log
    cannot lose state. The cost is one fsync per row; for retail-equity
    cadence that's fine.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Iterable

import pandas as pd

from trading_on_tcbs_api.stock_system_v2 import config
from trading_on_tcbs_api.stock_system_v2.exceptions import DuplicateOrderError
from trading_on_tcbs_api.stock_system_v2.obs import get_logger, log_event
from trading_on_tcbs_api.stock_system_v2.schemas import (
    OrderRequest,
    OrderResponse,
    OrderSide,
)

_logger = get_logger("tracker")

_LEDGER_COLUMNS = (
    "time",
    "client_order_id",
    "broker_order_id",
    "symbol",
    "side",
    "price",
    "volume",
    "status",
    "note",
)

_TERMINAL_STATUSES = frozenset({"FILLED", "REJECTED", "CANCELLED"})


class OrderTracker:
    """Append-only ledger with idempotency + crash recovery.

    Args:
        ledger_path: Override the default `ledger.csv` location. Tests
            pass a `tmp_path`; production uses `Settings.export_dir`.
    """

    def __init__(self, ledger_path: str | None = None) -> None:
        self.ledger_file = ledger_path or os.path.join(config.EXPORT_DIR, "ledger.csv")
        if not os.path.exists(self.ledger_file):
            self._create_ledger()
        # Pre-load every client_order_id we've seen so duplicate-submit
        # protection survives a process restart.
        self._seen_ids: set[str] = self._load_seen_ids()

    # — registration / logging —

    def register_pending(self, req: OrderRequest) -> None:
        """Reserve `req.client_order_id` and append a `PENDING` ledger row.

        Call this **before** submitting to the broker so the audit trail
        shows the intent even if the network call crashes in flight.

        Raises:
            DuplicateOrderError: if the `client_order_id` has been used.
        """
        if req.client_order_id in self._seen_ids:
            raise DuplicateOrderError(
                f"client_order_id {req.client_order_id} already registered",
                details={"client_order_id": req.client_order_id, "symbol": req.symbol},
            )
        self._seen_ids.add(req.client_order_id)
        self._append_row({
            "time": _now(),
            "client_order_id": req.client_order_id,
            "broker_order_id": "",
            "symbol": req.symbol,
            "side": req.side,
            "price": req.price,
            "volume": req.volume,
            "status": "PENDING",
            "note": "registered pre-submit",
        })

    def log_order(
        self,
        order_result: OrderResponse | dict[str, Any],
        symbol: str,
        side: OrderSide | str,
        price: float,
        volume: int,
    ) -> None:
        """Append a state-change row for an already-registered order.

        Accepts either a typed `OrderResponse` (preferred) or a legacy
        broker-result dict for back-compat with pre-Phase-3 callers.

        Raises:
            OSError: if the ledger file cannot be opened. Audit losses
                are louder than ignored failures by design.
        """
        if isinstance(order_result, OrderResponse):
            entry = {
                "time": _now(),
                "client_order_id": order_result.client_order_id,
                "broker_order_id": order_result.broker_order_id or "",
                "symbol": symbol,
                "side": side,
                "price": price,
                "volume": volume,
                "status": order_result.status,
                "note": order_result.note or "",
            }
        else:
            entry = {
                "time": _now(),
                "client_order_id": order_result.get("client_order_id", ""),
                "broker_order_id": order_result.get("order_id", ""),
                "symbol": symbol,
                "side": side,
                "price": price,
                "volume": volume,
                "status": order_result.get("status", "PENDING"),
                "note": order_result.get("note", ""),
            }
        self._append_row(entry)

    # — recovery —

    def recover_open_orders(self) -> list[dict[str, Any]]:
        """Return the latest row for every order not in a terminal status.

        On a fresh restart the autotrader calls this to learn about
        orders submitted before the crash. The list contains plain
        dicts (not `OrderResponse`) so partial / non-conformant rows
        from the legacy ledger format still surface.
        """
        if not os.path.exists(self.ledger_file):
            return []
        df = pd.read_csv(self.ledger_file)
        if df.empty:
            return []
        df["time"] = pd.to_datetime(df["time"], errors="coerce")
        df = df.sort_values("time").drop_duplicates(
            subset=["client_order_id"], keep="last"
        )
        df = df[~df["status"].isin(_TERMINAL_STATUSES)]
        df = df[df["client_order_id"].astype(str).str.strip().ne("")]
        return df.to_dict(orient="records")

    def get_history(self) -> pd.DataFrame:
        """Return the full ledger as a DataFrame; empty if nothing logged yet."""
        if os.path.exists(self.ledger_file):
            return pd.read_csv(self.ledger_file)
        return pd.DataFrame()

    # — internals —

    def _create_ledger(self) -> None:
        df = pd.DataFrame(columns=list(_LEDGER_COLUMNS))
        df.to_csv(self.ledger_file, index=False)
        log_event(_logger, "tracker.ledger.created", path=self.ledger_file)

    def _load_seen_ids(self) -> set[str]:
        if not os.path.exists(self.ledger_file):
            return set()
        try:
            df = pd.read_csv(self.ledger_file)
        except (OSError, ValueError, pd.errors.ParserError):
            return set()
        if "client_order_id" not in df.columns:
            return set()
        ids: Iterable[str] = df["client_order_id"].dropna().astype(str)
        return {i for i in ids if i.strip()}

    def _append_row(self, entry: dict[str, Any]) -> None:
        # Reorder + fill any missing columns so legacy ledgers still work.
        row = {col: entry.get(col, "") for col in _LEDGER_COLUMNS}
        df = pd.DataFrame([row])
        df.to_csv(self.ledger_file, mode="a", header=False, index=False)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
