"""Phase-7 end-to-end smoke test.

Exercises the full agent-shaped workflow — list strategies → list
symbols → run a backtest → scan for signals → validate an order →
submit it (safe-mode) — using **only** `invoke(name, args)`. No code
under test imports private V2 internals; this is the contract a future
Claude session would drive over MCP.

If this file's imports stay this thin, the codebase has cleared the
"agent runs every workflow via tool calls only" DoD.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakes import FakeDataProvider
from trading_on_tcbs_api.stock_system_v2.core.indicator_engine import IndicatorEngine
from trading_on_tcbs_api.stock_system_v2.execution.order_manager import OrderManager
from trading_on_tcbs_api.stock_system_v2.execution.order_tracker import OrderTracker
from trading_on_tcbs_api.stock_system_v2.execution.pre_trade_validator import (
    PreTradeValidator,
)
from trading_on_tcbs_api.stock_system_v2.finance.account_manager import AccountManager
from trading_on_tcbs_api.stock_system_v2.settings import Settings
from trading_on_tcbs_api.stock_system_v2.tools import (
    ToolError,
    invoke,
)
from trading_on_tcbs_api.stock_system_v2.tools.context import (
    ToolContext,
    clear_context,
    set_context,
)

FIXTURES_DIR = str(Path(__file__).resolve().parent / "fixtures")
FIXTURE_SYMBOLS = ("HPG", "TCB", "FPT")


@pytest.fixture
def smoke_context(tmp_path: Path):
    settings = Settings.load(base_dir=tmp_path).model_copy(
        update={"symbols": FIXTURE_SYMBOLS, "execution_disabled": False}
    )
    tracker = OrderTracker(str(tmp_path / "ledger.csv"))
    ctx = ToolContext(
        settings=settings,
        data_provider=FakeDataProvider(auth=None, reconciler=None, fixtures_dir=FIXTURES_DIR),
        indicator_engine=IndicatorEngine(),
        account=AccountManager(initial_cash=100_000_000),
        order_manager=OrderManager(auth=None, safe_mode=True, tracker=tracker),
        order_tracker=tracker,
        validator=PreTradeValidator(universe=FIXTURE_SYMBOLS),
        auth=None,
    )
    set_context(ctx)
    yield ctx
    clear_context()


def test_envelope_carries_correlation_id(smoke_context):
    env = invoke("list_symbols")
    assert env.correlation_id.startswith("tool_")
    assert env.result.symbols == list(FIXTURE_SYMBOLS)


def test_full_agent_workflow(smoke_context):
    """The DoD: drive scan → backtest → paper-trade through tool calls only."""
    # 1. Discover strategies.
    strategies_resp = invoke("list_strategies")
    available = strategies_resp.result.strategies
    assert "rsi" in available
    rsi_desc = available["rsi"]
    assert rsi_desc.params_schema  # JSON schema present
    assert rsi_desc.min_bars_required > 0

    # 2. Discover the universe.
    symbols_resp = invoke("list_symbols")
    symbols = symbols_resp.result.symbols
    assert symbols == list(FIXTURE_SYMBOLS)

    # 3. Backtest one strategy on one symbol.
    bt = invoke("run_backtest", {
        "strategy": "rsi",
        "symbol": "HPG",
        "days": 365,
        "params": {"period": 14, "is_reversal": True},
    })
    assert len(bt.result.results) >= 1
    native = next(r for r in bt.result.results if r.holding_strategy == "native")
    assert native.symbol == "HPG"
    assert "Survivor bias" in native.survivor_bias_disclaimer

    # 4. Walk-forward sanity (OOS-only).
    wf = invoke("walk_forward", {
        "strategy": "rsi",
        "symbol": "HPG",
        "days": 365 * 5,
        "train_bars": 120,
        "test_bars": 60,
    })
    assert wf.result.result.n_windows >= 1

    # 5. Scan for today's signals.
    scan = invoke("scan_market", {
        "strategies": [{"name": "rsi", "params": {"is_reversal": True}}],
        "symbols": list(symbols),
        "history_days": 365,
    })
    assert scan.result.n_strategies == 1
    # The fixture data may or may not produce a signal today; the
    # contract is just that the call shape is honoured.

    # 6. Account introspection.
    acct = invoke("get_account")
    assert acct.result.snapshot.cash == 100_000_000
    assert acct.result.snapshot.is_mock is True

    # 7. Validate an order.
    order_req = {
        "request": {
            "symbol": "HPG",
            "side": "BUY",
            "price": float(scan.result.results[0].price) if scan.result.results else 28000.0,
            "volume": 100,
        }
    }
    val = invoke("validate_order", order_req)
    assert val.result.risk_check.passed
    check_id = val.result.risk_check.check_id

    # 8. Submit (safe-mode → mock fill).
    submit = invoke("submit_order", {
        **order_req,
        "risk_check_id": check_id,
    })
    assert submit.result.response.status == "FILLED"
    assert submit.result.response.broker_order_id.startswith("mock_")

    # 9. Audit log surfaces the decision.
    audit = invoke("get_audit_log", {"limit": 10})
    assert audit.result.n_rows >= 1
    submitted = [r for r in audit.result.rows if (r.decision or "").startswith("submit")]
    assert submitted, "submit_order should have written a decision row"

    # 10. Health summary closes the loop.
    health = invoke("health_check")
    # Auth absent → warn-not-fail on a clean fixture data dir.
    assert isinstance(health.result.status.ok, bool)


def test_unknown_tool_raises_typed_error(smoke_context):
    with pytest.raises(ToolError) as exc:
        invoke("not_a_tool")
    assert exc.value.code == "UNKNOWN_TOOL"
    assert "available" in exc.value.details


def test_invalid_params_raises_typed_error(smoke_context):
    with pytest.raises(ToolError) as exc:
        invoke("get_history", {"symbol": "", "days": 365})
    assert exc.value.code == "INVALID_PARAMS"


def test_data_fetch_error_maps_to_typed_code(smoke_context):
    with pytest.raises(ToolError) as exc:
        invoke("get_history", {"symbol": "ZZZ", "days": 365})
    # FakeDataProvider returns empty for unknown symbol → handler raises
    # DataFetchError → mapped to DATA_FETCH_FAILED.
    assert exc.value.code == "DATA_FETCH_FAILED"
    assert exc.value.retriable is True


def test_duplicate_order_rejected_via_tools(smoke_context):
    val = invoke("validate_order", {
        "request": {"symbol": "HPG", "side": "BUY", "price": 28000.0, "volume": 100}
    })
    invoke("submit_order", {
        "request": val.result.risk_check.model_dump(exclude={"check_id"}) and {
            "symbol": "HPG", "side": "BUY", "price": 28000.0, "volume": 100,
            "client_order_id": "co_dupe_test_1",
        },
        "risk_check_id": val.result.risk_check.check_id,
    })

    val2 = invoke("validate_order", {
        "request": {
            "symbol": "HPG", "side": "BUY", "price": 28000.0, "volume": 100,
            "client_order_id": "co_dupe_test_1",
        }
    })
    with pytest.raises(ToolError) as exc:
        invoke("submit_order", {
            "request": {
                "symbol": "HPG", "side": "BUY", "price": 28000.0, "volume": 100,
                "client_order_id": "co_dupe_test_1",
            },
            "risk_check_id": val2.result.risk_check.check_id,
        })
    assert exc.value.code == "DUPLICATE_ORDER"
