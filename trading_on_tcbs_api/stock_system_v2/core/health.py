"""Health-check orchestrator (Phase 6).

Single entry point — `health_check(...)` — answers:

  - Is auth valid?
  - How fresh is the most recent closed bar (per-symbol newest)?
  - How many open orders does the tracker see?
  - What was the last logged error?

Wires together the primitives that already exist (`StockAuth`,
`OrderTracker`, `DataProvider`) so the operator's "should I let it
trade?" question is one call, not five.

Designed to never raise; every failure is captured as a `HealthCheck`
row with status `unknown` or `fail`. The whole point is for a tool
layer / dashboard to call this in a tight loop without exception
plumbing.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from trading_on_tcbs_api.stock_system_v2 import config
from trading_on_tcbs_api.stock_system_v2.execution.order_tracker import OrderTracker
from trading_on_tcbs_api.stock_system_v2.schemas.health import (
    HealthCheck,
    HealthStatus,
)


def health_check(
    *,
    auth: Any = None,
    tracker: OrderTracker | None = None,
    data_dir: str | None = None,
    last_error: str | None = None,
) -> HealthStatus:
    """Build a `HealthStatus` snapshot.

    Args:
        auth: Optional `StockAuth` (or anything with `.validate() -> bool`).
            Skipped when None — `auth_valid` falls back to False with a
            `note="auth not provided"` check.
        tracker: Optional `OrderTracker`. Defaults to a fresh one — the
            `recover_open_orders()` call only reads the ledger, no writes.
        data_dir: Override `Settings.data_dir` (mostly for tests).
        last_error: Free-form last-error string. The autotrader's main
            loop should pass its most recent caught exception message;
            None implies "no recent errors I'm aware of."

    Returns:
        `HealthStatus` with `ok=True` only when every check is `ok`.
    """
    checks: list[HealthCheck] = []

    auth_valid = _check_auth(auth, checks)
    open_orders = _check_open_orders(tracker, checks)
    data_age = _check_data_freshness(data_dir or config.DATA_DIR, checks)

    if last_error:
        checks.append(HealthCheck(name="last_error", status="warn", note=last_error))

    fail_levels = {"fail", "unknown"}
    ok = not any(c.status in fail_levels for c in checks)

    return HealthStatus(
        ok=ok,
        checks=checks,
        last_error=last_error,
        open_orders=open_orders,
        data_freshness_seconds=data_age,
        auth_valid=auth_valid,
    )


# — sub-checks —

def _check_auth(auth: Any, checks: list[HealthCheck]) -> bool:
    if auth is None:
        checks.append(HealthCheck(name="auth", status="warn", note="auth not provided"))
        return False
    try:
        valid = bool(auth.validate())
    except Exception as exc:  # noqa: BLE001 — health-check must not raise
        checks.append(HealthCheck(name="auth", status="fail", note=f"validate raised: {exc!r}"))
        return False
    checks.append(
        HealthCheck(name="auth", status="ok" if valid else "fail",
                    note="token accepted" if valid else "token rejected")
    )
    return valid


def _check_open_orders(tracker: OrderTracker | None, checks: list[HealthCheck]) -> int:
    try:
        t = tracker or OrderTracker()
        rows = t.recover_open_orders()
    except Exception as exc:  # noqa: BLE001
        checks.append(HealthCheck(name="tracker", status="fail", note=f"recover failed: {exc!r}"))
        return 0
    n = len(rows)
    checks.append(
        HealthCheck(
            name="open_orders",
            status="ok" if n == 0 else "warn",
            note=f"{n} open order(s)",
        )
    )
    return n


def _check_data_freshness(data_dir: str, checks: list[HealthCheck]) -> int | None:
    """Find the newest closed-bar timestamp across cached CSVs.

    Returns the age in seconds. Skipped (returns None) if the directory
    doesn't exist or has no CSV cache files yet.
    """
    if not data_dir or not os.path.isdir(data_dir):
        checks.append(
            HealthCheck(name="data_freshness", status="unknown",
                        note=f"data_dir not found: {data_dir}")
        )
        return None
    newest_ts: datetime | None = None
    files = [f for f in os.listdir(data_dir) if f.endswith("_1D.csv")]
    if not files:
        checks.append(HealthCheck(name="data_freshness", status="warn", note="no cached CSVs"))
        return None
    for fname in files[:200]:  # cheap upper bound; we only need the max
        path = os.path.join(data_dir, fname)
        try:
            df = pd.read_csv(path, usecols=["time"])
            if df.empty:
                continue
            ts = pd.to_datetime(df["time"], errors="coerce").max()
            if pd.isna(ts):
                continue
            if newest_ts is None or ts.to_pydatetime() > newest_ts:
                newest_ts = ts.to_pydatetime()
        except (OSError, ValueError, KeyError, pd.errors.ParserError):
            continue
    if newest_ts is None:
        checks.append(HealthCheck(name="data_freshness", status="warn", note="no parseable CSVs"))
        return None
    if newest_ts.tzinfo is None:
        newest_ts = newest_ts.replace(tzinfo=timezone.utc)
    age = int((datetime.now(timezone.utc) - newest_ts).total_seconds())
    status: str = "ok" if age < 60 * 60 * 36 else "warn"  # 36h covers a long weekend
    checks.append(
        HealthCheck(name="data_freshness", status=status,  # type: ignore[arg-type]
                    note=f"newest closed bar {age}s ago")
    )
    return age
