"""End-to-end backtester regression test.

Wires `core/backtester.py` against the `FakeDataProvider` so the run is
fully network-free, deterministic, and reproducible from check-in.

Like the strategy seals, this locks the *current* output. Re-run the
fixture generator and update the asserted values only when an intentional
change has been made.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakes import FakeDataProvider
from trading_on_tcbs_api.stock_system_v2.core.backtester import Backtester
from trading_on_tcbs_api.stock_system_v2.strategies import SimpleMAStrategy

FIXTURES_DIR = str(Path(__file__).resolve().parent / "fixtures")


def test_backtester_runs_simple_ma_against_fixture():
    backtester = Backtester(initial_capital=100_000_000)
    # Replace the auto-instantiated DataProvider with a fixture-backed fake.
    backtester.data_provider = FakeDataProvider(
        auth=None,
        reconciler=None,
        fixtures_dir=FIXTURES_DIR,
    )

    strategy = SimpleMAStrategy(short_window=20, long_window=50)
    # Fixture spans 2024-01-01 onward (~500 business days). 100k days
    # window guarantees the truncation does nothing for this synthetic data.
    report = backtester.run(strategy, symbol="HPG", days=100_000)

    # Schema-level invariants the agent layer will rely on.
    required_keys = {
        "symbol",
        "start_date",
        "end_date",
        "initial_capital",
        "final_value",
        "total_return_pct",
        "total_trades",
        "win_rate_pct",
        "max_drawdown_pct",
        "profit_factor",
        "fixed_hold_results",
    }
    assert required_keys.issubset(report.keys())
    assert report["symbol"] == "HPG"
    assert report["initial_capital"] == 100_000_000

    # Behavioural seal — locked from the deterministic fixture/strategy
    # combo. simple_ma__HPG.csv has 5 BUYs / 5 SELLs but the backtester
    # skips any leading SELL (no shares to sell yet), so 9 executed trades.
    assert report["total_trades"] == 9
    assert report["final_value"] > 0
    assert -100.0 <= report["max_drawdown_pct"] <= 0.0


def test_backtester_handles_empty_universe():
    """Schema contract: empty fixture → empty report, no crash."""
    backtester = Backtester(initial_capital=100_000_000)
    backtester.data_provider = FakeDataProvider(
        auth=None,
        reconciler=None,
        frames={"GHOST": __import__("pandas").DataFrame()},
    )
    strategy = SimpleMAStrategy()
    report = backtester.run(strategy, symbol="GHOST", days=365)
    assert report == {}
