"""health_check() tests (Phase 6)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from trading_on_tcbs_api.stock_system_v2.core.health import health_check
from trading_on_tcbs_api.stock_system_v2.execution.order_tracker import OrderTracker
from trading_on_tcbs_api.stock_system_v2.schemas import OrderRequest


class _FakeAuth:
    def __init__(self, valid: bool, raises=None):
        self._valid = valid
        self._raises = raises

    def validate(self) -> bool:
        if self._raises is not None:
            raise self._raises
        return self._valid


def _seed_data_dir(tmp_path: Path, *, age_hours: float = 1.0) -> Path:
    d = tmp_path / "stocks"
    d.mkdir()
    ts = datetime.now(timezone.utc) - timedelta(hours=age_hours)
    df = pd.DataFrame(
        {
            "time": [ts.strftime("%Y-%m-%d %H:%M:%S")],
            "open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0],
            "volume": [1.0], "is_partial": [False],
        }
    )
    df.to_csv(d / "HPG_1D.csv", index=False)
    return d


def test_all_green(tmp_path: Path):
    data_dir = _seed_data_dir(tmp_path, age_hours=1.0)
    tracker = OrderTracker(str(tmp_path / "ledger.csv"))
    status = health_check(auth=_FakeAuth(True), tracker=tracker, data_dir=str(data_dir))
    assert status.ok
    assert status.auth_valid
    assert status.open_orders == 0
    assert status.data_freshness_seconds is not None
    assert status.last_error is None


def test_auth_fail_flips_ok_false(tmp_path: Path):
    data_dir = _seed_data_dir(tmp_path)
    tracker = OrderTracker(str(tmp_path / "ledger.csv"))
    status = health_check(auth=_FakeAuth(False), tracker=tracker, data_dir=str(data_dir))
    assert not status.ok
    assert not status.auth_valid


def test_open_order_warns(tmp_path: Path):
    data_dir = _seed_data_dir(tmp_path)
    tracker = OrderTracker(str(tmp_path / "ledger.csv"))
    tracker.register_pending(OrderRequest(symbol="HPG", side="BUY", price=28000, volume=100))
    status = health_check(auth=_FakeAuth(True), tracker=tracker, data_dir=str(data_dir))
    assert status.open_orders == 1
    # WARN does not flip ok=False (only fail/unknown do).
    assert status.ok


def test_last_error_surfaces(tmp_path: Path):
    data_dir = _seed_data_dir(tmp_path)
    tracker = OrderTracker(str(tmp_path / "ledger.csv"))
    status = health_check(
        auth=_FakeAuth(True), tracker=tracker, data_dir=str(data_dir),
        last_error="data fetch timed out",
    )
    assert status.last_error == "data fetch timed out"
    assert any(c.name == "last_error" for c in status.checks)


def test_missing_data_dir(tmp_path: Path):
    tracker = OrderTracker(str(tmp_path / "ledger.csv"))
    status = health_check(
        auth=_FakeAuth(True), tracker=tracker,
        data_dir=str(tmp_path / "does_not_exist"),
    )
    assert status.data_freshness_seconds is None
    # unknown trips ok=False so the operator sees there's a problem.
    assert not status.ok


def test_stale_data_warns_but_doesnt_fail(tmp_path: Path):
    data_dir = _seed_data_dir(tmp_path, age_hours=72.0)  # 3 days old
    tracker = OrderTracker(str(tmp_path / "ledger.csv"))
    status = health_check(auth=_FakeAuth(True), tracker=tracker, data_dir=str(data_dir))
    # 72h > 36h threshold → WARN check, but ok stays True (warn-only).
    assert status.ok
    freshness = next(c for c in status.checks if c.name == "data_freshness")
    assert freshness.status == "warn"
