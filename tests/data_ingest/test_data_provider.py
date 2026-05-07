"""Tests for `DataProvider` Phase-1 invariants.

Network-free: we monkeypatch the vnstock `Quote.history` boundary so the test
exercises caching, schema validation, partial-bar marking, and the
`min_bars_required` cache-validity rule without hitting the wire.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from trading_on_tcbs_api.stock_system_v2.data_ingest import data_provider as dp_mod
from trading_on_tcbs_api.stock_system_v2.data_ingest.data_provider import DataProvider
from trading_on_tcbs_api.stock_system_v2.schemas.ohlcv import OHLCVSchemaError


@pytest.fixture
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(dp_mod.config, "DATA_DIR", str(tmp_path))
    return str(tmp_path)


@pytest.fixture
def fake_history(monkeypatch):
    """Patch vnstock Quote so DataProvider gets a deterministic frame."""

    def _build(n_bars: int = 250, scale: int = 1) -> pd.DataFrame:
        # vnstock-KBS returns thousand-VND for HoSE equities, so we deliver
        # raw values that need ×1000 scaling.
        times = pd.date_range(end=datetime.now().date() - timedelta(days=1), periods=n_bars, freq="B")
        closes = np.linspace(25, 35, n_bars) * scale  # raw thousand-VND
        return pd.DataFrame(
            {
                "time": times,
                "open": closes,
                "high": closes * 1.01,
                "low": closes * 0.99,
                "close": closes,
                "volume": np.arange(n_bars, dtype=float) + 100_000,
            }
        )

    state = {"frame": _build()}

    class _FakeQuote:
        def __init__(self, symbol: str, source: str = "KBS"):
            self.symbol = symbol

        def history(self, start, end, interval):
            return state["frame"].copy()

    monkeypatch.setattr(dp_mod, "Quote", _FakeQuote)
    monkeypatch.setattr(dp_mod.time, "sleep", lambda *_: None)  # skip rate-limit sleep
    return state


def test_fetch_applies_metadata_scale_not_heuristic(isolated_data_dir, fake_history):
    """vnstock raw 25–35 must scale to 25_000–35_000 via `get_symbol_meta`,
    independent of the old `<500` heuristic."""
    provider = DataProvider(auth=None)
    df = provider.get_historical_data("HPG", days=400, include_live=False, min_bars_required=10)
    assert not df.empty
    assert df["close"].min() > 1_000  # scaled to VND
    assert df["close"].max() < 100_000


def test_fetch_returns_schema_compliant_frame(isolated_data_dir, fake_history):
    provider = DataProvider(auth=None)
    df = provider.get_historical_data("HPG", days=400, include_live=False, min_bars_required=10)
    required = {"time", "open", "high", "low", "close", "volume", "is_partial"}
    assert required.issubset(df.columns)
    assert df["is_partial"].dtype == bool or df["is_partial"].isin([True, False]).all()
    assert (~df["is_partial"]).all(), "no partial bars expected when include_live=False"


def test_idempotent_history_two_calls(isolated_data_dir, fake_history):
    """A backtest run twice in a row must produce identical historical bars
    (Phase 1 DoD: 'identical historical bars on the same symbol two days in a row')."""
    provider = DataProvider(auth=None)
    df1 = provider.get_historical_data("HPG", days=400, include_live=False, min_bars_required=10)
    df2 = provider.get_historical_data("HPG", days=400, include_live=False, min_bars_required=10)
    pd.testing.assert_frame_equal(df1, df2)


def test_min_bars_required_invalidates_shallow_cache(isolated_data_dir, fake_history, monkeypatch):
    """Cache with fewer than `min_bars_required` bars must be treated as a miss."""
    provider = DataProvider(auth=None)
    # Seed a tiny cache (50 bars).
    fake_history["frame"] = fake_history["frame"].iloc[:50].copy()
    df = provider.get_historical_data("HPG", days=400, include_live=False, min_bars_required=10)
    assert len(df) == 50

    # Re-request with a higher floor; the cache should be rejected, but the
    # source still has only 50 bars, so we get 50 again — what matters is
    # that the code path triggers a re-fetch rather than silently returning
    # a too-shallow cache.
    fetches = {"n": 0}

    real_quote = dp_mod.Quote

    class _CountingQuote(real_quote):  # type: ignore[misc]
        def history(self, *a, **kw):
            fetches["n"] += 1
            return super().history(*a, **kw)

    monkeypatch.setattr(dp_mod, "Quote", _CountingQuote)
    provider.get_historical_data("HPG", days=400, include_live=False, min_bars_required=200)
    assert fetches["n"] == 1, "shallow cache should have been re-fetched"


def test_partial_bar_carries_nan_volume(isolated_data_dir, fake_history, monkeypatch):
    """Phase 1 item 3: today's appended bar must have volume=NaN, never 0,
    so volume strategies do not silently misfire."""

    class _StubAuth:
        token = "stub"

    provider = DataProvider(auth=_StubAuth())
    # Force "today is a trading day" so the live-merge branch runs.
    monkeypatch.setattr(provider, "is_trading_day", lambda d: True)
    monkeypatch.setattr(provider, "get_realtime_price", lambda sym: 31_500.0)

    df = provider.get_historical_data("HPG", days=400, include_live=True, min_bars_required=10)
    last = df.iloc[-1]
    assert bool(last["is_partial"]) is True
    assert np.isnan(last["volume"]), f"partial-bar volume should be NaN, got {last['volume']!r}"
    assert last["close"] == 31_500.0


def test_no_partial_bar_outside_trading_hours(isolated_data_dir, fake_history, monkeypatch):
    class _StubAuth:
        token = "stub"

    provider = DataProvider(auth=_StubAuth())
    monkeypatch.setattr(provider, "is_trading_day", lambda d: False)
    df = provider.get_historical_data("HPG", days=400, include_live=True, min_bars_required=10)
    assert (~df["is_partial"]).all()


def test_reconciler_invoked_on_fetch(isolated_data_dir, fake_history):
    """ADR-001 Option B: every fetch with auth runs through the reconciler."""
    from trading_on_tcbs_api.stock_system_v2.data_ingest.reconciler import PriceReconciler

    class _StubAuth:
        token = "stub"

    captured: dict = {}

    def fake_fetcher(auth, symbol):
        captured["called_with"] = symbol
        # Return a value matching vnstock's last close to keep `agreed=True`.
        return 35_000.0

    reconciler = PriceReconciler(threshold_bps=10_000.0, ref_price_fetcher=fake_fetcher)
    provider = DataProvider(auth=_StubAuth(), reconciler=reconciler)
    provider.get_historical_data("HPG", days=400, include_live=False, min_bars_required=10)
    assert captured.get("called_with") == "HPG"
    assert len(reconciler.history) == 1


def test_reconciler_skipped_when_no_auth(isolated_data_dir, fake_history):
    """No auth → no TCBS call → no reconciliation (correctly skipped)."""
    from trading_on_tcbs_api.stock_system_v2.data_ingest.reconciler import PriceReconciler

    calls = {"n": 0}

    def fake_fetcher(auth, symbol):
        calls["n"] += 1
        return 35_000.0

    reconciler = PriceReconciler(ref_price_fetcher=fake_fetcher)
    provider = DataProvider(auth=None, reconciler=reconciler)
    provider.get_historical_data("HPG", days=400, include_live=False, min_bars_required=10)
    assert calls["n"] == 0


def test_prefetch_caches_ref_price_and_reconciler_skips_http(isolated_data_dir, fake_history, monkeypatch):
    """The 429 fix: prefetch must populate `_ref_price_cache` so that the
    default reconciler reads from memory and never issues per-symbol HTTP
    calls during a scan. Pins this against future regression."""

    class _StubAuth:
        token = "stub"

    # Mock the prefetch HTTP call to return both matchPrice and refPrice.
    fake_response_data = {
        "data": [
            {"ticker": "HPG", "matchPrice": 35_000.0, "refPrice": 34_500.0},
            {"ticker": "TCB", "matchPrice": 25_000.0, "refPrice": 24_800.0},
        ]
    }

    class _FakeResponse:
        status_code = 200

        def json(self):
            return fake_response_data

    http_calls = {"prefetch": 0, "other": 0}

    def fake_get(url, headers=None, params=None, timeout=None):
        if "tickerCommons" in url and params and len(str(params.get("tickers", "")).split(",")) > 1:
            http_calls["prefetch"] += 1
        else:
            http_calls["other"] += 1
        return _FakeResponse()

    import requests as _requests

    monkeypatch.setattr(_requests, "get", fake_get)

    provider = DataProvider(auth=_StubAuth())

    # 1. Prefetch should cache both live and ref prices in one call.
    provider.prefetch_realtime_prices(["HPG", "TCB"])
    assert http_calls["prefetch"] == 1
    assert provider._ref_price_cache == {"HPG": 34_500.0, "TCB": 24_800.0}
    assert provider._live_price_cache["HPG"]["price"] == 35_000.0

    # 2. The default reconciler must read from the cache, not the wire.
    #    We run a fetch through `get_historical_data` (which triggers
    #    `reconciler.check`) and assert no extra HTTP went out.
    http_calls_before = http_calls["other"]
    provider.get_historical_data(
        "HPG", days=400, include_live=False, min_bars_required=10
    )
    assert http_calls["other"] == http_calls_before, (
        "reconciler issued an HTTP call instead of reading the prefetched ref-price cache"
    )

    # 3. Reconciler should still have produced a result (read from cache).
    assert len(provider.reconciler.history) >= 1
    last = provider.reconciler.history[-1]
    assert last.symbol == "HPG"
    assert last.secondary_value == 34_500.0


def test_get_realtime_price_handles_429(isolated_data_dir, monkeypatch):
    """`get_realtime_price` must return None on 429 without raising."""

    class _StubAuth:
        token = "stub"

    class _Resp429:
        status_code = 429
        text = "rate limited"

        def json(self):
            return {}

    import requests as _requests

    monkeypatch.setattr(_requests, "get", lambda *a, **kw: _Resp429())

    provider = DataProvider(auth=_StubAuth())
    assert provider.get_realtime_price("HPG") is None


def test_corrupt_cache_triggers_refetch(isolated_data_dir, fake_history):
    """A malformed cache file must not crash the provider."""
    cache_path = f"{isolated_data_dir}/HPG_1D.csv"
    with open(cache_path, "w") as f:
        f.write("not,a,valid,csv\nat all\n")

    provider = DataProvider(auth=None)
    df = provider.get_historical_data("HPG", days=400, include_live=False, min_bars_required=10)
    assert not df.empty
