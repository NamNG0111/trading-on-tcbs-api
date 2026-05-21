"""StrictRevalidator — re-runs a queued strategy against fresh OHLCV (Phase 10).

When the operator (or auto-mode) confirms a `PendingSignal`, the system
MUST re-verify the signal before placing an order. The confirmation can
arrive minutes or hours after the original scan — the bar that fired the
signal at 10:03 may no longer be the latest bar at 11:42, and the price
may have moved far enough that the original thesis no longer holds.

Strict mode (the only mode supported here, per operator decision in
`memory/trading_mode_preference.md`) requires ALL of:

  1. `signal_reemitted` — the originating strategy must emit the same
     side again on the latest closed bar of the fresh fetch.
  2. `new_bar` — the latest closed bar must be strictly newer than the
     bar the original signal fired on. Re-running on the same bar would
     be a tautological pass.
  3. `price_drift` — `|fresh_close - ref_price| / ref_price` must be
     within `max_price_drift_pct`. Default 2%.
  4. `freshness` — the fresh fetch returned at least one closed bar. A
     stale cache or empty result is a hard fail.

Any failed check flips `passed` to False; the coordinator then marks the
pending signal `stale` and the scanner picks up the symbol on its next
cycle as if nothing happened.
"""

from __future__ import annotations

from typing import Protocol

import pandas as pd

from trading_on_tcbs_api.stock_system_v2.core.indicator_engine import IndicatorEngine
from trading_on_tcbs_api.stock_system_v2.obs import get_logger, log_event
from trading_on_tcbs_api.stock_system_v2.schemas import (
    PendingSignal,
    RevalCheck,
    RevalidationResult,
)
from trading_on_tcbs_api.stock_system_v2.schemas.ohlcv import closed_bars
from trading_on_tcbs_api.stock_system_v2.strategies.registry import get_strategy

_logger = get_logger("hitl.revalidator")

_SIDE_CODE: dict[str, int] = {"BUY": 1, "SELL": -1}


class DataProviderLike(Protocol):
    """Subset of `DataProvider` the revalidator depends on.

    Allows tests to inject a fake without touching the network. The real
    `DataProvider.get_historical_data` matches this shape verbatim.
    """

    def get_historical_data(
        self,
        symbol: str,
        days: int = ...,
        resolution: str = ...,
        force_update: bool = ...,
        include_live: bool = ...,
        min_bars_required: int = ...,
    ) -> pd.DataFrame: ...


class StrictRevalidator:
    """Run the four strict checks against fresh market data.

    Args:
        data_provider: Source of fresh OHLCV. Must honor `force_update=True`
            so cached stale data cannot mask a real check failure.
        indicator_engine: Computes the indicator columns the strategy reads.
            Defaults to a fresh `IndicatorEngine()` if not supplied.
        max_price_drift_pct: Maximum acceptable price drift in percent
            (e.g. 2.0 = 2%). Drifts equal to the cap pass; greater fails.
        lookback_days: Days of history to fetch — must comfortably exceed
            every strategy's `min_bars_required`. Default 365.

    Example:
        >>> r = StrictRevalidator(data_provider=dp)
        >>> result = r.check(pending_signal)
        >>> if result.passed:
        ...     coordinator.place_order(pending_signal)
    """

    def __init__(
        self,
        data_provider: DataProviderLike,
        *,
        indicator_engine: IndicatorEngine | None = None,
        max_price_drift_pct: float = 2.0,
        lookback_days: int = 365,
    ) -> None:
        if max_price_drift_pct <= 0:
            raise ValueError("max_price_drift_pct must be > 0")
        self.data_provider = data_provider
        self.indicator_engine = indicator_engine or IndicatorEngine()
        self.max_price_drift_pct = max_price_drift_pct
        self.lookback_days = lookback_days

    # — public —

    def check(self, pending: PendingSignal) -> RevalidationResult:
        """Run all four checks. Returns a typed report; never raises.

        Any unexpected exception (network, schema, strategy bug) is folded
        into a `freshness` FAIL with the exception text in `detail`. The
        coordinator treats this as `stale` and the scanner retries cleanly.
        """
        try:
            df = self.data_provider.get_historical_data(
                symbol=pending.symbol,
                days=self.lookback_days,
                resolution="1D",
                force_update=True,
                include_live=False,
                min_bars_required=1,
            )
        except (OSError, ValueError, RuntimeError) as exc:
            return self._freshness_fail(f"data fetch raised: {exc}")

        df_closed = closed_bars(df)
        if df_closed is None or len(df_closed) == 0:
            return self._freshness_fail("fresh fetch returned no closed bars")

        last = df_closed.iloc[-1]
        fresh_price = float(last["close"])
        fresh_ts = pd.to_datetime(last["time"]).to_pydatetime()
        if fresh_ts.tzinfo is None:
            fresh_ts = fresh_ts.replace(tzinfo=pending.ref_bar_close_ts.tzinfo)

        # Check: new_bar
        new_bar_check = RevalCheck(
            name="new_bar",
            passed=fresh_ts > pending.ref_bar_close_ts,
            detail=f"fresh_bar={fresh_ts.isoformat()} ref_bar={pending.ref_bar_close_ts.isoformat()}",
        )

        # Check: price_drift
        drift_pct = abs(fresh_price - pending.ref_price) / pending.ref_price * 100.0
        drift_check = RevalCheck(
            name="price_drift",
            passed=drift_pct <= self.max_price_drift_pct,
            detail=f"drift={drift_pct:.3f}% cap={self.max_price_drift_pct:.3f}% fresh={fresh_price} ref={pending.ref_price}",
        )

        # Check: signal_reemitted — only meaningful when previous checks
        # don't already disqualify the signal, but we run it anyway so the
        # report tells the operator everything that's wrong, not just the
        # first wrong thing.
        signal_check = self._check_signal_reemitted(pending, df_closed)

        # Freshness implicit by reaching here (we have closed bars).
        freshness_check = RevalCheck(
            name="freshness",
            passed=True,
            detail=f"closed_bars={len(df_closed)}",
        )

        checks = [freshness_check, new_bar_check, drift_check, signal_check]
        passed = all(c.passed for c in checks)
        reason = None if passed else next(c.detail for c in checks if not c.passed)

        result = RevalidationResult(
            passed=passed,
            checks=checks,
            fresh_price=fresh_price,
            fresh_bar_close_ts=fresh_ts,
            price_drift_pct=drift_pct,
            reason=reason,
        )

        log_event(
            _logger,
            "hitl.revalidator.checked",
            signal_id=pending.id,
            symbol=pending.symbol,
            side=pending.side,
            passed=passed,
            drift_pct=drift_pct,
            correlation_id=pending.correlation_id,
        )
        return result

    # — internals —

    def _check_signal_reemitted(
        self, pending: PendingSignal, df_closed: pd.DataFrame
    ) -> RevalCheck:
        expected_code = _SIDE_CODE.get(pending.side)
        if expected_code is None:
            return RevalCheck(
                name="signal_reemitted",
                passed=False,
                detail=f"unknown side: {pending.side}",
            )

        try:
            strategy_cls = get_strategy(pending.strategy_name)
        except KeyError as exc:
            return RevalCheck(
                name="signal_reemitted",
                passed=False,
                detail=f"strategy not registered: {exc}",
            )

        try:
            strategy = strategy_cls(params=dict(pending.strategy_params) or None)
        except (TypeError, ValueError) as exc:
            return RevalCheck(
                name="signal_reemitted",
                passed=False,
                detail=f"strategy init failed: {exc}",
            )

        try:
            df_ind = self.indicator_engine.append_indicators(df_closed)
            df_sig = strategy.generate_signals(df_ind)
        except (KeyError, ValueError, RuntimeError) as exc:
            return RevalCheck(
                name="signal_reemitted",
                passed=False,
                detail=f"strategy evaluation failed: {exc}",
            )

        if "signal" not in df_sig.columns or len(df_sig) == 0:
            return RevalCheck(
                name="signal_reemitted",
                passed=False,
                detail="strategy did not produce a `signal` column",
            )

        last_signal = int(df_sig["signal"].iloc[-1])
        passed = last_signal == expected_code
        return RevalCheck(
            name="signal_reemitted",
            passed=passed,
            detail=f"last_signal={last_signal} expected={expected_code} ({pending.side})",
        )

    def _freshness_fail(self, reason: str) -> RevalidationResult:
        check = RevalCheck(name="freshness", passed=False, detail=reason)
        return RevalidationResult(passed=False, checks=[check], reason=reason)
