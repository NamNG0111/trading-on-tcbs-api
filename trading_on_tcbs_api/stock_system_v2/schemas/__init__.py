"""Pydantic schemas for V2 public-API contracts (Phase 3).

Every cross-module return type lives here. Internal helpers may still pass
plain dicts; anything that crosses a module boundary, hits a public method,
or feeds a tool layer must use one of these models.
"""

from trading_on_tcbs_api.stock_system_v2.schemas.backtest import (
    BacktestResult,
    HoldingStrategy,
    WalkForwardResult,
    WalkForwardWindow,
    to_backtest_results,
)
from trading_on_tcbs_api.stock_system_v2.schemas.ohlcv import (
    OHLCVFrame,
    OHLCVSchemaError,
    closed_bars,
    validate_ohlcv,
)
from trading_on_tcbs_api.stock_system_v2.schemas.orders import (
    AccountSnapshot,
    OrderRequest,
    OrderResponse,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
)
from trading_on_tcbs_api.stock_system_v2.schemas.risk import (
    DEFAULT_TTL_SECONDS,
    CheckSeverity,
    MarketContext,
    RiskCheckFinding,
    RiskCheckResult,
)
from trading_on_tcbs_api.stock_system_v2.schemas.health import (
    HealthCheck,
    HealthStatus,
)
from trading_on_tcbs_api.stock_system_v2.schemas.signals import (
    ScanResult,
    Signal,
    SignalAction,
)
from trading_on_tcbs_api.stock_system_v2.schemas.strategy_meta import (
    StrategyDescription,
    StrategyParams,
)

__all__ = [
    # OHLCV
    "OHLCVFrame",
    "OHLCVSchemaError",
    "closed_bars",
    "validate_ohlcv",
    # Signals / scan
    "Signal",
    "SignalAction",
    "ScanResult",
    "HealthStatus",
    "HealthCheck",
    "StrategyDescription",
    "StrategyParams",
    # Orders / account
    "OrderRequest",
    "OrderResponse",
    "OrderSide",
    "OrderType",
    "OrderStatus",
    "Position",
    "AccountSnapshot",
    # Risk
    "RiskCheckResult",
    "RiskCheckFinding",
    "CheckSeverity",
    "MarketContext",
    "DEFAULT_TTL_SECONDS",
    # Backtest
    "BacktestResult",
    "WalkForwardResult",
    "WalkForwardWindow",
    "HoldingStrategy",
    "to_backtest_results",
]
