"""Human-in-the-loop trading primitives (Phase 10).

Components:

  - `PendingSignalStore` — durable JSONL queue of signals awaiting
    confirmation; rebuilds open state from disk on restart.
  - `StrictRevalidator` (Chunk 2) — re-runs the originating strategy on
    fresh OHLCV before placement, ensures price drift is bounded.
  - `ConfirmationChannel` impls (Chunk 3 / 7) — Terminal + Telegram.
  - `HITLCoordinator` (Chunk 4) — orchestrates scan → channel →
    revalidator → validator → order_manager.

Read top-down for how a signal flows; read each module bottom-up for
the safety story.
"""

from trading_on_tcbs_api.stock_system_v2.execution.hitl.channels import (
    ConfirmationChannel,
    ConfirmationResponse,
    Decision,
    TerminalChannel,
)
from trading_on_tcbs_api.stock_system_v2.execution.hitl.coordinator import (
    HITLCoordinator,
    TradingMode,
)
from trading_on_tcbs_api.stock_system_v2.execution.hitl.pending_signal_store import (
    PendingSignalStore,
)
from trading_on_tcbs_api.stock_system_v2.execution.hitl.revalidator import (
    StrictRevalidator,
)

__all__ = [
    "PendingSignalStore",
    "StrictRevalidator",
    "ConfirmationChannel",
    "ConfirmationResponse",
    "Decision",
    "TerminalChannel",
    "HITLCoordinator",
    "TradingMode",
]
