"""End-to-end demo answering the §14 'what done looks like' prompt.

Drives the full toolbelt to answer:

    "Look at the universe. Find me a strategy that has held up
    out-of-sample on at least 5 symbols over the last 2 years.
    Show me the walk-forward stats. If you're confident, propose a
    paper-trade plan and run it for a week."

No internal V2 imports inside the workflow body — only `tools.invoke`.
That's the whole point: this script is a Python stand-in for what an
LLM agent would do over MCP.
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
from trading_on_tcbs_api.stock_system_v2.tools.context import (  # noqa: E402
    ToolContext,
    set_context,
)


def _bootstrap_real_context() -> None:
    """Build a `ToolContext` over the real cached data (no live auth)."""
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


def _annualised_sharpe(per_window_pct: list[float], windows_per_year: float = 4.0) -> float:
    if len(per_window_pct) < 2:
        return float("nan")
    decimals = [r / 100.0 for r in per_window_pct]
    mean = statistics.mean(decimals)
    stdev = statistics.pstdev(decimals)
    if stdev == 0:
        return 0.0
    return (mean / stdev) * math.sqrt(windows_per_year)


def main() -> int:
    _bootstrap_real_context()
    print("=" * 78)
    print("§14 demo — 'what done looks like'")
    print("=" * 78)

    # 1. Look at the universe.
    universe = invoke("list_symbols").result.symbols
    print(f"\nUniverse ({len(universe)}): {universe}")

    # 2. Discover strategies.
    strategies = invoke("list_strategies").result.strategies
    candidate_names = [n for n in strategies if n != "combined"]
    print(f"Candidate strategies: {candidate_names}")

    # 3. Walk-forward each (strategy × symbol). 2 years history,
    #    1y train + 6m test, 6m step → 1 OOS window per pair.
    print("\nRunning walk-forward × 2 years × every (strategy × symbol)…")
    matrix: dict[str, dict[str, dict]] = {strat: {} for strat in candidate_names}
    for strat in candidate_names:
        for sym in universe:
            try:
                resp = invoke("walk_forward", {
                    "strategy": strat,
                    "symbol": sym,
                    "days": 365 * 2,
                    "train_bars": 252,
                    "test_bars": 63,
                })
            except ToolError as exc:
                matrix[strat][sym] = {"error": exc.code}
                continue
            wf = resp.result.result
            per_window = [w.test_return_pct for w in wf.windows]
            matrix[strat][sym] = {
                "n_windows": wf.n_windows,
                "oos_total_return_pct": wf.oos_total_return_pct,
                "oos_avg_window_return_pct": wf.oos_avg_window_return_pct,
                "oos_total_trades": wf.oos_total_trades,
                "oos_win_rate_pct": wf.oos_win_rate_pct,
                "sharpe": _annualised_sharpe(per_window),
                "max_window_drawdown_pct": min(
                    (w.test_max_drawdown_pct for w in wf.windows), default=0.0,
                ),
            }

    # 4. "Held up OOS on ≥5 symbols": OOS total return > 0 AND ≥3 OOS trades.
    print("\nHeld-up matrix (✓ = OOS return > 0 with ≥3 trades; · = no; × = error):")
    print(f"{'strategy':<22} " + " ".join(f"{s:<5}" for s in universe) + "  count")
    print("-" * 78)

    held_up_count: dict[str, int] = {}
    for strat in candidate_names:
        row = []
        count = 0
        for sym in universe:
            cell = matrix[strat][sym]
            if "error" in cell:
                row.append("×")
            elif cell["oos_total_return_pct"] > 0 and cell["oos_total_trades"] >= 3:
                row.append("✓")
                count += 1
            else:
                row.append("·")
        held_up_count[strat] = count
        print(f"{strat:<22} " + " ".join(f"{c:<5}" for c in row) + f"  {count}")

    # 5. Pick the winner: most symbols held up; tiebreak on average Sharpe.
    qualifying = [s for s, n in held_up_count.items() if n >= 5]
    if not qualifying:
        print(
            "\nNo strategy held up OOS on ≥5 symbols over 2 years. "
            "Inconclusive; do not propose a paper-trade plan."
        )
        return 0

    def _score(strat: str) -> tuple[int, float]:
        finite_sharpes = [
            matrix[strat][s]["sharpe"]
            for s in universe
            if isinstance(matrix[strat][s].get("sharpe"), float)
            and math.isfinite(matrix[strat][s]["sharpe"])
        ]
        avg = statistics.mean(finite_sharpes) if finite_sharpes else float("-inf")
        return (held_up_count[strat], avg)

    winner = max(qualifying, key=_score)
    print(f"\nRecommended: {winner}  (held up on {held_up_count[winner]} of {len(universe)} symbols)")

    # 6. Show the WF stats for the winner.
    print(f"\nWalk-forward stats — {winner}:")
    print(
        f"  {'symbol':<6} {'windows':>7} {'OOS_ret%':>10} {'avg/win%':>10} "
        f"{'trades':>7} {'win%':>6} {'sharpe':>7} {'max_dd%':>9}"
    )
    held_symbols: list[str] = []
    for sym in universe:
        cell = matrix[winner][sym]
        if "error" in cell:
            print(f"  {sym:<6}  ERROR ({cell['error']})")
            continue
        held = (cell["oos_total_return_pct"] > 0 and cell["oos_total_trades"] >= 3)
        marker = " ✓" if held else "  "
        print(
            f"  {sym:<6} {cell['n_windows']:>7} {cell['oos_total_return_pct']:>10.2f} "
            f"{cell['oos_avg_window_return_pct']:>10.2f} {cell['oos_total_trades']:>7} "
            f"{cell['oos_win_rate_pct']:>6.1f} {cell['sharpe']:>7.2f} "
            f"{cell['max_window_drawdown_pct']:>9.2f}{marker}"
        )
        if held:
            held_symbols.append(sym)

    # 7. Confidence gate: at least one strategy held up; do we propose a plan?
    avg_sharpe = statistics.mean(
        matrix[winner][s]["sharpe"]
        for s in held_symbols
        if math.isfinite(matrix[winner][s]["sharpe"])
    ) if held_symbols else float("-inf")
    print(f"\n  avg sharpe over held-up symbols: {avg_sharpe:.2f}")

    confidence_ok = avg_sharpe > 0.3 and len(held_symbols) >= 5
    if not confidence_ok:
        print(
            "\nConfidence gate failed (need avg sharpe > 0.3 AND ≥5 symbols). "
            "Reporting evidence only; no paper-trade plan proposed."
        )
        print("\nSurvivor bias: NOT corrected. Treat the headline as an upper bound.")
        return 0

    # 8. Confident → propose a paper-trade plan: scan today, validate each
    #    signal against the held-up names, output approved orders.
    print("\nConfidence gate passed. Proposing a paper-trade plan…")
    scan = invoke("scan_market", {
        "strategies": [{"name": winner, "label": winner}],
        "symbols": held_symbols,
        "history_days": 365 * 2,
    }).result

    if not scan.results:
        print(f"  Today's scan produced no signals from {winner} on the held-up "
              f"symbols. Plan: hold off; rerun tomorrow.")
        return 0

    print(f"  {len(scan.results)} signals on {len(held_symbols)} held-up names today:")
    plan: list[dict] = []
    for sig in scan.results:
        req = {
            "symbol": sig.symbol, "side": sig.signal,
            "price": float(sig.price), "volume": 100,
        }
        try:
            val = invoke("validate_order", {"request": req}).result.risk_check
        except ToolError as exc:
            print(f"    ! {sig.symbol} {sig.signal} — validator error {exc.code}: {exc.message}")
            continue
        verdict = "APPROVE" if val.passed else "REJECT"
        print(
            f"    {verdict:<7} {sig.symbol} {sig.signal:<4} "
            f"@ {sig.price:>10,.0f}  → check_id={val.check_id[:12]}…  "
            f"violations={val.violations or '-'}"
        )
        if val.passed:
            plan.append({"request": req, "risk_check_id": val.check_id})

    if not plan:
        print("  No order survived validation. Plan: skip today.")
        return 0

    print(
        f"\nPaper-trade plan for the next 5 trading days:\n"
        f"  • Universe (held-up by {winner}): {held_symbols}\n"
        f"  • Daily routine: rerun this script's scan step; submit any "
        f"validator-approved BUY at the close, lot=100; let `OrderManager` "
        f"+ `OrderTracker` handle idempotency (kill-switch enforced via "
        f"EXECUTION_DISABLED=true).\n"
        f"  • Risk caps in force (PreTradeValidator): max 5 open positions, "
        f"price band ±7%, notional ≤ 500M VND, no shorting.\n"
        f"  • Today's approved orders ({len(plan)}):\n"
    )
    for p in plan:
        print(
            f"      {p['request']['side']:<4} {p['request']['volume']} "
            f"{p['request']['symbol']} @ {p['request']['price']:,.0f}  "
            f"(token={p['risk_check_id'][:12]}…)"
        )

    print(
        "\nSurvivor bias: NOT corrected — the universe is fixed at today's "
        "tickers, so any delisted name from earlier years is silently absent."
    )
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
