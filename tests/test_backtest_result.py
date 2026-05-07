"""Schema seal for the unified BacktestResult Pydantic model."""

from __future__ import annotations

from pathlib import Path

from tests.fakes import FakeDataProvider
from trading_on_tcbs_api.stock_system_v2.core.backtest_result import (
    BacktestResult,
    to_backtest_results,
)
from trading_on_tcbs_api.stock_system_v2.core.backtester import Backtester
from trading_on_tcbs_api.stock_system_v2.core.costs import TCBS_DEFAULT_COSTS
from trading_on_tcbs_api.stock_system_v2.strategies import SimpleMAStrategy

FIXTURES_DIR = str(Path(__file__).resolve().parent / "fixtures")


def test_to_backtest_results_yields_native_plus_fixed_records():
    bt = Backtester(
        initial_capital=100_000_000,
        costs=TCBS_DEFAULT_COSTS,
        data_provider=FakeDataProvider(auth=None, reconciler=None, fixtures_dir=FIXTURES_DIR),
    )
    report = bt.run(SimpleMAStrategy(short_window=20, long_window=50), symbol="HPG", days=100_000)
    assert report

    results = to_backtest_results(report, strategy_name="SimpleMA")
    assert len(results) >= 1
    native = [r for r in results if r.holding_strategy == "native"]
    fixed = [r for r in results if r.holding_strategy == "fixed"]
    assert len(native) == 1
    assert all(isinstance(r, BacktestResult) for r in results)
    assert native[0].fixed_hold_days is None
    assert all(r.fixed_hold_days is not None for r in fixed)
    assert all(r.survivor_bias_corrected is False for r in results)
    assert all("Survivor bias" in r.survivor_bias_disclaimer for r in results)
    # Commission default has been tuned post-Phase-2; just assert the field
    # is present and numeric so the seal isn't fragile to that knob.
    assert all(isinstance(r.costs.get("commission_bps"), (int, float)) for r in results)


def test_empty_report_yields_no_results():
    assert to_backtest_results({}, strategy_name="x") == []
