"""Look-ahead detection utility for V2 strategies (Phase 2).

A strategy is *causal* (no look-ahead) iff the signal at bar `t` depends only
on bars in `[0, t]`. Equivalently: re-running the strategy on the truncated
prefix `df[:t+1]` must produce the same signal at position `t` as running
it on the full frame.

`assert_no_lookahead` exercises this property by spot-checking at multiple
truncation points. Any divergence flags a leakage of future information into
a past signal — exactly the bug class that invalidates backtests.

The utility wraps the indicator engine + strategy as a single black box, so
look-ahead introduced *anywhere* in the pipeline (engine, strategy, helper
columns) is caught.
"""

from __future__ import annotations

from typing import Callable, Iterable

import pandas as pd

from trading_on_tcbs_api.stock_system_v2.core.indicator_engine import IndicatorEngine
from trading_on_tcbs_api.stock_system_v2.strategies import SignalStrategy


def _default_check_indices(n: int, min_index: int) -> list[int]:
    """Pick a representative set of truncation points.

    We check the last 10 bars (highest-leverage region for live signal use)
    plus every 25th bar from `min_index` upward (cheap broad coverage).
    """
    if n <= min_index + 1:
        return []
    tail = list(range(max(min_index, n - 10), n))
    stride = list(range(min_index, n - 10, 25))
    return sorted(set(stride + tail))


def assert_no_lookahead(
    strategy: SignalStrategy,
    df: pd.DataFrame,
    *,
    indicator_engine: IndicatorEngine | None = None,
    min_index: int = 60,
    check_indices: Iterable[int] | None = None,
    signal_col: str = "signal",
) -> None:
    """Assert that `strategy` does not peek at future bars.

    For each truncation point `t` in `check_indices`, re-runs the full
    pipeline (engine + strategy) on `df[:t+1]` and confirms the signal at
    bar `t` matches the signal at bar `t` in the full-frame run.

    Args:
        strategy: The strategy under test.
        df: Validated OHLCV frame (closed bars only, no partial row).
        indicator_engine: Engine to use; defaults to `IndicatorEngine()`.
        min_index: Skip truncations before this index — most strategies need
            warmup bars for SMA/RSI/etc. and emit deliberately-zero signals
            there. Default 60 covers SMA_50 + a few buffer bars.
        check_indices: Override the default truncation grid; useful when a
            strategy has a known long warmup.
        signal_col: Column name carrying the BUY/SELL/HOLD code.

    Raises:
        AssertionError: with a list of `(index, full, truncated)` mismatches.
    """
    engine = indicator_engine or IndicatorEngine()
    full_with_ind = engine.append_indicators(df)
    full_signals = strategy.generate_signals(full_with_ind.copy())[signal_col].astype(int).reset_index(drop=True)

    n = len(full_signals)
    indices = list(check_indices) if check_indices is not None else _default_check_indices(n, min_index)

    mismatches: list[tuple[int, int, int]] = []
    for t in indices:
        if t < 0 or t >= n:
            continue
        prefix = df.iloc[: t + 1].copy()
        prefix_with_ind = engine.append_indicators(prefix)
        prefix_signals = strategy.generate_signals(prefix_with_ind.copy())[signal_col].astype(int).reset_index(drop=True)
        if len(prefix_signals) == 0:
            continue
        # The prefix run may have dropped bars (e.g. partial); compare
        # against the same trailing position.
        truncated = int(prefix_signals.iloc[-1])
        full = int(full_signals.iloc[len(prefix_signals) - 1])
        if truncated != full:
            mismatches.append((t, full, truncated))

    if mismatches:
        details = ", ".join(f"t={t}: full={f}, truncated={tr}" for t, f, tr in mismatches[:10])
        raise AssertionError(
            f"{strategy.__class__.__name__} leaked future data at {len(mismatches)} index(es): {details}"
        )
