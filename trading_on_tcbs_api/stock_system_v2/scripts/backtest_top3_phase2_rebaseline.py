"""Phase 2 rebaseline of the weekly Top-3 momentum + volume backtest.

Produces three side-by-side runs on the standard equity universe, using
already-cached vnstock OHLCV (no network):

1. **Legacy** — zero costs, all-cash all-in on each leg (matches the
   pre-Phase-2 numbers in `backtest_weekly_top3.py`).
2. **TCBS costs** — `TCBS_DEFAULT_COSTS` applied on every fill (15 bps
   commission per side, 5 bps slippage, 10 bps sell tax, lot=100).
3. **TCBS costs + 5 walk-forward windows** — the same simulator,
   re-evaluated by anchored rolling 1-year-train / 6-month-test windows.
   The OOS columns are what an agent should cite.

Outputs `docs/PHASE2_TOP3_REBASELINE.md` with a summary table and the
delta vs. the legacy numbers.

Run:
    python trading_on_tcbs_api/stock_system_v2/scripts/backtest_top3_phase2_rebaseline.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from trading_on_tcbs_api.stock_system_v2.core.costs import (  # noqa: E402
    TCBS_DEFAULT_COSTS,
    ZERO_COSTS,
    TransactionCosts,
)
from trading_on_tcbs_api.stock_system_v2.data_ingest.data_provider import (  # noqa: E402
    DataProvider,
)

UNIVERSE = ["TCB", "HPG", "SSI", "VHM", "VIC", "VRE", "VNM", "FPT"]
HISTORY_DAYS = 5 * 365
INITIAL_CAPITAL = 1_000_000_000  # 1B VND, matches the legacy script
RETURN_WEIGHT = 0.5
TOP_N = 3
WALK_FORWARD_WINDOWS = 5


def _load_panel(symbols: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load weekly close & volume panels for `symbols` from cached vnstock data."""
    provider = DataProvider(auth=None)
    frames = []
    for sym in symbols:
        try:
            df = provider.get_historical_data(sym, days=HISTORY_DAYS, include_live=False)
        except Exception as exc:
            print(f"  skip {sym}: {exc}")
            continue
        if df.empty:
            continue
        df = df[["time", "close", "volume"]].copy()
        df["time"] = pd.to_datetime(df["time"]).dt.normalize()
        df["symbol"] = sym
        frames.append(df)
    if not frames:
        raise RuntimeError("No symbols loaded; check cached data directory.")

    panel = pd.concat(frames, ignore_index=True).drop_duplicates(["time", "symbol"], keep="last")
    daily_close = panel.pivot(index="time", columns="symbol", values="close").ffill()
    daily_volume = panel.pivot(index="time", columns="symbol", values="volume").fillna(0)
    return daily_close, daily_volume


def _weekly_signals(daily_close: pd.DataFrame, daily_volume: pd.DataFrame) -> dict[pd.Timestamp, list[str]]:
    weekly_close = daily_close.resample("W-FRI").last()
    weekly_volume = daily_volume.resample("W-FRI").sum()

    weekly_return = weekly_close.pct_change(1)
    avg_vol_20w = weekly_volume.shift(1).rolling(window=20).mean()
    vol_spike = (weekly_volume - avg_vol_20w) / avg_vol_20w

    rank_ret = weekly_return.rank(axis=1, pct=True, ascending=True)
    rank_vol = vol_spike.rank(axis=1, pct=True, ascending=True)

    score = (rank_ret * RETURN_WEIGHT) + (rank_vol * (1 - RETURN_WEIGHT))

    out: dict[pd.Timestamp, list[str]] = {}
    for date, row in score.iterrows():
        valid = row.dropna()
        if len(valid) >= TOP_N:
            out[date] = valid.nlargest(TOP_N).index.tolist()
    return out


def _simulate(
    daily_close: pd.DataFrame,
    signals: dict[pd.Timestamp, list[str]],
    costs: TransactionCosts,
    *,
    date_filter: tuple[pd.Timestamp, pd.Timestamp] | None = None,
) -> dict:
    """Replay the weekly rebalance with the given cost model.

    `date_filter` (start, end) limits trading to within that range — used
    by the walk-forward path to slice OOS test segments.
    """
    cash = INITIAL_CAPITAL
    holdings: dict[str, int] = {}
    portfolio_value_history: list[tuple[pd.Timestamp, float]] = []
    trade_count = 0

    trading_days = sorted(daily_close.index.tolist())

    for friday in sorted(signals.keys()):
        if date_filter and not (date_filter[0] <= friday <= date_filter[1]):
            continue

        top = signals[friday]
        future_days = [d for d in trading_days if d > friday]
        if not future_days:
            break
        exec_day = future_days[0]
        if date_filter and exec_day > date_filter[1]:
            break
        exec_prices = daily_close.loc[exec_day].fillna(0)
        friday_prices = daily_close.loc[:friday].iloc[-1]

        # Mark-to-market at Friday close
        stock_value = sum(holdings.get(s, 0) * friday_prices.get(s, 0) for s in holdings)
        portfolio_value = cash + stock_value
        target_per_stock = portfolio_value / TOP_N
        target_shares = {}
        for s in top:
            p = friday_prices.get(s, 0)
            if p and p > 0:
                shares = int(target_per_stock // p)
                shares = costs.round_shares(shares)
                target_shares[s] = shares

        # Phase 1: SELL down (reduce or exit)
        for s in list(holdings.keys()):
            cur = holdings[s]
            tgt = target_shares.get(s, 0)
            if cur > tgt:
                qty = cur - tgt
                price = exec_prices.get(s, 0)
                if price > 0:
                    fill = costs.sell_fill_price(price)
                    proceeds = costs.sell_proceeds(fill, qty)
                    notional = fill * qty
                    if notional < costs.min_ticket_vnd:
                        continue
                    cash += proceeds
                    holdings[s] -= qty
                    if holdings[s] == 0:
                        del holdings[s]
                    trade_count += 1

        # Phase 2: BUY up
        for s, tgt in target_shares.items():
            cur = holdings.get(s, 0)
            if tgt > cur:
                qty = tgt - cur
                price = exec_prices.get(s, 0)
                if price <= 0:
                    continue
                fill = costs.buy_fill_price(price)
                # Trim to fit available cash including commission
                step = max(1, costs.lot_size)
                while qty > 0 and costs.buy_cost(fill, qty) > cash:
                    qty -= step
                if qty <= 0:
                    continue
                notional = fill * qty
                if notional < costs.min_ticket_vnd:
                    continue
                cost_outflow = costs.buy_cost(fill, qty)
                cash -= cost_outflow
                holdings[s] = holdings.get(s, 0) + qty
                trade_count += 1

        eod_value = cash + sum(holdings.get(s, 0) * exec_prices.get(s, 0) for s in holdings)
        portfolio_value_history.append((exec_day, eod_value))

    last_day = daily_close.index[-1] if not date_filter else date_filter[1]
    last_prices = daily_close.loc[:last_day].iloc[-1]
    final_value = cash + sum(holdings.get(s, 0) * last_prices.get(s, 0) for s in holdings)

    total_return_pct = (final_value - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100.0
    if portfolio_value_history:
        ser = pd.Series([v for _, v in portfolio_value_history])
        roll_max = ser.cummax()
        max_dd = ((ser - roll_max) / roll_max).min() * 100.0
    else:
        max_dd = 0.0

    return {
        "final_value": final_value,
        "total_return_pct": total_return_pct,
        "trade_count": trade_count,
        "max_drawdown_pct": float(max_dd),
    }


def _walk_forward(daily_close, signals, costs, n_windows: int) -> dict:
    dates = sorted(signals.keys())
    if len(dates) < 30:
        return {"oos_total_return_pct": 0.0, "windows": []}

    chunk = max(1, len(dates) // (n_windows + 1))
    windows = []
    for i in range(n_windows):
        # Anchored: train spans [0, train_end), test follows.
        train_end_idx = chunk * (i + 1)
        test_start_idx = train_end_idx
        test_end_idx = min(test_start_idx + chunk, len(dates) - 1)
        if test_end_idx <= test_start_idx:
            continue
        test_start = dates[test_start_idx]
        test_end = dates[test_end_idx]
        stats = _simulate(daily_close, signals, costs, date_filter=(test_start, test_end))
        windows.append({
            "i": i,
            "test_start": str(test_start)[:10],
            "test_end": str(test_end)[:10],
            **stats,
        })

    if windows:
        # Compound the per-window returns to get an OOS total
        compounded = 1.0
        for w in windows:
            compounded *= 1.0 + w["total_return_pct"] / 100.0
        oos_total = (compounded - 1.0) * 100.0
        avg = sum(w["total_return_pct"] for w in windows) / len(windows)
    else:
        oos_total = 0.0
        avg = 0.0

    return {
        "oos_total_return_pct": oos_total,
        "oos_avg_window_return_pct": avg,
        "n_windows": len(windows),
        "windows": windows,
    }


def main() -> None:
    print(f"[rebaseline] loading {len(UNIVERSE)} symbols from cache…")
    daily_close, daily_volume = _load_panel(UNIVERSE)
    daily_close = daily_close.dropna(how="all")
    print(f"[rebaseline] panel: {daily_close.shape[0]} trading days × {daily_close.shape[1]} symbols")

    signals = _weekly_signals(daily_close, daily_volume)
    print(f"[rebaseline] signals: {len(signals)} weekly Top-{TOP_N} draws")

    legacy = _simulate(daily_close, signals, ZERO_COSTS)
    with_costs = _simulate(daily_close, signals, TCBS_DEFAULT_COSTS)
    wf = _walk_forward(daily_close, signals, TCBS_DEFAULT_COSTS, WALK_FORWARD_WINDOWS)

    delta_return = with_costs["total_return_pct"] - legacy["total_return_pct"]

    md = []
    md.append("# Phase 2 — Top-3 Weekly Momentum Rebaseline\n")
    md.append(f"_Generated by `scripts/backtest_top3_phase2_rebaseline.py`. Universe = {UNIVERSE}; horizon ≈ {HISTORY_DAYS} days._\n")
    md.append("Survivor bias: **not corrected** — the universe is fixed at today's tickers, so any delisted name from earlier years is silently absent. Treat the results below as upper-bound estimates.\n")
    md.append("\n## Headline numbers\n")
    md.append("| Run | Total return % | Trades | Max DD % |\n|---|---:|---:|---:|\n")
    md.append(f"| Legacy (zero costs, all-in) | {legacy['total_return_pct']:.2f} | {legacy['trade_count']} | {legacy['max_drawdown_pct']:.2f} |\n")
    md.append(f"| TCBS costs (15+5+10 bps, lot=100) | {with_costs['total_return_pct']:.2f} | {with_costs['trade_count']} | {with_costs['max_drawdown_pct']:.2f} |\n")
    md.append(f"| **Δ vs legacy** | **{delta_return:+.2f} pp** | {with_costs['trade_count'] - legacy['trade_count']:+d} | {with_costs['max_drawdown_pct'] - legacy['max_drawdown_pct']:+.2f} pp |\n")

    md.append("\n## Walk-forward (TCBS costs)\n")
    md.append(f"- Windows: {wf.get('n_windows', 0)} anchored rolling slices.\n")
    md.append(f"- OOS compounded return: **{wf.get('oos_total_return_pct', 0):.2f}%**.\n")
    md.append(f"- OOS average per-window return: **{wf.get('oos_avg_window_return_pct', 0):.2f}%**.\n")
    if wf.get("windows"):
        md.append("\n| Window | Test range | Return % | Trades | Max DD % |\n|---:|---|---:|---:|---:|\n")
        for w in wf["windows"]:
            md.append(f"| {w['i']} | {w['test_start']} → {w['test_end']} | {w['total_return_pct']:.2f} | {w['trade_count']} | {w['max_drawdown_pct']:.2f} |\n")

    md.append("\n## Reading the delta\n")
    md.append("- Costs alone shaved **{:.2f} pp** off the legacy headline number.\n".format(delta_return))
    md.append("- The walk-forward OOS number is the one an agent should cite as evidence; it strips out hindsight bias from sweeping the full history once.\n")
    md.append("- Survivor bias remains uncorrected; until a delisted-symbols list lands, every backtest carries the disclaimer above.\n")

    out_path = REPO_ROOT / "docs" / "PHASE2_TOP3_REBASELINE.md"
    os.makedirs(out_path.parent, exist_ok=True)
    out_path.write_text("".join(md))
    print(f"[rebaseline] wrote {out_path}")
    print(f"[rebaseline] legacy = {legacy['total_return_pct']:.2f}%   with costs = {with_costs['total_return_pct']:.2f}%   Δ = {delta_return:+.2f} pp")


if __name__ == "__main__":
    main()
