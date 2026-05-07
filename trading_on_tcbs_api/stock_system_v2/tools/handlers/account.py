"""Account tools: get_account, get_positions, get_audit_log."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field

from trading_on_tcbs_api.stock_system_v2 import config
from trading_on_tcbs_api.stock_system_v2.schemas import AccountSnapshot, Position
from trading_on_tcbs_api.stock_system_v2.tools.context import get_context
from trading_on_tcbs_api.stock_system_v2.tools.registry import tool


def _snapshot() -> AccountSnapshot:
    a = get_context().account
    positions = [
        Position(symbol=sym, quantity=qty, avg_cost=0.0)
        for sym, qty in a.get_positions().items()
        if qty > 0
    ]
    return AccountSnapshot(
        cash=a.cash,
        locked_cash=getattr(a, "locked_cash", 0.0),
        buying_power=a.get_buying_power_amount(),
        positions=positions,
        is_mock=getattr(a, "mock_mode", True),
        last_sync_status=getattr(a, "last_sync_status", "Mock"),
    )


# — get_account —

class GetAccountIn(BaseModel):
    pass


class GetAccountOut(BaseModel):
    snapshot: AccountSnapshot


@tool("get_account", input_model=GetAccountIn, output_model=GetAccountOut)
def get_account(_: GetAccountIn) -> GetAccountOut:
    """Return cash, buying power, positions, and mock/live status."""
    return GetAccountOut(snapshot=_snapshot())


# — get_positions —

class GetPositionsIn(BaseModel):
    pass


class GetPositionsOut(BaseModel):
    positions: list[Position]


@tool("get_positions", input_model=GetPositionsIn, output_model=GetPositionsOut)
def get_positions(_: GetPositionsIn) -> GetPositionsOut:
    """Return the current positions list (subset of `get_account`)."""
    return GetPositionsOut(positions=_snapshot().positions)


# — get_audit_log —

class GetAuditLogIn(BaseModel):
    limit: int = Field(50, ge=1, le=10_000)
    correlation_id: str | None = Field(
        None, description="Filter rows by their correlation_id field."
    )


class AuditRow(BaseModel):
    ts: str
    correlation_id: str | None = None
    decision: str | None = None
    symbol: str | None = None
    side: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class GetAuditLogOut(BaseModel):
    n_rows: int
    rows: list[AuditRow]


@tool("get_audit_log", input_model=GetAuditLogIn, output_model=GetAuditLogOut)
def get_audit_log(req: GetAuditLogIn) -> GetAuditLogOut:
    """Return the most recent decisions from `decisions.jsonl`.

    Each row is one order intent — submit, skip, reject — with the full
    request, response, validator findings, and account context that
    drove it. Use `correlation_id` to scope to one trade cycle.
    """
    path = Path(config.EXPORT_DIR) / "decisions.jsonl"
    if not path.exists():
        return GetAuditLogOut(n_rows=0, rows=[])
    raw = path.read_text().strip().splitlines()
    rows: list[AuditRow] = []
    for line in raw[-req.limit * 4 :]:  # over-read to allow filtering
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if req.correlation_id and obj.get("correlation_id") != req.correlation_id:
            continue
        known = {"ts", "correlation_id", "decision", "symbol", "side"}
        rows.append(
            AuditRow(
                ts=obj.get("ts", ""),
                correlation_id=obj.get("correlation_id"),
                decision=obj.get("decision"),
                symbol=obj.get("symbol"),
                side=obj.get("side"),
                extra={k: v for k, v in obj.items() if k not in known},
            )
        )
    rows = rows[-req.limit :]
    return GetAuditLogOut(n_rows=len(rows), rows=rows)
