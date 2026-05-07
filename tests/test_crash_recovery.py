"""Crash-recovery test (Phase 5).

Exercises the contract: an order registered before a `kill -9` must be
recoverable from the ledger when the process restarts. We can't actually
SIGKILL pytest, so we use a subprocess that calls
`OrderTracker.register_pending` and then `os._exit(9)` — bypassing
atexit handlers, finalisers, and any clean shutdown path.

If the subprocess writes the PENDING row before exiting, a fresh
tracker on the same ledger file must surface the order via
`recover_open_orders()`. That's the whole guarantee Phase 5 needs:
the autotrader can recover its open-order state after any kind of
process termination.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

from trading_on_tcbs_api.stock_system_v2.execution.order_tracker import OrderTracker


def test_pending_row_survives_kill_9(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.csv"

    # Subprocess script: register one PENDING order, then exit hard.
    # `os._exit` skips finalisers — it's the closest we get to SIGKILL
    # from a pytest worker.
    script = textwrap.dedent(
        f"""
        import os
        from trading_on_tcbs_api.stock_system_v2.execution.order_tracker import OrderTracker
        from trading_on_tcbs_api.stock_system_v2.schemas import OrderRequest

        t = OrderTracker(r"{ledger}")
        req = OrderRequest(
            symbol="HPG",
            side="BUY",
            price=28000,
            volume=100,
            client_order_id="co_test_crashrecovery_001",
        )
        t.register_pending(req)
        os._exit(9)
        """
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(Path(__file__).resolve().parents[1]),
        capture_output=True,
        timeout=30,
    )
    # The hard exit code 9 is what we expect.
    assert result.returncode == 9

    # Now reopen the tracker on the same ledger and confirm the PENDING
    # row is recoverable.
    fresh = OrderTracker(str(ledger))
    open_orders = fresh.recover_open_orders()
    assert len(open_orders) == 1
    assert open_orders[0]["client_order_id"] == "co_test_crashrecovery_001"
    assert open_orders[0]["status"] == "PENDING"
    assert open_orders[0]["symbol"] == "HPG"
