"""Sanity checks for the transaction cost model."""

from __future__ import annotations

import pytest

from trading_on_tcbs_api.stock_system_v2.core.costs import (
    TCBS_DEFAULT_COSTS,
    ZERO_COSTS,
    TransactionCosts,
)


def test_zero_costs_preserves_mid_price():
    # ZERO_COSTS still charges sell_tax_bps=10 by current defaults; only the
    # slippage and commission legs zero out.
    assert ZERO_COSTS.buy_fill_price(100.0) == 100.0
    assert ZERO_COSTS.sell_fill_price(100.0) == 100.0
    assert ZERO_COSTS.buy_cost(100.0, 10) == 1000.0
    # Sell tax of 10 bps applies to gross proceeds.
    assert ZERO_COSTS.sell_proceeds(100.0, 10) == pytest.approx(1000.0 * (1 - 10 / 10_000))


def test_tcbs_defaults_charge_each_side():
    costs = TCBS_DEFAULT_COSTS
    # Buy at mid 1000 with default 5 bps slippage → fill 1000.5
    assert costs.buy_fill_price(1000.0) == pytest.approx(1000.5)
    assert costs.sell_fill_price(1000.0) == pytest.approx(999.5)

    # Defaults today: commission_bps=0, sell_tax_bps=10.
    buy_cost = costs.buy_cost(costs.buy_fill_price(1000.0), 100)
    assert buy_cost == pytest.approx(100050.0 * (1 + costs.commission_bps / 10_000))

    sell = costs.sell_proceeds(costs.sell_fill_price(1000.0), 100)
    expected_sell = 99950.0 * (1 - costs.commission_bps / 10_000 - costs.sell_tax_bps / 10_000)
    assert sell == pytest.approx(expected_sell)


def test_round_shares_floors_to_lot():
    costs = TransactionCosts(lot_size=100)
    assert costs.round_shares(150) == 100
    assert costs.round_shares(199) == 100
    assert costs.round_shares(99) == 0
    assert costs.round_shares(200) == 200


def test_negative_params_rejected():
    with pytest.raises(ValueError):
        TransactionCosts(commission_bps=-1.0)
