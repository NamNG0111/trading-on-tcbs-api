"""MarketScanner — runs every registered strategy across a symbol universe.

Phase-3 contract:
- Constructor takes its dependencies explicitly (no internal `DataProvider()`).
- Public methods accept and return Pydantic models (`ScanResult`).
- A typed `DataFetchError` from the provider is caught per-symbol and the
  symbol is skipped, with a structured warning. Anything unexpected is
  surfaced (no bare `except Exception: pass`).
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from trading_on_tcbs_api.stock_system_v2.core.indicator_engine import IndicatorEngine
from trading_on_tcbs_api.stock_system_v2.data_ingest.data_provider import DataProvider
from trading_on_tcbs_api.stock_system_v2.exceptions import DataFetchError
from trading_on_tcbs_api.stock_system_v2.obs import (
    get_logger,
    log_event,
    record_metric,
    with_correlation,
)
from trading_on_tcbs_api.stock_system_v2.obs.metrics import timed
from trading_on_tcbs_api.stock_system_v2.schemas import ScanResult
from trading_on_tcbs_api.stock_system_v2.strategies import SignalStrategy

_logger = get_logger("scanner")


class MarketScanner:
    """Scan a list of symbols against one or more `SignalStrategy` instances.

    Args:
        data_provider: Source of OHLCV + live prices. Inject a fake in tests.
        indicator_engine: Pre-computes indicator columns each strategy reads.
        strategies: Mapping of `display_name → strategy`. Empty mappings
            are valid (returns no scan rows).
        history_days: Bars of history to request per symbol; default 365.

    Raises:
        InvalidParameterError: never raised here today, but reserved for
            future input validation when a typed `ScanRequest` lands.

    Example:
        >>> scanner = MarketScanner(
        ...     data_provider=DataProvider(auth=auth),
        ...     indicator_engine=IndicatorEngine(),
        ...     strategies={"RSI Reversal": RSIStrategy()},
        ... )
        >>> results = scanner.scan(["HPG", "TCB"])
        >>> [r.symbol for r in results if r.signal == "BUY"]
    """

    def __init__(
        self,
        *,
        data_provider: DataProvider,
        indicator_engine: IndicatorEngine,
        strategies: dict[str, SignalStrategy] | None = None,
        history_days: int = 365,
    ) -> None:
        self.data_provider = data_provider
        self.indicator_engine = indicator_engine
        self.strategies: dict[str, SignalStrategy] = dict(strategies or {})
        self.history_days = history_days

    def scan(self, symbols: list[str]) -> list[ScanResult]:
        """Return today's non-zero signals across the given symbols.

        One `ScanResult` row per (symbol × strategy) hit. Symbols whose
        history fails to load are skipped with a structured warning;
        unexpected errors propagate so they can be debugged.

        Args:
            symbols: Tickers to evaluate. Order is preserved in the output.

        Returns:
            list[ScanResult]: Rows for every BUY/SELL signal observed on
                the most recent closed bar.
        """
        results: list[ScanResult] = []
        with with_correlation(prefix="scan") as cid:
            log_event(
                _logger, "scan.start",
                n_symbols=len(symbols), n_strategies=len(self.strategies),
            )
            record_metric("scans.run", 1.0, n_symbols=len(symbols))

            self.data_provider.clear_realtime_cache()
            self.data_provider.prefetch_realtime_prices(symbols)

            with timed("scan.duration_ms", n_symbols=len(symbols)):
                for symbol in symbols:
                    try:
                        df = self.data_provider.get_historical_data(
                            symbol, days=self.history_days, include_live=True
                        )
                    except DataFetchError as exc:
                        log_event(
                            _logger, "scan.skip_symbol",
                            level=30, symbol=symbol, reason=str(exc),
                        )
                        record_metric("data.fetch.error", 1.0, symbol=symbol)
                        continue

                    if df.empty:
                        record_metric("data.fetch.empty", 1.0, symbol=symbol)
                        continue

                    live_price: float | None = None
                    if "is_partial" in df.columns and bool(df["is_partial"].iloc[-1]):
                        live_price = float(df["close"].iloc[-1])

                    df_ind = self.indicator_engine.append_indicators(df)
                    if df_ind.empty:
                        continue

                    sym_results = self._evaluate(symbol, df_ind, live_price)
                    for r in sym_results:
                        log_event(
                            _logger, "scan.signal",
                            symbol=r.symbol, strategy=r.strategy,
                            signal=r.signal, price=r.price,
                        )
                        record_metric(
                            "signals.emitted", 1.0,
                            symbol=r.symbol, strategy=r.strategy, side=r.signal,
                        )
                    results.extend(sym_results)

            log_event(_logger, "scan.complete", n_signals=len(results), correlation_id=cid)
        return results

    def scan_to_df(self, symbols: list[str]) -> dict[str, pd.DataFrame]:
        """Run `scan` and group the rows into one DataFrame per strategy.

        Convenience wrapper for the legacy CSV exporters / TUI views.
        Empty result list returns an empty dict.
        """
        results = self.scan(symbols)
        if not results:
            return {}
        flat = [self._flatten(r) for r in results]
        df = pd.DataFrame(flat)

        out: dict[str, pd.DataFrame] = {}
        for strategy_name, group in df.groupby("strategy"):
            cleaned = group.dropna(axis=1, how="all").drop(columns=["strategy"])
            preferred = ["date", "symbol", "signal", "price", "live_price"]
            cols = [c for c in preferred if c in cleaned.columns] + [
                c for c in cleaned.columns if c not in preferred
            ]
            out[strategy_name] = cleaned[cols].reset_index(drop=True)
        return out

    def print_results(self, results: list[ScanResult]) -> None:
        """Pretty-print a scan summary to stdout.

        This is operator-UX only — we keep `print()` here on purpose
        because it's the human-eyeball path, not the structured-logs
        path. Structured records went out via `log_event` during the
        scan itself.
        """
        if not results:
            print("\nNo signals found for today.")
            return

        print("\n" + "=" * 40)
        print(f"MARKET SCAN RESULTS ({len(results)} FOUND)")
        print("=" * 40)
        print(f"{'SYMBOL':<10} {'SIGNAL':<10} {'PRICE':<12} {'DATE':<12}")
        print("-" * 40)
        for res in results:
            green, red, reset = "\033[92m", "\033[91m", "\033[0m"
            color = green if res.signal == "BUY" else red
            print(f"{color}{res.symbol:<10} {res.signal:<10} {res.price:<12,.0f} {res.date:<12}{reset}")
        print("=" * 40)

    # — internals —

    def _evaluate(
        self, symbol: str, df_ind: pd.DataFrame, live_price: float | None
    ) -> list[ScanResult]:
        out: list[ScanResult] = []

        for strat_name, strat in self.strategies.items():
            df_sig = strat.generate_signals(df_ind)
            if df_sig.empty:
                continue
            last_row = df_sig.iloc[-1]
            code = int(last_row.get("signal", 0) or 0)
            if code == 0:
                continue
            action = "BUY" if code == 1 else "SELL"

            # Phase-4: typed accessor on the strategy is the source of truth
            # for context — replaces the old "scrape every added column"
            # heuristic. Falls back to the base implementation for
            # strategies that don't override.
            context: dict[str, Any] = strat.extract_signal_context(last_row)

            time_val = last_row.get("time")
            date_str = (
                time_val.strftime("%Y-%m-%d")
                if hasattr(time_val, "strftime")
                else str(time_val or "")
            )

            out.append(
                ScanResult(
                    date=date_str,
                    symbol=symbol,
                    strategy=strat_name,
                    signal=action,
                    price=float(last_row.get("close", 0.0) or 0.0),
                    live_price=live_price,
                    signal_context=context,
                )
            )
        return out

    @staticmethod
    def _flatten(r: ScanResult) -> dict[str, Any]:
        row: dict[str, Any] = {
            "date": r.date,
            "symbol": r.symbol,
            "strategy": r.strategy,
            "signal": r.signal,
            "price": r.price,
            "live_price": r.live_price,
        }
        row.update(r.signal_context)
        return row


def _coerce_scalar(value: Any) -> Any:
    """Convert numpy/pandas scalars to plain Python so Pydantic accepts them."""
    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, AttributeError):
            return value
    return value
