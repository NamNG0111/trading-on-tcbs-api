"""V2 application settings (Phase 3).

Replaces ad-hoc `from … import config` access with an explicit Pydantic
`Settings` value object. The intended pattern is:

    settings = Settings.load()                  # one-shot at process start
    scanner  = MarketScanner(settings=settings, …)

Per-call overrides use `settings.model_copy(update={...})` which Pydantic
validates again — this is how a Phase-7 tool layer will accept caller
overrides (different universe, different risk caps) without reaching for a
global.

`config.py` keeps its module-level constants for back-compat — they now
read from `Settings.load()` so any legacy import sees the same values.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_SYMBOLS: tuple[str, ...] = (
    "TCB", "HPG", "SSI", "VHM", "VIC", "VRE", "VNM", "FPT",
)


class RiskParams(BaseModel):
    """Operator-tunable risk caps for the autotrader / scanner."""

    model_config = ConfigDict(frozen=True)

    max_capital_per_trade_pct: float = Field(0.10, gt=0.0, le=1.0)
    stop_loss_pct: float = Field(0.05, gt=0.0, le=1.0)
    take_profit_pct: float = Field(0.10, gt=0.0, le=1.0)
    max_open_positions: int = Field(5, ge=1)
    # — Phase-10 hard caps. Sentinel 0 disables the check. —
    max_position_size_vnd: int = Field(
        50_000_000, ge=0,
        description="Per-name post-trade position cap, in VND. 0 disables.",
    )
    max_daily_loss_vnd: int = Field(
        10_000_000, ge=0,
        description="Realized loss ceiling for one trading day, in VND. 0 disables.",
    )
    max_trades_per_day: int = Field(
        10, ge=0,
        description="Maximum orders the live trader will submit in one day. 0 disables.",
    )


class Settings(BaseModel):
    """Frozen Pydantic value object describing one V2 process configuration.

    Construction: prefer `Settings.load()` so machine-specific overrides
    in `config/local_config.json` and a couple of env vars get picked up.
    Tests should construct directly with explicit args to avoid coupling
    to the on-disk state.
    """

    model_config = ConfigDict(frozen=True)

    base_dir: Path
    data_dir: Path
    export_dir: Path
    log_dir: Path
    token_file: Path
    credentials_file: Path
    base_url: str = "https://openapi.tcbs.com.vn"

    symbols: tuple[str, ...] = DEFAULT_SYMBOLS
    timeframe: str = "1D"
    risk: RiskParams = Field(default_factory=RiskParams)

    execution_disabled: bool = Field(
        False,
        description="Phase-5 hard kill-switch. When True, every order placement returns rejected, regardless of safe-mode.",
    )

    # — Phase 10: HITL configuration —
    trading_mode: Literal["hitl", "auto"] = Field(
        "hitl",
        description="`hitl` requires per-signal human confirmation; `auto` skips the channel but still re-validates.",
    )
    confirmation_channel: Literal["terminal", "telegram"] = Field(
        "terminal",
        description="Which channel a coordinator uses to ask for confirmation in HITL mode.",
    )
    confirmation_timeout_sec: int = Field(
        3600, gt=0, description="How long a pending signal stays awaiting a reply before auto-expiring.",
    )
    max_price_drift_pct: float = Field(
        2.0, gt=0.0, le=50.0,
        description="Re-validator's drift cap, in percent. Default 2%.",
    )
    telegram_bot_token: str | None = Field(
        None, description="Telegram Bot API token; required when confirmation_channel='telegram'.",
    )
    telegram_chat_id: str | None = Field(
        None, description="Target chat id for HITL prompts; required when confirmation_channel='telegram'.",
    )

    @classmethod
    def load(cls, *, base_dir: Path | None = None) -> "Settings":
        """Build a `Settings` from disk + env, with sane fallbacks.

        - `base_dir` defaults to `trading_on_tcbs_api/` (one level above
          this module) — matches the legacy `config.BASE_DIR`.
        - `local_config.json` (gitignored) overrides `data_dir` and
          `export_dir`. Used to point them at Google Drive on the dev box.
        - `EXECUTION_DISABLED=true` env var flips the kill-switch on.
        """
        root = base_dir or Path(__file__).resolve().parents[1]
        data_dir = root / "data" / "stocks"
        export_dir = root / "data" / "exports"
        local_cfg = root / "config" / "local_config.json"
        if local_cfg.exists():
            try:
                cfg = json.loads(local_cfg.read_text())
            except (OSError, json.JSONDecodeError) as exc:
                # Surface but don't fail — process must still start.
                print(f"[settings] warning: could not read {local_cfg}: {exc}")
                cfg = {}
            data_dir = Path(cfg.get("DATA_DIR", data_dir))
            export_dir = Path(cfg.get("EXPORT_DIR", export_dir))

        execution_disabled = os.environ.get("EXECUTION_DISABLED", "").lower() in {"1", "true", "yes"}

        for d in (data_dir, export_dir, root / "logs"):
            d.mkdir(parents=True, exist_ok=True)

        return cls(
            base_dir=root,
            data_dir=data_dir,
            export_dir=export_dir,
            log_dir=root / "logs",
            token_file=root / "config" / "token.json",
            credentials_file=root / "config" / "credentials.yaml",
            execution_disabled=execution_disabled,
        )


_cached: Settings | None = None


def get_settings() -> Settings:
    """Return a process-wide `Settings` singleton, lazily built on first call.

    Public callers should usually construct + inject `Settings` themselves.
    This accessor exists so `config.py` (the back-compat shim) can resolve
    its module-level constants without rewiring every legacy import.
    """
    global _cached
    if _cached is None:
        _cached = Settings.load()
    return _cached
