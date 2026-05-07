"""Fixture-backed `DataProvider` substitute.

Mirrors the production `DataProvider` constructor signature
(`auth`, `reconciler`) and the subset of methods downstream code calls
(`get_historical_data`, `clear_realtime_cache`, `prefetch_realtime_prices`,
`get_realtime_price`, `is_trading_day`). Returns frames already validated
against `OHLCVFrame`, so tests can compose this with the real
`IndicatorEngine`, `MarketScanner`, and `Backtester` without monkeypatching.

Two construction modes:

- **From a fixtures directory** — pass `fixtures_dir` and the provider will
  read `<symbol>.csv` for each requested symbol. The CSV must already conform
  to the OHLCV contract (columns, dtypes, monotonic time).
- **From an in-memory dict** — pass `frames={'HPG': df, ...}`. Convenient for
  unit tests that build their own frames via `make_ohlcv`.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
from trading_on_tcbs_api.stock_system_v2.data_ingest.reconciler import PriceReconciler
from trading_on_tcbs_api.stock_system_v2.schemas import validate_ohlcv


class FakeDataProvider:
    """Drop-in `DataProvider` test double."""

    def __init__(
        self,
        *,
        auth: object | None = None,
        reconciler: Optional[PriceReconciler] = None,
        fixtures_dir: Optional[str] = None,
        frames: Optional[dict[str, pd.DataFrame]] = None,
        trading_day_override: Optional[bool] = None,
    ) -> None:
        if (fixtures_dir is None) == (frames is None):
            raise ValueError("Provide exactly one of fixtures_dir or frames")
        self.auth = auth
        self.reconciler = reconciler
        self._fixtures_dir = fixtures_dir
        self._frames: dict[str, pd.DataFrame] = {
            sym: df.copy() for sym, df in (frames or {}).items()
        }
        self._live_prices: dict[str, float] = {}
        self._trading_day_override = trading_day_override

    # --- DataProvider parity surface --------------------------------

    def clear_realtime_cache(self) -> None:
        self._live_prices.clear()

    def prefetch_realtime_prices(self, symbols: list[str]) -> None:
        # No-op: tests set live prices explicitly via `set_live_price`.
        pass

    def set_live_price(self, symbol: str, price: float) -> None:
        self._live_prices[symbol] = float(price)

    def get_realtime_price(self, symbol: str) -> Optional[float]:
        if symbol in self._live_prices:
            return self._live_prices[symbol]
        if self.auth is not None and hasattr(self.auth, "get_realtime_price"):
            return self.auth.get_realtime_price(symbol)
        return None

    def is_trading_day(self, d) -> bool:
        if self._trading_day_override is not None:
            return self._trading_day_override
        return d.weekday() < 5

    def get_expected_fresh_date(self):
        # Tests don't exercise cache-staleness logic on the fake; return
        # something safe that compares correctly against fixture timestamps.
        return datetime.now().date()

    # --- Core: `get_historical_data` --------------------------------

    def get_historical_data(
        self,
        symbol: str,
        days: int = 365,
        resolution: str = "1D",
        force_update: bool = False,
        include_live: bool = True,
        min_bars_required: int = 200,
    ) -> pd.DataFrame:
        df = self._load_frame(symbol)
        if df is None or df.empty:
            empty = pd.DataFrame()
            validate_ohlcv(empty, symbol=symbol, resolution=resolution, require_non_empty=False)
            return empty

        df = df.copy()
        # Truncate to the requested window so the interface matches production.
        cutoff = pd.Timestamp(datetime.now()) - pd.Timedelta(days=days)
        df = df[df["time"] >= cutoff].reset_index(drop=True)

        if include_live and self.auth is not None:
            live = self.get_realtime_price(symbol)
            if live and live > 0:
                last_time = df.iloc[-1]["time"]
                next_day = pd.Timestamp(last_time) + pd.Timedelta(days=1)
                partial = pd.DataFrame(
                    [{
                        "time": next_day,
                        "open": live,
                        "high": live,
                        "low": live,
                        "close": live,
                        "volume": np.nan,
                        "is_partial": True,
                    }]
                )
                df = pd.concat([df, partial], ignore_index=True)

        validate_ohlcv(df, symbol=symbol, resolution=resolution, require_non_empty=False)

        if self.reconciler is not None and self.auth is not None:
            try:
                self.reconciler.check(symbol=symbol, df=df, auth=self.auth)
            except Exception:
                # Match production: `severity='warn'` lets the data through.
                pass

        return df

    # --- Internal ---------------------------------------------------

    def _load_frame(self, symbol: str) -> Optional[pd.DataFrame]:
        if symbol in self._frames:
            return self._frames[symbol]
        if self._fixtures_dir is None:
            return None
        path = os.path.join(self._fixtures_dir, f"{symbol}.csv")
        if not os.path.exists(path):
            return None
        df = pd.read_csv(path)
        df["time"] = pd.to_datetime(df["time"])
        if "is_partial" not in df.columns:
            df["is_partial"] = False
        else:
            df["is_partial"] = df["is_partial"].astype(bool)
        # Cache so subsequent lookups are O(1).
        self._frames[symbol] = df
        return df
