"""Position reconciliation v2 (Phase 5).

The legacy `AccountManager.sync_from_api` overwrites local positions
silently when the API returns data. Phase 5 closes this hole: every sync
runs through `reconcile_position_book(local, broker)` first, and any
delta past the per-symbol threshold raises `PositionDriftError` instead
of being applied.

The exception carries a structured `details["diff"]` with the per-symbol
(local, broker) tuple so an operator can decide manually whether to
overwrite (the broker is authoritative) or pause the autotrader (a
genuine accounting bug exists). The system never decides on its own.
"""

from __future__ import annotations

from dataclasses import dataclass

from trading_on_tcbs_api.stock_system_v2.exceptions import PositionDriftError
from trading_on_tcbs_api.stock_system_v2.obs import log_event, record_metric, get_logger

_logger = get_logger("reconciler")


@dataclass(frozen=True)
class ReconcileResult:
    """Outcome of comparing two position books.

    `diff` maps `symbol → (local_qty, broker_qty)` for every symbol that
    differs by more than `threshold_shares`. Zero-vs-zero entries are
    omitted. `over_threshold` is True iff `diff` is non-empty.
    """

    diff: dict[str, tuple[int, int]]
    threshold_shares: int

    @property
    def over_threshold(self) -> bool:
        return bool(self.diff)

    @property
    def symbols(self) -> list[str]:
        return sorted(self.diff)


def reconcile_position_book(
    local: dict[str, int],
    broker: dict[str, int],
    *,
    threshold_shares: int = 0,
) -> ReconcileResult:
    """Compute the symbol-level diff between two position books.

    Args:
        local: Mapping `symbol → quantity` from the in-process book
            (mock account, paper-trade simulator, etc.).
        broker: Mapping `symbol → quantity` from the live broker sync.
        threshold_shares: Per-symbol tolerance. A diff of `<= threshold`
            shares is treated as no drift and excluded from the result.
            Default 0 — exact match required.

    Returns:
        `ReconcileResult` carrying every drifting symbol.
    """
    universe = set(local) | set(broker)
    diff: dict[str, tuple[int, int]] = {}
    for sym in universe:
        loc = int(local.get(sym, 0))
        brk = int(broker.get(sym, 0))
        if abs(loc - brk) > threshold_shares:
            diff[sym] = (loc, brk)
    return ReconcileResult(diff=diff, threshold_shares=threshold_shares)


def assert_no_drift(
    local: dict[str, int],
    broker: dict[str, int],
    *,
    threshold_shares: int = 0,
) -> None:
    """Raise `PositionDriftError` if any symbol drifts past the threshold.

    Convenience wrapper for the autotrader's hot path: call this and
    catch `PositionDriftError` to halt the loop when state diverges.

    Raises:
        PositionDriftError: with `details["diff"]` populated and
            `details["threshold"]` carrying the configured tolerance.
    """
    result = reconcile_position_book(local, broker, threshold_shares=threshold_shares)
    if result.over_threshold:
        log_event(
            _logger, "reconcile.drift",
            level=40, diff=dict(result.diff),
            threshold=threshold_shares, n_symbols=len(result.diff),
        )
        record_metric("drift.events", 1.0, n_symbols=len(result.diff))
        raise PositionDriftError(
            f"Position book drift across {len(result.diff)} symbol(s): {result.symbols}",
            details={
                "diff": dict(result.diff),
                "threshold": threshold_shares,
                "symbols": result.symbols,
            },
        )
