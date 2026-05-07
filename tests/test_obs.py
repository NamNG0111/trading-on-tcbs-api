"""Observability primitives tests (Phase 6)."""

from __future__ import annotations

import io
import json
import logging
from pathlib import Path

import pytest

from trading_on_tcbs_api.stock_system_v2.obs import (
    configure_logging,
    current_correlation_id,
    get_logger,
    log_event,
    new_correlation_id,
    record_metric,
    with_correlation,
    write_decision,
)


@pytest.fixture
def captured_log() -> io.StringIO:
    buf = io.StringIO()
    configure_logging(stream=buf, level=logging.INFO, force=True)
    return buf


def _lines(buf: io.StringIO) -> list[dict]:
    raw = buf.getvalue().strip().splitlines()
    return [json.loads(line) for line in raw if line.strip()]


def test_log_event_emits_json(captured_log):
    logger = get_logger("test")
    log_event(logger, "scan.start", n_symbols=5)
    rows = _lines(captured_log)
    assert len(rows) == 1
    row = rows[0]
    assert row["event"] == "scan.start"
    assert row["n_symbols"] == 5
    assert row["logger"] == "v2.test"
    assert "ts" in row
    assert "correlation_id" not in row  # outside any scope


def test_correlation_propagates_to_log_lines(captured_log):
    logger = get_logger("test")
    with with_correlation(prefix="scan") as cid:
        log_event(logger, "inner")
        assert current_correlation_id() == cid
    rows = _lines(captured_log)
    assert rows[0]["correlation_id"] == cid
    assert cid.startswith("scan_")
    assert current_correlation_id() is None  # reset on exit


def test_explicit_correlation_id(captured_log):
    logger = get_logger("test")
    with with_correlation("custom_id_42"):
        log_event(logger, "x")
    assert _lines(captured_log)[0]["correlation_id"] == "custom_id_42"


def test_record_metric(captured_log):
    record_metric("orders.placed", 1.0, symbol="HPG")
    rows = _lines(captured_log)
    assert rows[-1]["event"] == "metric"
    assert rows[-1]["metric"] == "orders.placed"
    assert rows[-1]["value"] == 1.0
    assert rows[-1]["symbol"] == "HPG"


def test_new_correlation_id_unique():
    a = new_correlation_id("scan")
    b = new_correlation_id("scan")
    assert a != b
    assert a.startswith("scan_")


def test_write_decision_appends_jsonl(tmp_path: Path):
    target = tmp_path / "decisions.jsonl"
    with with_correlation("test_corr_1"):
        write_decision({"decision": "submit", "symbol": "HPG"}, path=target)
        write_decision({"decision": "skip:cash", "symbol": "TCB"}, path=target)
    lines = target.read_text().strip().splitlines()
    assert len(lines) == 2
    rows = [json.loads(line) for line in lines]
    assert rows[0]["decision"] == "submit"
    assert rows[1]["symbol"] == "TCB"
    assert all(r["correlation_id"] == "test_corr_1" for r in rows)
    assert all("ts" in r for r in rows)


def test_logger_serialises_pydantic_models(captured_log):
    from trading_on_tcbs_api.stock_system_v2.schemas import OrderRequest

    logger = get_logger("test")
    req = OrderRequest(symbol="HPG", side="BUY", price=28000, volume=100)
    log_event(logger, "order.req", request=req)
    row = _lines(captured_log)[0]
    assert isinstance(row["request"], dict)
    assert row["request"]["symbol"] == "HPG"
