"""Run the §14 'what done looks like' gate on ONE strategy.

Usage:
    python -m trading_on_tcbs_api.stock_system_v2.scripts.evaluate_strategy <registry_id>
    python -m trading_on_tcbs_api.stock_system_v2.scripts.evaluate_strategy <registry_id> '{"period": 14}'

Workflow:
  1. Walk-forward the strategy across every symbol in `Settings.symbols`
     over 2 years (1y train + 6m test, 6m step).
  2. Apply the §14 gate: held up on ≥5 of 8 with avg Sharpe > 0.3.
  3. If passed, scan today's signals on the held-up symbols and
     validate each — output the validator-approved orders.
  4. Print a verdict the operator can act on directly.

This is the same gate `demo_done_looks_like.py` applies, scoped to one
strategy. Use it after adding a new strategy class to confirm the gate
passes before starting the paper soak.
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from trading_on_tcbs_api.stock_system_v2.tools import ToolError, invoke  # noqa: E402
from trading_on_tcbs_api.stock_system_v2.tools.context import ToolContext, set_context  # noqa: E402

HELD_UP_MIN = 5
SHARPE_MIN = 0.3


def _bootstrap() -> None:
    from trading_on_tcbs_api.stock_system_v2.core.indicator_engine import IndicatorEngine
    from trading_on_tcbs_api.stock_system_v2.data_ingest.data_provider import DataProvider
    from trading_on_tcbs_api.stock_system_v2.execution.order_manager import OrderManager
    from trading_on_tcbs_api.stock_system_v2.execution.order_tracker import OrderTracker
    from trading_on_tcbs_api.stock_system_v2.execution.pre_trade_validator import (
        PreTradeValidator,
        ValidatorConfig,
    )
    from trading_on_tcbs_api.stock_system_v2.finance.account_manager import AccountManager
    from trading_on_tcbs_api.stock_system_v2.settings import Settings

    settings = Settings.load()
    tracker = OrderTracker()
    set_context(ToolContext(
        settings=settings,
        data_provider=DataProvider(auth=None),
        indicator_engine=IndicatorEngine(),
        account=AccountManager(initial_cash=100_000_000),
        order_manager=OrderManager(auth=None, safe_mode=True, tracker=tracker),
        order_tracker=tracker,
        validator=PreTradeValidator(
            config=ValidatorConfig(max_notional_vnd=500_000_000.0),
            universe=tuple(settings.symbols),
        ),
        auth=None,
    ))


def _annualised_sharpe(per_window_pct: list[float]) -> float:
    if len(per_window_pct) < 2:
        return float("nan")
    decimals = [r / 100.0 for r in per_window_pct]
    mean = statistics.mean(decimals)
    stdev = statistics.pstdev(decimals)
    if stdev == 0:
        return 0.0
    return (mean / stdev) * math.sqrt(4.0)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(f"Usage: {argv[0]} <registry_id> ['<json-params>']")
        return 2
    name = argv[1]
    params: dict = {}
    if len(argv) >= 3:
        try:
            params = json.loads(argv[2])
        except json.JSONDecodeError as exc:
            print(f"Bad params JSON: {exc}")
            return 2

    _bootstrap()

    universe = invoke("list_symbols").result.symbols
    print(f"Evaluating strategy={name!r} params={params or '{}'} over {universe}\n")

    rows: dict[str, dict] = {}
    held_up: list[str] = []
    for sym in universe:
        try:
            resp = invoke("walk_forward", {
                "strategy": name, "symbol": sym, "params": params,
                "days": 365 * 2, "train_bars": 252, "test_bars": 63,
            })
        except ToolError as exc:
            rows[sym] = {"error": exc.code, "message": exc.message}
            continue
        wf = resp.result.result
        sharpe = _annualised_sharpe([w.test_return_pct for w in wf.windows])
        max_dd = min((w.test_max_drawdown_pct for w in wf.windows), default=0.0)
        held = wf.oos_total_return_pct > 0 and wf.oos_total_trades >= 3
        rows[sym] = {
            "n_windows": wf.n_windows,
            "oos_total_return_pct": wf.oos_total_return_pct,
            "oos_total_trades": wf.oos_total_trades,
            "oos_win_rate_pct": wf.oos_win_rate_pct,
            "sharpe": sharpe,
            "max_window_drawdown_pct": max_dd,
            "held_up": held,
        }
        if held:
            held_up.append(sym)

    print(
        f"  {'symbol':<6} {'windows':>7} {'OOS_ret%':>10} {'trades':>7} "
        f"{'win%':>6} {'sharpe':>7} {'max_dd%':>9}"
    )
    for sym in universe:
        cell = rows[sym]
        if "error" in cell:
            print(f"  {sym:<6}  ERROR ({cell['error']}): {cell.get('message', '')}")
            continue
        marker = " ✓" if cell["held_up"] else ""
        print(
            f"  {sym:<6} {cell['n_windows']:>7} {cell['oos_total_return_pct']:>10.2f} "
            f"{cell['oos_total_trades']:>7} {cell['oos_win_rate_pct']:>6.1f} "
            f"{cell['sharpe']:>7.2f} {cell['max_window_drawdown_pct']:>9.2f}{marker}"
        )

    avg_sharpe = (
        statistics.mean(rows[s]["sharpe"] for s in held_up if math.isfinite(rows[s]["sharpe"]))
        if held_up else float("-inf")
    )
    print(f"\n  held up on {len(held_up)} of {len(universe)} | avg Sharpe over held-up: {avg_sharpe:.2f}")

    passed = len(held_up) >= HELD_UP_MIN and avg_sharpe > SHARPE_MIN
    if not passed:
        print(
            f"\nVERDICT: FAIL — gate requires ≥{HELD_UP_MIN} symbols held up "
            f"AND avg Sharpe > {SHARPE_MIN}.\n"
            f"Survivor bias is NOT corrected; treat any borderline-pass result with extra skepticism."
        )
        return 1

    print(f"\nVERDICT: PASS — proposing today's paper-trade plan…")
    scan = invoke("scan_market", {
        "strategies": [{"name": name, "params": params, "label": name}],
        "symbols": held_up, "history_days": 365 * 2,
    }).result

    if not scan.results:
        print(f"  No signals from {name} on {held_up} today. Plan: hold off; rerun tomorrow.")
        return 0

    plan: list[dict] = []
    for sig in scan.results:
        req = {"symbol": sig.symbol, "side": sig.signal,
               "price": float(sig.price), "volume": 100}
        try:
            val = invoke("validate_order", {"request": req}).result.risk_check
        except ToolError as exc:
            print(f"  ! {sig.symbol} {sig.signal}: validator error {exc.code}")
            continue
        verdict = "APPROVE" if val.passed else "REJECT"
        print(
            f"  {verdict:<7} {sig.symbol} {sig.signal:<4} @ {sig.price:>10,.0f}  "
            f"check_id={val.check_id[:12]}…  violations={val.violations or '-'}"
        )
        if val.passed:
            plan.append({"request": req, "risk_check_id": val.check_id})

    if plan:
        print(f"\n  {len(plan)} approved order(s) — submit via paper trader during trading hours.")
        print(f"  Survivor bias: NOT corrected. Daily routine: rerun this command + submit approved orders.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
