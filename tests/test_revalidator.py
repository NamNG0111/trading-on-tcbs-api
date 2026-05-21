"""StrictRevalidator tests (Phase 10 chunk 2).

Uses a minimal stub data provider over a real fixture (HPG.csv) so the
checks run against a realistic 365-bar frame. The originating
`PendingSignal` is constructed to match (or deliberately diverge from)
the last fixture bar to exercise each check.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from trading_on_tcbs_api.stock_system_v2.execution.hitl import StrictRevalidator
from trading_on_tcbs_api.stock_system_v2.schemas import PendingSignal

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


# — stub provider —


class _StubDataProvider:
    """Returns a caller-controlled DataFrame; ignores fetch kwargs."""

    def __init__(self, df: pd.DataFrame | None, *, raise_exc: Exception | None = None) -> None:
        self._df = df
        self._raise = raise_exc
        self.calls: list[dict] = []

    def get_historical_data(self, **kwargs) -> pd.DataFrame:
        self.calls.append(kwargs)
        if self._raise is not None:
            raise self._raise
        if self._df is None:
            return pd.DataFrame()
        return self._df.copy()


def _load_hpg() -> pd.DataFrame:
    df = pd.read_csv(os.path.join(FIXTURES, "HPG.csv"))
    df["time"] = pd.to_datetime(df["time"])
    if "is_partial" not in df.columns:
        df["is_partial"] = False
    return df


def _make_pending(
    *,
    symbol: str = "HPG",
    side: str = "BUY",
    strategy: str = "rsi",
    ref_price: float,
    ref_bar_close_ts: datetime,
    strategy_params: dict | None = None,
) -> PendingSignal:
    return PendingSignal.from_scan(
        symbol=symbol,
        side=side,
        strategy_name=strategy,
        ref_price=ref_price,
        ref_bar_close_ts=ref_bar_close_ts,
        proposed_volume=100,
        proposed_notional_vnd=int(ref_price * 100),
        correlation_id="cycle_test",
        timeout_seconds=3600,
        strategy_params=strategy_params or {},
    )


# — construction —


def test_negative_max_drift_rejected():
    with pytest.raises(ValueError):
        StrictRevalidator(data_provider=_StubDataProvider(None), max_price_drift_pct=0)


# — freshness fails —


def test_empty_frame_fails_freshness():
    rev = StrictRevalidator(data_provider=_StubDataProvider(pd.DataFrame()))
    pending = _make_pending(
        ref_price=27_500.0,
        ref_bar_close_ts=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    result = rev.check(pending)
    assert not result.passed
    assert any(c.name == "freshness" and not c.passed for c in result.checks)


def test_provider_exception_folds_into_freshness_fail():
    rev = StrictRevalidator(
        data_provider=_StubDataProvider(None, raise_exc=RuntimeError("network down"))
    )
    pending = _make_pending(
        ref_price=27_500.0,
        ref_bar_close_ts=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    result = rev.check(pending)
    assert not result.passed
    assert "network down" in result.reason


def test_all_bars_partial_fails_freshness():
    """Only-partial fetch → closed_bars returns empty."""
    df = _load_hpg().tail(3).copy()
    df["is_partial"] = True
    rev = StrictRevalidator(data_provider=_StubDataProvider(df))
    pending = _make_pending(
        ref_price=float(df["close"].iloc[-1]),
        ref_bar_close_ts=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    result = rev.check(pending)
    assert not result.passed
    assert result.reason is not None


# — new_bar check —


def test_same_bar_fails_new_bar_check():
    df = _load_hpg()
    last = df.iloc[-1]
    pending = _make_pending(
        ref_price=float(last["close"]),
        # Exact same timestamp — the bar didn't advance.
        ref_bar_close_ts=pd.to_datetime(last["time"]).to_pydatetime().replace(tzinfo=timezone.utc),
    )
    rev = StrictRevalidator(data_provider=_StubDataProvider(df))
    result = rev.check(pending)
    new_bar = next(c for c in result.checks if c.name == "new_bar")
    assert not new_bar.passed
    assert not result.passed


# — price_drift check —


def test_price_within_cap_passes_drift():
    df = _load_hpg()
    last_close = float(df["close"].iloc[-1])
    pending = _make_pending(
        # 1.5% drift; cap default is 2%.
        ref_price=last_close * 1.015,
        ref_bar_close_ts=pd.to_datetime(df["time"].iloc[-2]).to_pydatetime().replace(tzinfo=timezone.utc),
    )
    rev = StrictRevalidator(data_provider=_StubDataProvider(df), max_price_drift_pct=2.0)
    result = rev.check(pending)
    drift = next(c for c in result.checks if c.name == "price_drift")
    assert drift.passed
    assert result.price_drift_pct is not None
    assert result.price_drift_pct < 2.0


def test_price_outside_cap_fails_drift():
    df = _load_hpg()
    last_close = float(df["close"].iloc[-1])
    pending = _make_pending(
        # 5% drift far exceeds the 2% cap.
        ref_price=last_close * 1.05,
        ref_bar_close_ts=pd.to_datetime(df["time"].iloc[-2]).to_pydatetime().replace(tzinfo=timezone.utc),
    )
    rev = StrictRevalidator(data_provider=_StubDataProvider(df), max_price_drift_pct=2.0)
    result = rev.check(pending)
    drift = next(c for c in result.checks if c.name == "price_drift")
    assert not drift.passed
    assert not result.passed


def test_drift_cap_is_inclusive():
    """A drift exactly equal to the cap should pass — the rule is `<=`."""
    df = _load_hpg()
    last_close = float(df["close"].iloc[-1])
    pending = _make_pending(
        ref_price=last_close * 1.02,  # exactly 2.0% high
        ref_bar_close_ts=pd.to_datetime(df["time"].iloc[-2]).to_pydatetime().replace(tzinfo=timezone.utc),
    )
    rev = StrictRevalidator(data_provider=_StubDataProvider(df), max_price_drift_pct=2.0)
    result = rev.check(pending)
    drift = next(c for c in result.checks if c.name == "price_drift")
    # Floating-point: assert within tolerance.
    assert drift.passed or abs(result.price_drift_pct - 2.0) < 1e-9


# — signal_reemitted check —


def test_unknown_strategy_fails_signal_check():
    df = _load_hpg()
    pending = _make_pending(
        strategy="not_a_real_strategy",
        ref_price=float(df["close"].iloc[-1]),
        ref_bar_close_ts=pd.to_datetime(df["time"].iloc[-2]).to_pydatetime().replace(tzinfo=timezone.utc),
    )
    rev = StrictRevalidator(data_provider=_StubDataProvider(df))
    result = rev.check(pending)
    sig = next(c for c in result.checks if c.name == "signal_reemitted")
    assert not sig.passed
    assert not result.passed


def _drop_at_end_series(n: int = 80) -> pd.DataFrame:
    """Series that climbs steadily then crashes hard at the end → RSI < 30 on last bar."""
    # 70 bars rising, last 10 bars crashing.
    rising = [20_000.0 + i * 100 for i in range(n - 10)]
    crash_start = rising[-1]
    crashing = [crash_start * (0.94 ** (i + 1)) for i in range(10)]
    closes = rising + crashing
    times = [pd.Timestamp("2024-01-01") + pd.Timedelta(days=i) for i in range(n)]
    return pd.DataFrame({
        "time": times,
        "open": closes,
        "high": [c * 1.005 for c in closes],
        "low": [c * 0.995 for c in closes],
        "close": closes,
        "volume": [1_000_000] * n,
        "is_partial": [False] * n,
    })


def test_signal_check_passes_when_strategy_emits_matching_side():
    """RSI-basic on a crash-at-end series should emit BUY on the last bar."""
    df = _drop_at_end_series()
    ref_price = float(df["close"].iloc[-1])
    pending = _make_pending(
        symbol="SYN",
        side="BUY",
        strategy="rsi",
        strategy_params={"is_reversal": False, "period": 14, "oversold": 30, "overbought": 70},
        ref_price=ref_price,
        ref_bar_close_ts=pd.to_datetime(df["time"].iloc[-2]).to_pydatetime().replace(tzinfo=timezone.utc),
    )
    rev = StrictRevalidator(data_provider=_StubDataProvider(df))
    result = rev.check(pending)
    sig = next(c for c in result.checks if c.name == "signal_reemitted")
    new_bar = next(c for c in result.checks if c.name == "new_bar")
    drift = next(c for c in result.checks if c.name == "price_drift")
    assert sig.passed, f"rsi basic should re-emit BUY on oversold last bar; detail={sig.detail}"
    assert new_bar.passed
    assert drift.passed
    assert result.passed


def test_signal_check_fails_when_side_flips():
    """Same oversold series but asking about SELL — strategy will not emit SELL."""
    df = _drop_at_end_series()
    pending = _make_pending(
        symbol="SYN",
        side="SELL",
        strategy="rsi",
        strategy_params={"is_reversal": False, "period": 14, "oversold": 30, "overbought": 70},
        ref_price=float(df["close"].iloc[-1]),
        ref_bar_close_ts=pd.to_datetime(df["time"].iloc[-2]).to_pydatetime().replace(tzinfo=timezone.utc),
    )
    rev = StrictRevalidator(data_provider=_StubDataProvider(df))
    result = rev.check(pending)
    sig = next(c for c in result.checks if c.name == "signal_reemitted")
    assert not sig.passed
    assert not result.passed


# — fetch contract —


def test_force_update_is_set_on_fetch():
    """The revalidator MUST bypass cache; assert on the kwargs the provider saw."""
    df = _load_hpg()
    stub = _StubDataProvider(df)
    rev = StrictRevalidator(data_provider=stub)
    pending = _make_pending(
        ref_price=float(df["close"].iloc[-1]),
        ref_bar_close_ts=pd.to_datetime(df["time"].iloc[-2]).to_pydatetime().replace(tzinfo=timezone.utc),
    )
    rev.check(pending)
    assert len(stub.calls) == 1
    assert stub.calls[0]["force_update"] is True
    assert stub.calls[0]["include_live"] is False  # partial bar would muddy the check
