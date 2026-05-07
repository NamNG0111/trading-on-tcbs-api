
import os
import time
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
from vnstock.api.quote import Quote

from trading_on_tcbs_api.stock_system_v2 import config
from trading_on_tcbs_api.stock_system_v2.data_ingest.reconciler import PriceReconciler
from trading_on_tcbs_api.stock_system_v2.data_ingest.symbol_metadata import get_symbol_meta
from trading_on_tcbs_api.stock_system_v2.obs import get_logger, log_event, record_metric
from trading_on_tcbs_api.stock_system_v2.schemas import validate_ohlcv

_logger = get_logger("data")

# Default minimum bar count required before treating a cached frame as
# satisfactory. Replaces the old "5-day buffer + is_ipo flag" heuristic.
DEFAULT_MIN_BARS_REQUIRED = 200

class DataProvider:
    """
    Provides market data (Historical and Real-time) for the stock system.
    Uses 'vnstock' library (Source: KBS) for historical data as TCBS API 
    does not support history via Open API.
    """
    
    def __init__(self, auth=None, reconciler: Optional[PriceReconciler] = None):
        self.data_dir = config.DATA_DIR
        self.auth = auth  # Optional auth for real-time data
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
        self._live_price_cache = {}  # {symbol: {'price': float, 'time': datetime}}
        self._ref_price_cache: dict[str, float] = {}  # {symbol: refPrice}
        # ADR-001 Option B: cross-source reconciliation. Default reconciler
        # reads `refPrice` from this provider's prefetch cache so a 100-symbol
        # scan doesn't issue 100 extra TCBS calls (which trips the 429 rate
        # limit). Pass an explicit `reconciler` to override.
        self.reconciler = reconciler if reconciler is not None else PriceReconciler(
            ref_price_fetcher=self._cached_ref_price_fetcher,
        )

    def _cached_ref_price_fetcher(self, _auth, symbol: str) -> Optional[float]:
        """Reconciler hook: return prefetched `refPrice` without hitting the wire.

        Returns `None` if the symbol wasn't in the most recent prefetch — the
        reconciler treats that as "skip this check" rather than fail-closed,
        so a missing cache entry just defers reconciliation until the next
        prefetch covers the symbol.
        """
        return self._ref_price_cache.get(symbol)

    def clear_realtime_cache(self):
        """Manually flush the realtime + ref price caches to guarantee fresh data on the next fetch."""
        self._live_price_cache.clear()
        self._ref_price_cache.clear()

    def prefetch_realtime_prices(self, symbols: list):
        """Batch fetch realtime prices for multiple symbols to minimize API calls.

        Caches both `matchPrice` (live) and `refPrice` (prior close) per symbol
        in a single round-trip so the reconciler can read `refPrice` from
        memory instead of issuing per-symbol calls during the scan loop.
        """
        if not self.auth or not self.auth.token or not symbols:
            return

        # TCBS can typically handle up to 50 tickers in one comma-separated string
        chunk_size = 50
        for i in range(0, len(symbols), chunk_size):
            chunk = symbols[i:i+chunk_size]
            url = f"{config.BASE_URL}/tartarus/v1/tickerCommons"
            params = {'tickers': ",".join(chunk)}
            headers = {
                "Authorization": f"Bearer {self.auth.token}",
                "Content-Type": "application/json"
            }
            try:
                import requests
                response = requests.get(url, headers=headers, params=params, timeout=5)
                if response.status_code == 200:
                    data = response.json().get("data", [])
                    now = datetime.now()
                    for item in data:
                        sym = item.get('ticker')
                        match_price = item.get('matchPrice') or item.get('refPrice')
                        ref_price = item.get('refPrice')
                        if sym and match_price:
                            self._live_price_cache[sym] = {'price': match_price, 'time': now}
                        if sym and ref_price:
                            try:
                                self._ref_price_cache[sym] = float(ref_price)
                            except (TypeError, ValueError):
                                pass
                elif response.status_code == 429:
                    log_event(_logger, "data.prefetch.rate_limited", level=30)
                    return
            except (OSError, ValueError, KeyError, RuntimeError) as e:
                # Network/parse errors at the I/O edge. The cache is
                # already populated for the symbols processed before the
                # failure point, and `get_historical_data` falls back to
                # the closed-bar history when the live cache misses.
                log_event(_logger, "data.prefetch.error", level=40, cause=str(e))

    def get_realtime_price(self, symbol: str) -> Optional[float]:
        """Fetch real-time price from TCBS (Checks prefetch cache first)."""
        # Check cache (Populated by prefetch_realtime_prices)
        if symbol in self._live_price_cache:
            return self._live_price_cache[symbol]['price']

        if not self.auth or not self.auth.token:
            return None
            
        url = f"{config.BASE_URL}/tartarus/v1/tickerCommons"
        params = {'tickers': symbol}
        headers = {
            "Authorization": f"Bearer {self.auth.token}",
            "Content-Type": "application/json"
        }
        
        try:
            import requests
            response = requests.get(url, headers=headers, params=params, timeout=5)
            if response.status_code == 200:
                data = response.json().get("data", [])
                if data:
                    # API returns 'matchPrice' for current price
                    price = data[0].get('matchPrice')
                    # Fallback to refPrice if no match (e.g. pre-market)
                    if not price:
                        price = data[0].get('refPrice')

                    ref_price = data[0].get('refPrice')
                    if price:  # Update live cache
                        self._live_price_cache[symbol] = {'price': price, 'time': datetime.now()}
                    if ref_price:  # Opportunistically populate the reconciler cache too
                        try:
                            self._ref_price_cache[symbol] = float(ref_price)
                        except (TypeError, ValueError):
                            pass
                    return price
                else:
                    log_event(_logger, "data.realtime.empty", level=30)
            elif response.status_code == 429:
                # Rate limit hit — surface clearly and bail out without
                # retrying. The caller treats `None` as "no live price",
                # which is safe (volume strategies won't misfire because
                # the partial-bar fix from Phase 1 still holds).
                log_event(_logger, "data.realtime.rate_limited", level=30, symbol=symbol)
            else:
                log_event(_logger, "data.realtime.fetch_error", level=40, status_code=response.status_code)
        except (OSError, ValueError, KeyError, RuntimeError) as e:
            log_event(_logger, "data.realtime.error", level=40, cause=str(e))
        return None

    def _get_holidays(self) -> set:
        """Load holidays from CSV"""
        holidays = set()
        holiday_file = os.path.join(config.BASE_DIR, "config", "holidays_vn.csv")
        if os.path.exists(holiday_file):
            try:
                df_holidays = pd.read_csv(holiday_file)
                if 'date' in df_holidays.columns:
                    holidays = set(pd.to_datetime(df_holidays['date']).dt.date)
            except (OSError, ValueError, KeyError) as e:
                log_event(_logger, "data.holidays.read_failed", level=30, path=holiday_file, cause=str(e))
        return holidays

    def is_trading_day(self, d: datetime.date) -> bool:
        """Check if date is a valid trading day (Mon-Fri and not holiday)"""
        if d.weekday() >= 5:
            return False
        return d not in self._get_holidays()

    def get_expected_fresh_date(self) -> datetime.date:
        """
        Determines the date we expect the historical data to be updated to.
        Checks config/holidays_vn.csv to safely account for Weekends and Holidays.
        """
        today = datetime.now()
        
        # Cache for 60 minutes
        if hasattr(self, '_expected_date') and hasattr(self, '_expected_date_time'):
            if (today - self._expected_date_time).total_seconds() < 3600:
                return self._expected_date

        # If today is a trading day and market has closed (after 16:00), we expect today's data
        if self.is_trading_day(today.date()) and today.hour >= 16:
            self._expected_date = today.date()
        else:
            # Otherwise, step backwards to find the last completed trading day
            check_date = today.date() - timedelta(days=1)
            while not self.is_trading_day(check_date):
                check_date -= timedelta(days=1)
            self._expected_date = check_date
            
        self._expected_date_time = today
        return self._expected_date

    def get_historical_data(
        self,
        symbol: str,
        days: int = 365,
        resolution: str = '1D',
        force_update: bool = False,
        include_live: bool = True,
        min_bars_required: int = DEFAULT_MIN_BARS_REQUIRED,
    ) -> pd.DataFrame:
        """Fetch historical OHLCV and (optionally) append a partial live bar.

        The returned DataFrame conforms to the `OHLCVFrame` schema: it always
        carries `time, open, high, low, close, volume, is_partial` columns.
        Today's still-forming bar — if appended — is marked `is_partial=True`
        and carries `volume=NaN` (not 0) so volume-based strategies that read
        the last bar do not silently misfire.

        Args:
            symbol: Ticker to fetch.
            days: Calendar-day lookback window.
            resolution: Bar resolution string (only `1D` is supported today).
            force_update: Bypass the cache and re-fetch.
            include_live: If True, append today's live price as a partial bar.
            min_bars_required: Minimum closed-bar count for the cache to be
                considered satisfactory. Replaces the old 5-day-tolerance +
                `is_ipo` heuristic. Stocks listed for fewer than this many bars
                will be re-fetched on every call (the source has nothing more
                to give, so the DataFrame returned will simply be short).
        """
        # Cache file path
        cache_file = os.path.join(self.data_dir, f"{symbol}_{resolution}.csv")

        today = datetime.now()
        start_date = (today - timedelta(days=days)).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")

        df = pd.DataFrame()

        # 1. Try Load Cache
        if not force_update and os.path.exists(cache_file):
            try:
                df = pd.read_csv(cache_file)
                df['time'] = pd.to_datetime(df['time'])

                if not df.empty:
                    last_date = df['time'].max().date()

                    # 1. Fresh? Compare against expected fresh date.
                    expected_date = self.get_expected_fresh_date()
                    is_fresh = last_date >= expected_date

                    # 2. Deep enough? Explicit closed-bar threshold,
                    #    no calendar tolerance and no implicit `is_ipo` shortcut.
                    is_deep_enough = len(df) >= min_bars_required

                    if is_fresh and is_deep_enough:
                        record_metric("data.fetch.hit", 1.0, symbol=symbol)
                    else:
                        log_event(
                            _logger, "data.cache.invalid",
                            symbol=symbol, fresh=is_fresh,
                            bars=len(df), required=min_bars_required,
                        )
                        record_metric("data.fetch.miss", 1.0, symbol=symbol, reason="invalid")
                        df = pd.DataFrame()  # Force re-fetch
            except (OSError, ValueError, KeyError, pd.errors.ParserError) as e:
                # Cache file is malformed or unreadable. Treat as cache
                # miss — the fetch path below repopulates it. Do not
                # silently swallow: the cause is logged so a corrupted
                # ledger leaves a breadcrumb.
                log_event(_logger, "data.cache.read_failed", level=30, symbol=symbol, cause=str(e))
                df = pd.DataFrame()

        # 2. Fetch from Source if needed
        data_source = 'KBS'
        if df.empty:
            log_event(
                _logger, "data.fetch.start",
                symbol=symbol, source=data_source,
                start=start_date, end=end_date,
            )
            try:
                # Rate Limit: 20 req/min => 1 req every 3s.
                time.sleep(3.1)

                stock = Quote(symbol=symbol, source=data_source)
                # Note: vnstock history end_date is inclusive
                df = stock.history(start=start_date, end=end_date, interval=resolution)
                if df is not None and not df.empty:
                    # Deterministic price scaling via per-symbol metadata.
                    # vnstock-KBS returns thousand-VND for HoSE equities, so
                    # multiply by the symbol's declared scale factor.
                    meta = get_symbol_meta(symbol)
                    if meta.vnstock_price_scale != 1:
                        for col in ('open', 'high', 'low', 'close'):
                            if col in df.columns:
                                df[col] = df[col] * meta.vnstock_price_scale

                    df['time'] = pd.to_datetime(df['time'])
                    # Closed-bar default; the live-merge step below sets True
                    # on today's row when it appends one.
                    df['is_partial'] = False

                    df.to_csv(cache_file, index=False)
            except (OSError, ValueError, KeyError, RuntimeError, TypeError, AttributeError) as e:
                # Upstream (vnstock) or network failure. Caller sees an
                # empty DataFrame — the scanner already treats that as
                # "skip this symbol" and continues.
                log_event(_logger, "data.fetch.error", level=40, symbol=symbol, cause=str(e))

        if df.empty:
            # Validate even the empty case so callers see a typed schema error
            # if (e.g.) the file existed but was malformed.
            validate_ohlcv(df, symbol=symbol, resolution=resolution, require_non_empty=False)
            return df

        # Backfill `is_partial` for caches written before this column existed.
        if 'is_partial' not in df.columns:
            df['is_partial'] = False

        # 3. Merge Real-time Price as a partial bar.
        last_time = df.iloc[-1]['time']
        if include_live:
            if not self.auth:
                log_event(_logger, "data.live.no_auth", symbol=symbol)
            elif not self.is_trading_day(today.date()):
                pass  # No partial bar on weekends / holidays
            else:
                current_price = self.get_realtime_price(symbol)
                if current_price and current_price > 0:
                    if today.date() > last_time.date():
                        # Append a NEW partial bar. Volume is NaN — we do not
                        # have intraday cumulative volume and writing 0 would
                        # silently misfire volume strategies.
                        new_row = {
                            'time': pd.Timestamp(today),
                            'open': current_price,
                            'high': current_price,
                            'low': current_price,
                            'close': current_price,
                            'volume': np.nan,
                            'is_partial': True,
                        }
                        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                    elif today.date() == last_time.date():
                        # The cache already has today's row (post-close
                        # refresh). Update the close in-place and leave
                        # is_partial unchanged — by definition the bar is
                        # already settled if get_expected_fresh_date accepted
                        # it; we just refresh the closing print.
                        df.at[df.index[-1], 'close'] = current_price
                else:
                    log_event(_logger, "data.live.fetch_failed", level=30, symbol=symbol, returned=current_price)

        # 4. Truncate to requested window.
        df = df[df['time'] >= start_date].reset_index(drop=True)

        # 5. Validate the contract before handing the frame to callers.
        validate_ohlcv(df, symbol=symbol, resolution=resolution, require_non_empty=False)

        # 6. Cross-source reconciliation (ADR-001 Option B). Compares the
        #    last closed-bar close against TCBS `refPrice`. Skipped silently
        #    when auth is missing or TCBS does not return a ref price.
        if self.auth is not None:
            try:
                self.reconciler.check(symbol=symbol, df=df, auth=self.auth)
            except (OSError, ValueError, KeyError, RuntimeError) as e:
                # `severity='raise'` is opt-in; for the default 'warn'
                # reconciler, exceptions here are unexpected — log and
                # continue rather than failing the data fetch.
                log_event(_logger, "data.reconcile.error", level=40, symbol=symbol, cause=str(e))

        return df

if __name__ == "__main__":
    # Test
    provider = DataProvider()
    df = provider.get_historical_data("HPG", days=30)
    print(df.tail())
