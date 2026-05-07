"""One-shot fixture generator.

Materialises three deterministic OHLCV CSVs (HPG, TCB, FPT) and the expected
signal output for every V2 strategy on each fixture. Re-running this script
overwrites the artifacts — run it (and review the diff) only when an
intentional behaviour change has been made.

Outputs:
    tests/fixtures/HPG.csv
    tests/fixtures/TCB.csv
    tests/fixtures/FPT.csv
    tests/fixtures/expected/<strategy>__<symbol>.csv  (cols: time, signal)

Usage:
    python tests/fixtures/generate_fixtures.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

# Make the repo importable when invoked as a script.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.conftest import make_ohlcv  # noqa: E402
from trading_on_tcbs_api.stock_system_v2.core.indicator_engine import IndicatorEngine  # noqa: E402
from trading_on_tcbs_api.stock_system_v2.strategies import (  # noqa: E402
    CumulativeDropStrategy,
    DipBuyStrategy,
    IntradayDipStrategy,
    RSIDivergenceStrategy,
    RSIStrategy,
    SimpleMAStrategy,
    VolumeBoomStrategy,
)

FIXTURES_DIR = Path(__file__).parent
EXPECTED_DIR = FIXTURES_DIR / "expected"

# (symbol, seed, base_price) — keep entries stable; appending is fine.
FIXTURE_SPECS = [
    ("HPG", 42, 28_000.0),
    ("TCB", 7, 24_000.0),
    ("FPT", 99, 110_000.0),
]

# (label, factory) — `label` becomes the filename stem of the expected output.
# Each factory must return a fresh strategy instance.
STRATEGY_FACTORIES: list[tuple[str, callable]] = [
    ("simple_ma", lambda: SimpleMAStrategy(short_window=20, long_window=50)),
    ("rsi_basic", lambda: RSIStrategy(period=14, is_reversal=False)),
    ("rsi_reversal", lambda: RSIStrategy(period=14, is_reversal=True)),
    ("rsi_divergence", lambda: RSIDivergenceStrategy(rsi_period=14, lookback=5, max_bars_between=30)),
    ("volume_boom", lambda: VolumeBoomStrategy(window=20, threshold_pct=50.0)),
    ("dip_buy", lambda: DipBuyStrategy(sma_window=20, drop_pct=10.0)),
    ("cumulative_drop", lambda: CumulativeDropStrategy(days=3, drop_pct=10.0)),
    ("intraday_dip", lambda: IntradayDipStrategy(lookback_days=60, percentile=75.0)),
]


def _write_ohlcv_fixture(symbol: str, seed: int, base_price: float) -> pd.DataFrame:
    df = make_ohlcv(n=500, seed=seed, base_price=base_price)
    out_path = FIXTURES_DIR / f"{symbol}.csv"
    df.to_csv(out_path, index=False)
    print(f"  wrote {out_path.relative_to(REPO_ROOT)} ({len(df)} bars)")
    return df


def _write_expected_signals(label: str, symbol: str, df_with_signal: pd.DataFrame) -> None:
    EXPECTED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = EXPECTED_DIR / f"{label}__{symbol}.csv"
    keep = df_with_signal[["time", "signal"]].copy()
    keep["signal"] = keep["signal"].astype(int)
    keep.to_csv(out_path, index=False)
    n_buys = int((keep["signal"] == 1).sum())
    n_sells = int((keep["signal"] == -1).sum())
    print(f"    {label}: {n_buys} BUY, {n_sells} SELL → {out_path.name}")


def main() -> None:
    print(f"[fixtures] regenerating under {FIXTURES_DIR.relative_to(REPO_ROOT)}")
    engine = IndicatorEngine()

    for symbol, seed, base_price in FIXTURE_SPECS:
        df_raw = _write_ohlcv_fixture(symbol, seed, base_price)
        df_with_indicators = engine.append_indicators(df_raw)
        for label, factory in STRATEGY_FACTORIES:
            strat = factory()
            df_sig = strat.generate_signals(df_with_indicators.copy())
            _write_expected_signals(label, symbol, df_sig)

    print("[fixtures] done")


if __name__ == "__main__":
    main()
