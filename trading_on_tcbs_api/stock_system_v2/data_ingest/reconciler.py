"""Cross-source price reconciler — Phase 1, Option B.

ADR-001 keeps both vnstock (historical) and TCBS (live) as data sources. To
prevent silent divergence between them — a corp-action that has propagated to
one provider but not the other, a stale cache, a feed glitch — every fetch
boundary runs the surviving frame through `PriceReconciler.check`.

TCBS does not currently expose a working historical endpoint via OpenAPI
(see `scripts/probe_history.py`), so the runtime check is necessarily
single-point: compare vnstock's most recent **closed** bar close against
TCBS's `refPrice` (prior-close reference). The interface is structured so a
future last-N implementation can slot in without touching the call sites.

Severity policy
---------------
- ``warn``  — log a structured warning; let the data through.
- ``raise`` — raise `PriceReconciliationError`; fail closed.

The default is ``warn`` because Phase 1 is observational; Phase 5 (execution
safety) is the right phase to escalate to ``raise`` for any path that places
orders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Iterable, Literal, Optional

import pandas as pd

# Default threshold above which closes are considered to have diverged.
# 25 basis points = 0.25% — large enough to ignore tick rounding and the
# milli-VND drift between providers, small enough to surface a real corp-
# action mismatch (split, dividend, ticker change).
DEFAULT_THRESHOLD_BPS: float = 25.0

Severity = Literal["warn", "raise"]


class PriceReconciliationError(ValueError):
    """Raised when sources diverge beyond threshold and severity == 'raise'."""


@dataclass
class ReconciliationResult:
    """Outcome of a single reconciliation check.

    `agreed` is True iff the absolute spread is within `threshold_bps`. Even
    when False, the data may still flow — `severity` controls that. The
    record is the audit trail.
    """

    symbol: str
    primary_value: float
    secondary_value: float
    spread_bps: float
    threshold_bps: float
    agreed: bool
    primary_label: str = "vnstock_close"
    secondary_label: str = "tcbs_refPrice"
    timestamp: datetime = field(default_factory=datetime.now)
    note: str = ""

    def message(self) -> str:
        return (
            f"[Reconcile] {self.symbol}: {self.primary_label}={self.primary_value:,.2f} "
            f"vs {self.secondary_label}={self.secondary_value:,.2f} "
            f"(spread={self.spread_bps:+.1f} bps, threshold={self.threshold_bps:.1f}); "
            f"{'OK' if self.agreed else 'DIVERGED'}. {self.note}".rstrip()
        )


# Type alias for a function that, given an auth object and a symbol, returns
# TCBS's prior-close reference price (or None if unavailable). Injected so
# tests can run without the wire.
RefPriceFetcher = Callable[[object, str], Optional[float]]


def _default_ref_price_fetcher(auth: object, symbol: str) -> Optional[float]:
    """Default fetcher: hit TCBS `tickerCommons` and pull `refPrice`.

    Imported lazily so the reconciler module has no hard dependency on
    `requests` at import time (keeps tests light).
    """
    if auth is None or getattr(auth, "token", None) is None:
        return None
    import requests

    from trading_on_tcbs_api.stock_system_v2 import config

    url = f"{config.BASE_URL}/tartarus/v1/tickerCommons"
    headers = {"Authorization": f"Bearer {auth.token}", "Content-Type": "application/json"}
    try:
        resp = requests.get(url, headers=headers, params={"tickers": symbol}, timeout=5)
    except (requests.exceptions.RequestException, ValueError):
        return None
    if resp.status_code != 200:
        return None
    rows = resp.json().get("data", [])
    if not rows:
        return None
    ref = rows[0].get("refPrice")
    try:
        return float(ref) if ref is not None else None
    except (TypeError, ValueError):
        return None


class PriceReconciler:
    """Compare vnstock's last closed-bar close to TCBS's `refPrice`.

    Usage:
        reconciler = PriceReconciler(threshold_bps=25.0, severity="warn")
        result = reconciler.check(symbol="HPG", df=vnstock_df, auth=auth)
        if result is not None and not result.agreed:
            ...  # already logged / raised per severity
    """

    def __init__(
        self,
        threshold_bps: float = DEFAULT_THRESHOLD_BPS,
        severity: Severity = "warn",
        ref_price_fetcher: RefPriceFetcher = _default_ref_price_fetcher,
        logger: Optional[Callable[[str], None]] = None,
    ) -> None:
        if threshold_bps <= 0:
            raise ValueError("threshold_bps must be positive")
        self.threshold_bps = float(threshold_bps)
        self.severity: Severity = severity
        self._ref_price_fetcher = ref_price_fetcher
        # Phase-6 dual-emission: keep the human-readable string going to
        # stdout (the `capsys`-driven tests + operator console rely on
        # it) and *also* mirror it as a structured log event. The
        # legacy `logger=` injection still wins when supplied.
        if logger is not None:
            self._log = logger
        else:
            from trading_on_tcbs_api.stock_system_v2.obs import get_logger, log_event

            _l = get_logger("price_reconciler")

            def _dual_log(msg: str) -> None:
                print(msg)
                log_event(_l, "price_reconciler.event", text=msg)

            self._log = _dual_log
        self._history: list[ReconciliationResult] = []

    @property
    def history(self) -> list[ReconciliationResult]:
        """Audit trail of every check this reconciler has run."""
        return list(self._history)

    def check(self, *, symbol: str, df: pd.DataFrame, auth: object) -> Optional[ReconciliationResult]:
        """Run a single reconciliation pass.

        Returns the `ReconciliationResult` (logged + appended to history),
        or `None` if the check was skipped (no auth, no data, no ref price).
        Raises `PriceReconciliationError` if `severity='raise'` and the
        spread exceeds threshold.
        """
        if df is None or df.empty:
            return None
        if "close" not in df.columns:
            return None

        # Use the last *closed* bar; if the schema marks a partial bar, skip
        # it. The reconciler operates on settled data only.
        if "is_partial" in df.columns:
            closed = df.loc[df["is_partial"] != True]
            if closed.empty:
                return None
            primary = float(closed["close"].iloc[-1])
        else:
            primary = float(df["close"].iloc[-1])

        secondary = self._ref_price_fetcher(auth, symbol)
        if secondary is None or secondary <= 0:
            return None

        spread_bps = (primary - secondary) / secondary * 10_000.0
        agreed = abs(spread_bps) <= self.threshold_bps
        result = ReconciliationResult(
            symbol=symbol,
            primary_value=primary,
            secondary_value=secondary,
            spread_bps=spread_bps,
            threshold_bps=self.threshold_bps,
            agreed=agreed,
        )
        self._history.append(result)

        if not agreed:
            self._log(result.message())
            if self.severity == "raise":
                raise PriceReconciliationError(result.message())
        return result

    def check_series(
        self,
        *,
        symbol: str,
        primary_series: Iterable[float],
        secondary_series: Iterable[float],
        primary_label: str = "primary",
        secondary_label: str = "secondary",
    ) -> ReconciliationResult:
        """Compare two equal-length series of closes and report worst-case spread.

        Provided for the future case where TCBS exposes historical bars (or
        an alternate provider does); not used by the runtime path today.
        """
        p = pd.Series(list(primary_series), dtype=float)
        s = pd.Series(list(secondary_series), dtype=float)
        if len(p) == 0 or len(p) != len(s):
            raise ValueError("primary and secondary series must be non-empty and equal length")

        spreads = (p - s) / s * 10_000.0
        worst_idx = spreads.abs().idxmax()
        spread_bps = float(spreads.iloc[worst_idx])
        agreed = abs(spread_bps) <= self.threshold_bps
        result = ReconciliationResult(
            symbol=symbol,
            primary_value=float(p.iloc[worst_idx]),
            secondary_value=float(s.iloc[worst_idx]),
            spread_bps=spread_bps,
            threshold_bps=self.threshold_bps,
            agreed=agreed,
            primary_label=primary_label,
            secondary_label=secondary_label,
            note=f"worst-of-{len(p)} at index {int(worst_idx)}",
        )
        self._history.append(result)
        if not agreed:
            self._log(result.message())
            if self.severity == "raise":
                raise PriceReconciliationError(result.message())
        return result
