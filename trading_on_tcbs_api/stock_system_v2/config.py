"""Back-compat shim — the canonical home is `stock_system_v2.settings.Settings`.

Every constant exported below is sourced from `Settings.load()`. New code
should depend on a `Settings` instance passed in explicitly; this module
exists so legacy imports (`from … import config`) keep resolving while the
DI refactor lands incrementally.
"""

from __future__ import annotations

import os

from trading_on_tcbs_api.stock_system_v2.settings import (
    DEFAULT_SYMBOLS,
    Settings,
    get_settings,
)

_settings: Settings = get_settings()

SYMBOLS = list(_settings.symbols)
TIMEFRAME = _settings.timeframe

RISK_PARAMS = {
    "max_capital_per_trade_pct": _settings.risk.max_capital_per_trade_pct,
    "stop_loss_pct": _settings.risk.stop_loss_pct,
    "take_profit_pct": _settings.risk.take_profit_pct,
    "max_open_positions": _settings.risk.max_open_positions,
}

BASE_DIR = str(_settings.base_dir)
DATA_DIR = str(_settings.data_dir)
LOG_DIR = str(_settings.log_dir)
TOKEN_FILE = str(_settings.token_file)
CREDENTIALS_FILE = str(_settings.credentials_file)
LOCAL_CONFIG_FILE = os.path.join(BASE_DIR, "config", "local_config.json")
EXPORT_DIR = str(_settings.export_dir)
BASE_URL = _settings.base_url

__all__ = [
    "BASE_DIR",
    "BASE_URL",
    "CREDENTIALS_FILE",
    "DATA_DIR",
    "DEFAULT_SYMBOLS",
    "EXPORT_DIR",
    "LOCAL_CONFIG_FILE",
    "LOG_DIR",
    "RISK_PARAMS",
    "SYMBOLS",
    "TIMEFRAME",
    "TOKEN_FILE",
]
