"""Sanity checks for the typed exception hierarchy (Phase 3)."""

from __future__ import annotations

import pytest

from trading_on_tcbs_api.stock_system_v2.exceptions import (
    AuthExpiredError,
    DataFetchError,
    InsufficientHistoryError,
    InvalidParameterError,
    OrderRejectedError,
    RiskLimitViolatedError,
    StaleCacheError,
    StockSystemError,
)


def test_hierarchy():
    assert issubclass(DataFetchError, StockSystemError)
    assert issubclass(StaleCacheError, DataFetchError)
    assert issubclass(InsufficientHistoryError, DataFetchError)
    assert issubclass(InvalidParameterError, StockSystemError)
    assert issubclass(AuthExpiredError, StockSystemError)
    assert issubclass(OrderRejectedError, StockSystemError)
    assert issubclass(RiskLimitViolatedError, StockSystemError)


def test_details_round_trip():
    err = StaleCacheError("cache is too old", details={"symbol": "HPG", "age_days": 7})
    assert err.message == "cache is too old"
    assert err.details == {"symbol": "HPG", "age_days": 7}
    assert "HPG" in str(err)


def test_can_be_caught_via_root():
    with pytest.raises(StockSystemError):
        raise InvalidParameterError("bad value")
