"""Single-symbol backtester for V2 strategies.

Phase 2 upgrade: pluggable transaction costs + position sizer. Defaults are
chosen so an existing call site (`Backtester().run(strategy, symbol)`)
reproduces the legacy zero-cost, all-in behaviour exactly — call sites that
want realism opt in via constructor args.

The legacy `forward_returns` and `fixed_hold_results` blocks are preserved
unchanged; the unified Pydantic `BacktestResult` schema (Phase 3 deliverable)
is built from this dict by `to_backtest_result`.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd

from trading_on_tcbs_api.stock_system_v2.core.costs import ZERO_COSTS, TransactionCosts
from trading_on_tcbs_api.stock_system_v2.core.indicator_engine import IndicatorEngine
from trading_on_tcbs_api.stock_system_v2.core.position_sizer import (
    PositionSizer,
    SizerContext,
)
from trading_on_tcbs_api.stock_system_v2.data_ingest.data_provider import DataProvider
from trading_on_tcbs_api.stock_system_v2.obs import (
    get_logger,
    log_event,
    with_correlation,
)
from trading_on_tcbs_api.stock_system_v2.strategies import SignalStrategy

_logger = get_logger("backtester")


class _AllInSizer(PositionSizer):
    """Legacy default: spend all available cash on one name. Preserves the
    pre-Phase-2 behaviour so existing tests/scripts don't shift under us.
    """

    def size(self, ctx: SizerContext, history: pd.DataFrame | None = None) -> int:
        if ctx.cash <= ctx.price:
            return 0
        return self._round_lot(ctx.cash // ctx.price, ctx.lot_size)


class Backtester:
    """Engine to backtest a SignalStrategy against historical data."""

    def __init__(
        self,
        initial_capital: float = 100_000_000,
        *,
        costs: Optional[TransactionCosts] = None,
        sizer: Optional[PositionSizer] = None,
        data_provider: Optional[DataProvider] = None,
        indicator_engine: Optional[IndicatorEngine] = None,
        survivor_bias_corrected: bool = False,
    ):
        self.initial_capital = initial_capital
        self.costs = costs or ZERO_COSTS
        self.sizer = sizer or _AllInSizer()
        self.data_provider = data_provider or DataProvider(auth=None)
        self.indicator_engine = indicator_engine or IndicatorEngine()
        self.survivor_bias_corrected = survivor_bias_corrected

    def run(
        self,
        strategy: SignalStrategy,
        symbol: str,
        days: int = 365,
        forward_returns_days: List[int] = None,
        allow_multiple_buys: bool = False,
    ) -> Dict:
        """Run the backtest.

        Args:
            strategy: The strategy instance.
            symbol: Stock ticker.
            days: History duration.
            forward_returns_days: Days to statically hold after BUY.
            allow_multiple_buys: Plot subsequent BUY signals while holding
                shares (visualizer only).

        Returns:
            dict: Performance report. The schema is locked by
            `tests/test_backtester_e2e.py`. Includes the Phase-2 fields
            `costs`, `survivor_bias_corrected`, and `sizer_name`.
        """
        with with_correlation(prefix="backtest"):
            log_event(_logger, "backtest.start", symbol=symbol, strategy=type(strategy).__name__, days=days)
            df = self.data_provider.get_historical_data(symbol, days=days, include_live=False)
            if df.empty:
                log_event(_logger, "backtest.no_data", level=30, symbol=symbol)
                return {}

            df = self.indicator_engine.append_indicators(df)
            df = strategy.generate_signals(df)
            if 'signal' not in df.columns:
                log_event(_logger, "backtest.no_signal_column", level=40)
                return {}

        if forward_returns_days is None:
            forward_returns_days = [3, 5, 10, 20]

        forward_returns = {d: [] for d in forward_returns_days}
        signal_details = []
        df_len = len(df)
        prices = df['close'].values
        signals = df['signal'].values

        for idx in range(df_len):
            if signals[idx] == 1:
                entry_price = prices[idx]
                row_dict = df.iloc[idx].to_dict()
                row_dict['Ticker'] = symbol

                for d in forward_returns_days:
                    if idx + d < df_len:
                        exit_price = prices[idx + d]
                        ret = (exit_price - entry_price) / entry_price
                        forward_returns[d].append(ret)
                        row_dict[f'Return_{d}D_pct'] = ret * 100
                    else:
                        row_dict[f'Return_{d}D_pct'] = None

                signal_details.append(row_dict)

        # Native simulation (sizer + costs)
        cash = self.initial_capital
        shares = 0
        trades: list[dict] = []
        portfolio_values: list[float] = []
        peak_value = self.initial_capital
        max_drawdown = 0.0
        current_position: Optional[dict] = None
        closed_trades: list[dict] = []

        for i, row in df.iterrows():
            price = row['close']
            signal = row['signal']
            date = row['time']

            pv = cash + (shares * price)
            portfolio_values.append(pv)

            if pv > peak_value:
                peak_value = pv
            drawdown = (pv - peak_value) / peak_value if peak_value > 0 else 0
            if drawdown < max_drawdown:
                max_drawdown = drawdown

            if signal == 1:
                if shares == 0:
                    fill_price = self.costs.buy_fill_price(price)
                    ctx = SizerContext(cash=cash, equity=pv, price=fill_price, lot_size=self.costs.lot_size)
                    history_so_far = df.iloc[: i + 1] if isinstance(i, int) else df.loc[:i]
                    shares_to_buy = self.sizer.size(ctx, history_so_far)
                    # Trim down if commissions push cost above cash.
                    step = max(1, self.costs.lot_size)
                    while shares_to_buy > 0 and self.costs.buy_cost(fill_price, shares_to_buy) > cash:
                        shares_to_buy -= step
                    if shares_to_buy > 0:
                        cost = self.costs.buy_cost(fill_price, shares_to_buy)
                        notional = fill_price * shares_to_buy
                        if cost <= cash and notional >= self.costs.min_ticket_vnd:
                            cash -= cost
                            shares += shares_to_buy
                            current_position = {
                                'entry_price': fill_price,
                                'entry_date': date,
                                'shares': shares_to_buy,
                                'cost': cost,
                            }
                            trades.append({
                                'date': date,
                                'type': 'BUY',
                                'price': fill_price,
                                'shares': shares_to_buy,
                                'value': cost,
                            })
                elif allow_multiple_buys:
                    trades.append({
                        'date': date,
                        'type': 'BUY',
                        'price': price,
                        'shares': 0,
                        'value': 0,
                    })

            elif signal == -1 and shares > 0:
                fill_price = self.costs.sell_fill_price(price)
                revenue = self.costs.sell_proceeds(fill_price, shares)
                sold_shares = shares
                cash += revenue
                shares = 0

                if current_position:
                    pnl = revenue - current_position['cost']
                    entry_d = pd.to_datetime(current_position['entry_date'])
                    exit_d = pd.to_datetime(date)
                    hold_days = (exit_d - entry_d).days
                    closed_trades.append({'pnl': pnl, 'hold_days': hold_days})
                    current_position = None

                trades.append({
                    'date': date,
                    'type': 'SELL',
                    'price': fill_price,
                    'shares': sold_shares,
                    'value': revenue,
                })

        final_value = cash + (shares * df.iloc[-1]['close'])
        total_return = (final_value - self.initial_capital) / self.initial_capital

        gross_profit = sum(t['pnl'] for t in closed_trades if t['pnl'] > 0)
        gross_loss = abs(sum(t['pnl'] for t in closed_trades if t['pnl'] < 0))
        profit_factor = (gross_profit / gross_loss) if gross_loss != 0 else (float('inf') if gross_profit > 0 else 0)
        avg_hold_days = sum(t['hold_days'] for t in closed_trades) / len(closed_trades) if closed_trades else 0

        winning_trades = sum(1 for t in closed_trades if t['pnl'] > 0)
        win_rate = (winning_trades / len(closed_trades)) * 100 if closed_trades else 0

        # Fixed-hold simulation (costs applied here too — agents reading this
        # report should see consistent numbers across both holding modes).
        fixed_hold_results = {}
        for d in forward_returns_days:
            sim_cash = self.initial_capital
            sim_shares = 0
            sim_entry_cost = 0.0
            sim_entry_idx = -1
            sim_pnl_list: list[float] = []

            for idx in range(df_len):
                price = prices[idx]

                if sim_shares > 0 and (idx - sim_entry_idx == d or idx == df_len - 1):
                    fill = self.costs.sell_fill_price(price)
                    revenue = self.costs.sell_proceeds(fill, sim_shares)
                    pnl_pct = (revenue - sim_entry_cost) / sim_entry_cost if sim_entry_cost else 0.0
                    sim_pnl_list.append(pnl_pct)
                    sim_cash += revenue
                    sim_shares = 0
                    sim_entry_idx = -1

                if sim_shares == 0 and signals[idx] == 1:
                    fill = self.costs.buy_fill_price(price)
                    if sim_cash > fill:
                        ctx = SizerContext(cash=sim_cash, equity=sim_cash, price=fill, lot_size=self.costs.lot_size)
                        shares_to_buy = self.sizer.size(ctx, df.iloc[: idx + 1])
                        step = max(1, self.costs.lot_size)
                        while shares_to_buy > 0 and self.costs.buy_cost(fill, shares_to_buy) > sim_cash:
                            shares_to_buy -= step
                        if shares_to_buy > 0:
                            sim_entry_cost = self.costs.buy_cost(fill, shares_to_buy)
                            if sim_entry_cost <= sim_cash:
                                sim_cash -= sim_entry_cost
                                sim_shares = shares_to_buy
                                sim_entry_idx = idx

            sim_final_value = sim_cash + (sim_shares * prices[-1])
            sim_total_ret = (sim_final_value - self.initial_capital) / self.initial_capital

            win_r = (sum(1 for x in sim_pnl_list if x > 0) / len(sim_pnl_list) * 100) if sim_pnl_list else 0
            avg_r = (sum(sim_pnl_list) / len(sim_pnl_list) * 100) if sim_pnl_list else 0
            max_r = (max(sim_pnl_list) * 100) if sim_pnl_list else 0
            min_r = (min(sim_pnl_list) * 100) if sim_pnl_list else 0

            fixed_hold_results[d] = {
                'total_return_pct': sim_total_ret * 100,
                'win_rate_pct': win_r,
                'avg_trade_pct': avg_r,
                'best_trade_pct': max_r,
                'worst_trade_pct': min_r,
                'total_trades': len(sim_pnl_list),
            }

        report = {
            'symbol': symbol,
            'start_date': df.iloc[0]['time'].strftime('%Y-%m-%d'),
            'end_date': df.iloc[-1]['time'].strftime('%Y-%m-%d'),
            'initial_capital': self.initial_capital,
            'final_value': final_value,
            'total_return_pct': total_return * 100,
            'total_trades': len(trades),
            'win_rate_pct': win_rate,
            'max_drawdown_pct': max_drawdown * 100,
            'profit_factor': profit_factor,
            'avg_hold_days': avg_hold_days,
            'history_days': days,
            'forward_returns': forward_returns,
            'fixed_hold_results': fixed_hold_results,
            'trades_log': trades,
            'signal_details': signal_details,
            # Phase 2 additions —
            'costs': self.costs.model_dump(),
            'sizer_name': type(self.sizer).__name__,
            'survivor_bias_corrected': self.survivor_bias_corrected,
        }

        return report


if __name__ == "__main__":
    pass
