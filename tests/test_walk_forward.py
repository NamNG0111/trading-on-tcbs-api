"""Walk-forward backtester smoke + invariants."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakes import FakeDataProvider
from trading_on_tcbs_api.stock_system_v2.core.costs import TCBS_DEFAULT_COSTS, ZERO_COSTS
from trading_on_tcbs_api.stock_system_v2.core.position_sizer import FixedFractionSizer
from trading_on_tcbs_api.stock_system_v2.core.walk_forward import WalkForwardBacktester
from trading_on_tcbs_api.stock_system_v2.strategies import SimpleMAStrategy

FIXTURES_DIR = str(Path(__file__).resolve().parent / "fixtures")


def _make_backtester(**overrides):
    return WalkForwardBacktester(
        train_bars=120,
        test_bars=60,
        step_bars=60,
        data_provider=FakeDataProvider(auth=None, reconciler=None, fixtures_dir=FIXTURES_DIR),
        **overrides,
    )


def test_walk_forward_runs_and_reports_oos_only():
    bt = _make_backtester()
    res = bt.run(SimpleMAStrategy(short_window=20, long_window=50), symbol="HPG", days=100_000)

    assert res.symbol == "HPG"
    assert res.strategy_name == "SimpleMAStrategy"
    assert res.n_windows >= 3, "fixture is 500 bars; train 120 + 60-step → at least 3 windows"
    assert len(res.windows) == res.n_windows
    assert res.oos_total_trades >= 0


def test_costs_make_returns_more_conservative():
    """Same fixture, same strategy, costs vs no-costs — total OOS return must drop or stay equal."""
    no_costs = _make_backtester(costs=ZERO_COSTS).run(
        SimpleMAStrategy(short_window=20, long_window=50), symbol="HPG", days=100_000
    )
    with_costs = _make_backtester(costs=TCBS_DEFAULT_COSTS).run(
        SimpleMAStrategy(short_window=20, long_window=50), symbol="HPG", days=100_000
    )
    assert with_costs.oos_total_return_pct <= no_costs.oos_total_return_pct + 1e-6


def test_disclaimer_present():
    res = _make_backtester().run(SimpleMAStrategy(short_window=20, long_window=50), symbol="HPG", days=100_000)
    assert "Survivor bias" in res.survivor_bias_disclaimer


def test_sizer_name_propagates():
    sizer = FixedFractionSizer(fraction=0.25)
    res = _make_backtester(sizer=sizer).run(
        SimpleMAStrategy(short_window=20, long_window=50), symbol="HPG", days=100_000
    )
    assert res.sizer_name == "FixedFractionSizer"
