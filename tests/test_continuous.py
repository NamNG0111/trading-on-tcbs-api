"""Phase-9 continuous-learning primitives."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.fakes import FakeDataProvider
from trading_on_tcbs_api.stock_system_v2.agents import (
    decisions_dataset,
    drift_check,
    flag_tool_output,
    strategy_proposal_brief,
)
from trading_on_tcbs_api.stock_system_v2.core.indicator_engine import IndicatorEngine
from trading_on_tcbs_api.stock_system_v2.execution.order_manager import OrderManager
from trading_on_tcbs_api.stock_system_v2.execution.order_tracker import OrderTracker
from trading_on_tcbs_api.stock_system_v2.execution.pre_trade_validator import (
    PreTradeValidator,
)
from trading_on_tcbs_api.stock_system_v2.finance.account_manager import AccountManager
from trading_on_tcbs_api.stock_system_v2.settings import Settings
from trading_on_tcbs_api.stock_system_v2.tools.context import (
    ToolContext,
    clear_context,
    set_context,
)

FIXTURES_DIR = str(Path(__file__).resolve().parent / "fixtures")
SYMBOLS = ("HPG", "TCB", "FPT")


@pytest.fixture
def ctx(tmp_path: Path):
    settings = Settings.load(base_dir=tmp_path).model_copy(update={"symbols": SYMBOLS})
    tracker = OrderTracker(str(tmp_path / "ledger.csv"))
    c = ToolContext(
        settings=settings,
        data_provider=FakeDataProvider(auth=None, reconciler=None, fixtures_dir=FIXTURES_DIR),
        indicator_engine=IndicatorEngine(),
        account=AccountManager(initial_cash=100_000_000),
        order_manager=OrderManager(auth=None, safe_mode=True, tracker=tracker),
        order_tracker=tracker,
        validator=PreTradeValidator(universe=SYMBOLS),
        auth=None,
    )
    set_context(c)
    yield c
    clear_context()


def _seed_decisions(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


# — decisions dataset —

def test_decisions_dataset_empty(tmp_path: Path):
    ds = decisions_dataset(path=tmp_path / "missing.jsonl")
    assert ds.n_rows == 0
    assert ds.by_symbol == {}


def test_decisions_dataset_aggregates(tmp_path: Path):
    target = tmp_path / "decisions.jsonl"
    _seed_decisions(target, [
        {"correlation_id": "c1", "decision": "submit:safe_mode", "symbol": "HPG", "side": "BUY"},
        {"correlation_id": "c1", "decision": "submit:safe_mode", "symbol": "HPG", "side": "BUY"},
        {"correlation_id": "c2", "decision": "reject:kill_switch", "symbol": "HPG", "side": "BUY"},
        {"correlation_id": "c3", "decision": "skipped:warning", "symbol": "TCB", "side": "SELL"},
    ])
    ds = decisions_dataset(path=target)
    assert ds.n_rows == 4
    assert ds.n_correlation_ids == 3
    hpg = ds.by_symbol["HPG:BUY"]
    assert hpg.n_decisions == 3
    assert hpg.n_submitted == 2
    assert hpg.n_skipped_reject == 1
    tcb = ds.by_symbol["TCB:SELL"]
    assert tcb.n_skipped_warning == 1
    assert ds.raw_decision_codes["submit:safe_mode"] == 2


# — strategy proposal brief —

def test_strategy_proposal_brief_lists_registry(ctx):
    brief = strategy_proposal_brief()
    assert "rsi" in brief.registered_strategies
    assert "simple_ma" in brief.registered_strategies
    # `combined` is the meta-strategy, skipped by list_strategies handler.
    assert "combined" not in brief.registered_strategies
    # Regimes covered.
    assert "mean-revert" in brief.by_regime or "trend" in brief.by_regime
    assert brief.instructions  # non-empty
    # Every gap row carries a coherent regime + note.
    for gap in brief.gaps:
        assert gap.n_strategies <= 1
        assert gap.regime in {"trend", "mean-revert", "vol-expansion"}


# — drift detection —

def test_drift_check_within_threshold(ctx):
    """When live ≈ expected, breached is False."""
    alert = drift_check(
        strategy="rsi",
        symbol="HPG",
        observed_live_return_pct=0.0,
        walk_forward_days=365 * 2,
        threshold_pct_points=200.0,
    )
    assert alert.breached is False
    assert "within" in alert.rationale.lower()


def test_drift_check_breaches(ctx):
    alert = drift_check(
        strategy="rsi",
        symbol="HPG",
        observed_live_return_pct=999.0,  # absurd live return
        walk_forward_days=365 * 2,
        threshold_pct_points=10.0,
    )
    assert alert.breached is True
    assert "diverges" in alert.rationale.lower()


# — tool-quality feedback —

def test_flag_tool_output_appends(tmp_path: Path):
    target = tmp_path / "tq.jsonl"
    flag_tool_output(
        tool_name="get_history",
        issue="returned NaN volume on closed bar",
        arguments={"symbol": "HPG", "days": 365},
        received={"n_bars": 0},
        severity="major",
        path=target,
    )
    flag_tool_output(
        tool_name="run_backtest",
        issue="profit_factor=inf with 1 trade",
        arguments={"strategy": "rsi", "symbol": "HPG"},
        severity="minor",
        path=target,
    )
    rows = [json.loads(line) for line in target.read_text().strip().splitlines()]
    assert len(rows) == 2
    assert rows[0]["tool"] == "get_history"
    assert rows[0]["severity"] == "major"
    assert rows[1]["severity"] == "minor"
    assert all("ts" in r for r in rows)
