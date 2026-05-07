"""Walk-forward backtester (Phase 2).

Splits a single symbol's history into N rolling (train, test) windows and
reports out-of-sample-only stats. The strategies V2 ships today carry no
trainable parameters, so the "train" segment is currently used only as a
warmup buffer (indicators stabilise) — agents picking parameters by symbol
will fit them on `train` and freeze them for `test` when that capability
lands.

The aggregate report (`WalkForwardResult`) is the canonical evidence an
agent should cite when claiming a strategy "works" on a name. In-sample
backtests are not allowed as evidence.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from trading_on_tcbs_api.stock_system_v2.core.backtest_result import (
    WalkForwardResult,
    WalkForwardWindow,
)
from trading_on_tcbs_api.stock_system_v2.core.costs import ZERO_COSTS, TransactionCosts
from trading_on_tcbs_api.stock_system_v2.core.indicator_engine import IndicatorEngine
from trading_on_tcbs_api.stock_system_v2.core.position_sizer import (
    PositionSizer,
    SizerContext,
)
from trading_on_tcbs_api.stock_system_v2.data_ingest.data_provider import DataProvider
from trading_on_tcbs_api.stock_system_v2.strategies import SignalStrategy


class WalkForwardBacktester:
    """Rolling train/test backtest harness.

    A single dataframe is split into N anchored windows of `(train_bars,
    test_bars)`. The strategy is run **on the full prefix up through each
    test window's end** (so indicator warmup is preserved) but only the
    trades that fall inside the test window are tallied. This isolates
    out-of-sample performance.
    """

    def __init__(
        self,
        train_bars: int = 252,
        test_bars: int = 63,
        step_bars: Optional[int] = None,
        initial_capital: float = 100_000_000,
        costs: Optional[TransactionCosts] = None,
        sizer: Optional[PositionSizer] = None,
        data_provider: Optional[DataProvider] = None,
        indicator_engine: Optional[IndicatorEngine] = None,
        survivor_bias_corrected: bool = False,
    ):
        if train_bars < 30:
            raise ValueError("train_bars must be >= 30 for indicator warmup")
        if test_bars < 5:
            raise ValueError("test_bars must be >= 5")
        self.train_bars = train_bars
        self.test_bars = test_bars
        self.step_bars = step_bars or test_bars
        self.initial_capital = initial_capital
        self.costs = costs or ZERO_COSTS
        self.sizer = sizer
        self.data_provider = data_provider or DataProvider(auth=None)
        self.indicator_engine = indicator_engine or IndicatorEngine()
        self.survivor_bias_corrected = survivor_bias_corrected

    def run(self, strategy: SignalStrategy, symbol: str, days: int = 365 * 3) -> WalkForwardResult:
        df = self.data_provider.get_historical_data(symbol, days=days, include_live=False)
        if df.empty:
            return self._empty_result(symbol, strategy)

        df = self.indicator_engine.append_indicators(df)
        df = strategy.generate_signals(df).reset_index(drop=True)

        n = len(df)
        if n < self.train_bars + self.test_bars:
            return self._empty_result(symbol, strategy)

        windows: list[WalkForwardWindow] = []
        equity_curve: list[float] = [self.initial_capital]
        all_test_trades = 0
        all_test_wins = 0

        # Walk anchored from the start: train spans [0, train_bars),
        # successive test segments slide forward by `step_bars`.
        test_start = self.train_bars
        idx = 0
        while test_start + self.test_bars <= n:
            test_end = test_start + self.test_bars
            stats = self._simulate_test_window(df, test_start, test_end)

            windows.append(
                WalkForwardWindow(
                    window_index=idx,
                    train_start=str(df.iloc[0]['time'])[:10],
                    train_end=str(df.iloc[test_start - 1]['time'])[:10],
                    test_start=str(df.iloc[test_start]['time'])[:10],
                    test_end=str(df.iloc[test_end - 1]['time'])[:10],
                    n_test_trades=stats['trades'],
                    test_return_pct=stats['return_pct'],
                    test_win_rate_pct=stats['win_rate_pct'],
                    test_max_drawdown_pct=stats['max_drawdown_pct'],
                )
            )

            all_test_trades += stats['trades']
            all_test_wins += stats['wins']
            equity_curve.append(equity_curve[-1] * (1.0 + stats['return_pct'] / 100.0))

            test_start += self.step_bars
            idx += 1

        if not windows:
            return self._empty_result(symbol, strategy)

        oos_total_return_pct = (equity_curve[-1] / equity_curve[0] - 1.0) * 100.0
        oos_avg_window_return_pct = float(np.mean([w.test_return_pct for w in windows]))
        oos_win_rate_pct = (all_test_wins / all_test_trades * 100.0) if all_test_trades else 0.0

        return WalkForwardResult(
            symbol=symbol,
            strategy_name=type(strategy).__name__,
            n_windows=len(windows),
            oos_total_return_pct=oos_total_return_pct,
            oos_avg_window_return_pct=oos_avg_window_return_pct,
            oos_win_rate_pct=oos_win_rate_pct,
            oos_total_trades=all_test_trades,
            windows=windows,
            costs=self.costs.model_dump(),
            sizer_name=type(self.sizer).__name__ if self.sizer is not None else "AllInSizer",
            survivor_bias_corrected=self.survivor_bias_corrected,
        )

    # — internals —

    def _empty_result(self, symbol: str, strategy: SignalStrategy) -> WalkForwardResult:
        return WalkForwardResult(
            symbol=symbol,
            strategy_name=type(strategy).__name__,
            n_windows=0,
            oos_total_return_pct=0.0,
            oos_avg_window_return_pct=0.0,
            oos_win_rate_pct=0.0,
            oos_total_trades=0,
            windows=[],
            costs=self.costs.model_dump(),
            sizer_name=type(self.sizer).__name__ if self.sizer is not None else "AllInSizer",
            survivor_bias_corrected=self.survivor_bias_corrected,
        )

    def _simulate_test_window(self, df: pd.DataFrame, start: int, end: int) -> dict:
        cash = self.initial_capital
        shares = 0
        peak = cash
        max_dd = 0.0
        trades = 0
        wins = 0
        last_buy_cost = 0.0

        for idx in range(start, end):
            price = df.iloc[idx]['close']
            signal = df.iloc[idx]['signal']

            pv = cash + shares * price
            if pv > peak:
                peak = pv
            dd = (pv - peak) / peak if peak > 0 else 0.0
            if dd < max_dd:
                max_dd = dd

            if signal == 1 and shares == 0:
                fill = self.costs.buy_fill_price(price)
                if self.sizer is not None:
                    ctx = SizerContext(cash=cash, equity=pv, price=fill, lot_size=self.costs.lot_size)
                    shares_to_buy = self.sizer.size(ctx, df.iloc[: idx + 1])
                else:
                    shares_to_buy = int(cash // fill) if cash > fill else 0
                    shares_to_buy = (shares_to_buy // self.costs.lot_size) * self.costs.lot_size if self.costs.lot_size > 1 else shares_to_buy
                step = max(1, self.costs.lot_size)
                while shares_to_buy > 0 and self.costs.buy_cost(fill, shares_to_buy) > cash:
                    shares_to_buy -= step
                if shares_to_buy > 0:
                    cost = self.costs.buy_cost(fill, shares_to_buy)
                    notional = fill * shares_to_buy
                    if cost <= cash and notional >= self.costs.min_ticket_vnd:
                        cash -= cost
                        shares = shares_to_buy
                        last_buy_cost = cost
            elif signal == -1 and shares > 0:
                fill = self.costs.sell_fill_price(price)
                proceeds = self.costs.sell_proceeds(fill, shares)
                if proceeds > last_buy_cost:
                    wins += 1
                trades += 1
                cash += proceeds
                shares = 0
                last_buy_cost = 0.0

        # Force-close at window end so the next window starts flat.
        if shares > 0:
            price = df.iloc[end - 1]['close']
            fill = self.costs.sell_fill_price(price)
            proceeds = self.costs.sell_proceeds(fill, shares)
            if proceeds > last_buy_cost:
                wins += 1
            trades += 1
            cash += proceeds
            shares = 0

        final = cash
        ret_pct = (final - self.initial_capital) / self.initial_capital * 100.0
        return {
            'trades': trades,
            'wins': wins,
            'return_pct': ret_pct,
            'win_rate_pct': (wins / trades * 100.0) if trades else 0.0,
            'max_drawdown_pct': max_dd * 100.0,
        }
