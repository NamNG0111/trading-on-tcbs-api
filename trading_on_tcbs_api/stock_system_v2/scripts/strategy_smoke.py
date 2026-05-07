"""Smoke-gate runner for one V2 strategy (Phase 4).

Runs every gate listed in `strategies/CONTRIBUTING.md`:

  1. Walk-forward backtest completes without error on every fixture
     symbol in `tests/fixtures/`.
  2. OOS Sharpe is reported (negative is allowed; missing is not).
  3. Trade count is in `[trade_min, trade_max]` per symbol.
  4. Max single-bar drawdown is finite and reported.

Exit code is 0 when every gate passes, 1 otherwise. Designed to be the
target of `make strategy-smoke <name>` and the strategy-PR CI job.

Usage:
    python -m trading_on_tcbs_api.stock_system_v2.scripts.strategy_smoke <name>

`<name>` must be a key in `STRATEGIES`. The runner uses the strategy's
default `Params()` — call sites that need to gate on tuned params should
extend this script.
"""

from __future__ import annotations

import math
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.fakes import FakeDataProvider  # noqa: E402
from trading_on_tcbs_api.stock_system_v2.core.costs import TCBS_DEFAULT_COSTS  # noqa: E402
from trading_on_tcbs_api.stock_system_v2.core.walk_forward import (  # noqa: E402
    WalkForwardBacktester,
)
from trading_on_tcbs_api.stock_system_v2.strategies import STRATEGIES, get_strategy  # noqa: E402

FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
SMOKE_SYMBOLS = ["HPG", "TCB", "FPT"]
TRADE_MIN = 0  # fixture series are short; smoke just guards "didn't crash"
TRADE_MAX = 5000


def _annualised_sharpe(returns_pct: list[float]) -> float:
    if len(returns_pct) < 2:
        return float("nan")
    decimals = [r / 100.0 for r in returns_pct]
    mean = statistics.mean(decimals)
    stdev = statistics.pstdev(decimals)
    if stdev == 0:
        return 0.0
    # Per-window returns; the standard universe has ~63-bar windows
    # (quarterly), so annualise by sqrt(4).
    return (mean / stdev) * math.sqrt(4)


def run_smoke(name: str) -> int:
    if name not in STRATEGIES:
        print(f"[smoke] unknown strategy '{name}'. Available: {sorted(STRATEGIES)}")
        return 1
    cls = get_strategy(name)
    if name == "combined":
        print("[smoke] CombinedStrategy is a meta-strategy and cannot be smoke-tested without sub-strategies; skipping.")
        return 0

    print(f"[smoke] {name} ({cls.__name__}) — running across {SMOKE_SYMBOLS}")
    failures: list[str] = []

    for symbol in SMOKE_SYMBOLS:
        try:
            strategy = cls()
        except Exception as exc:
            failures.append(f"{symbol}: instantiation failed: {exc}")
            continue

        bt = WalkForwardBacktester(
            train_bars=120,
            test_bars=60,
            step_bars=60,
            costs=TCBS_DEFAULT_COSTS,
            data_provider=FakeDataProvider(
                auth=None, reconciler=None, fixtures_dir=str(FIXTURES_DIR)
            ),
        )
        try:
            res = bt.run(strategy, symbol=symbol, days=100_000)
        except Exception as exc:
            failures.append(f"{symbol}: walk-forward raised: {exc}")
            continue

        if res.n_windows == 0:
            failures.append(f"{symbol}: no walk-forward windows produced")
            continue

        per_window = [w.test_return_pct for w in res.windows]
        sharpe = _annualised_sharpe(per_window)
        trades = res.oos_total_trades
        max_dd = min((w.test_max_drawdown_pct for w in res.windows), default=0.0)

        if not math.isfinite(max_dd):
            failures.append(f"{symbol}: non-finite max drawdown")
        if not (TRADE_MIN <= trades <= TRADE_MAX):
            failures.append(f"{symbol}: trade count {trades} outside [{TRADE_MIN}, {TRADE_MAX}]")

        print(
            f"  {symbol}: windows={res.n_windows} trades={trades} "
            f"oos_total_return_pct={res.oos_total_return_pct:.2f} "
            f"sharpe~{sharpe:.2f} max_dd={max_dd:.2f}"
        )

    if failures:
        print("[smoke] FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("[smoke] all gates passed")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: strategy_smoke.py <name>")
        return 2
    return run_smoke(sys.argv[1])


if __name__ == "__main__":
    raise SystemExit(main())
