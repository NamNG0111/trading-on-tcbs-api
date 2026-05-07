"""Tests for `PriceReconciler` (Phase 1, ADR-001 Option B)."""

from __future__ import annotations

import pytest

from trading_on_tcbs_api.stock_system_v2.data_ingest.reconciler import (
    PriceReconciler,
    PriceReconciliationError,
)
from tests.conftest import make_ohlcv


class _StubAuth:
    token = "stub"


def _const_fetcher(value):
    def fetch(auth, symbol):
        return value
    return fetch


def test_check_passes_when_within_threshold(capsys):
    df = make_ohlcv(n=20)
    last = float(df["close"].iloc[-1])
    reconciler = PriceReconciler(
        threshold_bps=50.0,
        ref_price_fetcher=_const_fetcher(last * 1.001),  # +10 bps
    )
    result = reconciler.check(symbol="HPG", df=df, auth=_StubAuth())
    assert result is not None
    assert result.agreed is True
    # secondary = primary * 1.001 → spread = (primary - secondary)/secondary ≈ -10 bps
    assert abs(abs(result.spread_bps) - 10.0) < 0.5
    # No warning printed when agreed.
    captured = capsys.readouterr()
    assert "DIVERGED" not in captured.out


def test_check_warns_when_beyond_threshold(capsys):
    df = make_ohlcv(n=20)
    last = float(df["close"].iloc[-1])
    reconciler = PriceReconciler(
        threshold_bps=10.0,
        ref_price_fetcher=_const_fetcher(last * 1.01),  # +100 bps
    )
    result = reconciler.check(symbol="HPG", df=df, auth=_StubAuth())
    assert result is not None
    assert result.agreed is False
    captured = capsys.readouterr()
    assert "DIVERGED" in captured.out


def test_check_raises_when_severity_raise():
    df = make_ohlcv(n=20)
    last = float(df["close"].iloc[-1])
    reconciler = PriceReconciler(
        threshold_bps=10.0,
        severity="raise",
        ref_price_fetcher=_const_fetcher(last * 1.01),
    )
    with pytest.raises(PriceReconciliationError):
        reconciler.check(symbol="HPG", df=df, auth=_StubAuth())


def test_check_skips_when_no_ref_price():
    df = make_ohlcv(n=20)
    reconciler = PriceReconciler(ref_price_fetcher=_const_fetcher(None))
    assert reconciler.check(symbol="HPG", df=df, auth=_StubAuth()) is None


def test_check_skips_partial_bar():
    """The reconciler must compare against the last *closed* bar, not the
    partial bar — otherwise a normal intraday move would routinely trip."""
    df = make_ohlcv(n=20, with_partial=True)
    last_closed = float(df.loc[~df["is_partial"], "close"].iloc[-1])
    # Set ref price equal to last closed close → spread 0; partial-bar close
    # is 0.2% above, which would trip if (incorrectly) used.
    reconciler = PriceReconciler(
        threshold_bps=5.0,
        ref_price_fetcher=_const_fetcher(last_closed),
    )
    result = reconciler.check(symbol="HPG", df=df, auth=_StubAuth())
    assert result is not None
    assert result.agreed is True


def test_history_records_every_check():
    df = make_ohlcv(n=10)
    reconciler = PriceReconciler(ref_price_fetcher=_const_fetcher(float(df["close"].iloc[-1])))
    reconciler.check(symbol="HPG", df=df, auth=_StubAuth())
    reconciler.check(symbol="TCB", df=df, auth=_StubAuth())
    assert len(reconciler.history) == 2
    assert {r.symbol for r in reconciler.history} == {"HPG", "TCB"}


def test_check_series_reports_worst_spread():
    reconciler = PriceReconciler(threshold_bps=50.0)
    p = [100.0, 100.0, 100.0]
    s = [100.0, 100.5, 100.0]  # middle: +50 bps in absolute terms is -49.75
    result = reconciler.check_series(
        symbol="HPG",
        primary_series=p,
        secondary_series=s,
    )
    assert "worst-of-3" in result.note
    assert abs(result.spread_bps) > 40  # picked the middle index


def test_invalid_threshold_rejected():
    with pytest.raises(ValueError):
        PriceReconciler(threshold_bps=0)
    with pytest.raises(ValueError):
        PriceReconciler(threshold_bps=-1)
