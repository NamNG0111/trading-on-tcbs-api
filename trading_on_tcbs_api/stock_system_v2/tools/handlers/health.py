"""Health tool: health_check."""

from __future__ import annotations

from pydantic import BaseModel

from trading_on_tcbs_api.stock_system_v2.core.health import health_check as _health_check
from trading_on_tcbs_api.stock_system_v2.schemas import HealthStatus
from trading_on_tcbs_api.stock_system_v2.tools.context import get_context
from trading_on_tcbs_api.stock_system_v2.tools.registry import tool


class HealthCheckIn(BaseModel):
    pass


class HealthCheckOut(BaseModel):
    status: HealthStatus


@tool("health_check", input_model=HealthCheckIn, output_model=HealthCheckOut)
def health_check(_: HealthCheckIn) -> HealthCheckOut:
    """Report auth validity, data freshness, open orders, and last error.

    Designed to be called in a tight loop. Never raises — every check
    becomes a row inside `HealthStatus.checks` with status `ok`,
    `warn`, `fail`, or `unknown`. `ok=True` only when no check is
    `fail` or `unknown`.
    """
    ctx = get_context()
    status = _health_check(
        auth=ctx.auth,
        tracker=ctx.order_tracker,
        data_dir=str(ctx.settings.data_dir),
    )
    return HealthCheckOut(status=status)
