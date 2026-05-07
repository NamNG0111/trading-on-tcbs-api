"""Position reconciliation tests (Phase 5)."""

from __future__ import annotations

import pytest

from trading_on_tcbs_api.stock_system_v2.exceptions import PositionDriftError
from trading_on_tcbs_api.stock_system_v2.finance.reconciler import (
    assert_no_drift,
    reconcile_position_book,
)


def test_clean_books_no_drift():
    res = reconcile_position_book({"HPG": 100, "TCB": 200}, {"HPG": 100, "TCB": 200})
    assert not res.over_threshold
    assert res.diff == {}


def test_disagreement_surfaces_in_diff():
    res = reconcile_position_book({"HPG": 100}, {"HPG": 50})
    assert res.over_threshold
    assert res.diff == {"HPG": (100, 50)}


def test_extra_symbol_on_either_side_is_drift():
    res = reconcile_position_book({"HPG": 100}, {"HPG": 100, "TCB": 50})
    assert res.diff == {"TCB": (0, 50)}


def test_threshold_absorbs_small_delta():
    res = reconcile_position_book(
        {"HPG": 100}, {"HPG": 102}, threshold_shares=5,
    )
    assert not res.over_threshold


def test_assert_no_drift_raises_with_structured_details():
    with pytest.raises(PositionDriftError) as exc:
        assert_no_drift({"HPG": 100, "TCB": 200}, {"HPG": 50, "TCB": 200})
    err = exc.value
    assert err.details["diff"] == {"HPG": (100, 50)}
    assert err.details["symbols"] == ["HPG"]
    assert err.details["threshold"] == 0


def test_assert_no_drift_passes_when_clean():
    assert_no_drift({"HPG": 100}, {"HPG": 100})
    # No exception raised.
