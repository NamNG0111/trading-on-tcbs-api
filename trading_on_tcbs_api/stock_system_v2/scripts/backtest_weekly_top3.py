import os
import sys
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

# Add project root to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from trading_on_tcbs_api.stock_system_v2.data_ingest.data_provider import DataProvider
from trading_on_tcbs_api.stock_system_v2.scripts.scan_market import stock_list
from trading_on_tcbs_api.stock_system_v2 import config

def run_backtest(return_weight=None):
    print("--- WEEKLY TOP 3 CROSS-SECTIONAL BACKTEST ---")
    provider = DataProvider()
    
    # 1. Fetch Data
    symbols = stock_list
    TEST_DAYS = 5 * 365 # 5 years
    
    dfs = []
    print(f"Fetching data for {len(symbols)} symbols over 5 years (this may take a minute)...\r")
    for i, sym in enumerate(symbols):
        print(f"[{i+1}/{len(symbols)}] Fetching {sym}...", end='\r', flush=True)
        # Suppress prints from provider if possible, or just let it print
        # We will capture it.
        try:
            df_sym = provider.get_historical_data(sym, days=TEST_DAYS, include_live=False)
            if not df_sym.empty:
                df_sym = df_sym[['time', 'close', 'volume']].copy()
                df_sym['symbol'] = sym
                df_sym['time'] = pd.to_datetime(df_sym['time'])
                # Only keep dates, strip time
                df_sym['time'] = df_sym['time'].dt.normalize()
                dfs.append(df_sym)
        except Exception as e:
            continue
            
    print("\nData fetched. Processing...\n")
    if not dfs:
        print("No data fetched.")
        return
        
    df_all = pd.concat(dfs, ignore_index=True)
    df_all = df_all.drop_duplicates(subset=['time', 'symbol'], keep='last')
    
    # Pivot to get wide format (Dates x Symbols)
    daily_close = df_all.pivot(index='time', columns='symbol', values='close').ffill()
    daily_volume = df_all.pivot(index='time', columns='symbol', values='volume').fillna(0)
    
    # 2. Resample to Weekly (Ending Friday)
    weekly_close = daily_close.resample('W-FRI').last()
    weekly_volume = daily_volume.resample('W-FRI').sum()
    
    # 3. Calculate Metrics
    # Price Increase: This week's close vs Last week's close
    weekly_return = weekly_close.pct_change(1)
    
    # Volume Spike: This week's volume vs 20-week average (shifted by 1 to exclude this week)
    avg_vol_20w = weekly_volume.shift(1).rolling(window=20).mean()
    vol_spike = (weekly_volume - avg_vol_20w) / avg_vol_20w
    
    # 4. Cross-Sectional Ranking
    # Rank (pct=True means 0.0 to 1.0, highest is 1.0)
    rank_ret = weekly_return.rank(axis=1, pct=True, ascending=True)
    rank_vol = vol_spike.rank(axis=1, pct=True, ascending=True)
    
    # Score = 50% Price + 50% Volume
    if return_weight is None:
        return_weight = 0.5
    score = (rank_ret * return_weight) + (rank_vol * (1-return_weight))
    
    # Generate signals: Top 3 every Friday
    friday_signals = {} # Date -> List of Top 3 symbols
    
    for date, row in score.iterrows():
        # Exclude NaN values (which means either no price history or no 20w vol history)
        valid_row = row.dropna()
        if len(valid_row) >= 3:
            top3 = valid_row.nlargest(3).index.tolist()
            friday_signals[date] = top3
            
    # 5. Portfolio Simulation
    INITIAL_CAPITAL = 1_000_000_000 # 1 Tỷ VND
    cash = INITIAL_CAPITAL
    holdings = {} # symbol -> quantity
    
    portfolio_history = []
    trade_log = []
    
    # We need a list of actual trading days to find the execution day (Monday or next available day)
    trading_days = daily_close.index.sort_values().tolist()
    
    for _, friday_date in enumerate(sorted(friday_signals.keys())):
        top3 = friday_signals[friday_date]
        
        # Determine Friday Close prices for calculating Target Portfolio Weights
        # Use ffill to ensure we get the last price if a stock didn't trade exactly on friday_date
        friday_prices = daily_close.loc[:friday_date].iloc[-1]
        
        # Portfolio Value at Friday Close
        stock_value_friday = sum(holdings.get(sym, 0) * friday_prices.get(sym, 0) for sym in holdings)
        portfolio_value_friday = cash + stock_value_friday
        
        # Target Allocation: 33.33% per stock in Top 3
        target_value_per_stock = portfolio_value_friday / 3.0
        
        target_shares = {}
        target_weights_log = {}
        for sym in top3:
            price_friday = friday_prices.get(sym)
            if price_friday and price_friday > 0:
                # Target shares: amount to buy, based on friday price, rounded down to 100
                shares = int(target_value_per_stock // price_friday)
                shares = (shares // 100) * 100
                target_shares[sym] = shares
                target_weights_log[sym] = shares * price_friday / portfolio_value_friday

        # Find next available trading day after this Friday
        future_days = [d for d in trading_days if d > friday_date]
        if not future_days:
            # Lệnh chờ cho T2 tuần tới
            print("\n*** LỆNH CHỜ MUA/BÁN VÀO THỨ 2 TUẦN TỚI ***")
            print(f"Ngày ra tín hiệu: {friday_date.strftime('%Y-%m-%d')}")
            print(f"Tổng tài sản: {portfolio_value_friday:,.0f} VND (Tiền mặt: {cash:,.0f})")
            print(f"Top 3 tuần này: {top3}")
            
            for sym in list(holdings.keys()):
                current_qty = holdings[sym]
                target_qty = target_shares.get(sym, 0)
                if current_qty > target_qty:
                    qty_to_sell = current_qty - target_qty
                    print(f" -> [BÁN] {qty_to_sell} cổ phiếu {sym} (Tạm tính theo giá T6: {friday_prices.get(sym, 0):,.0f})")
                    trade_log.append({
                        'Date': 'PENDING',
                        'Signal_Date': friday_date.strftime('%Y-%m-%d'),
                        'Type': 'SELL PENDING',
                        'Symbol': sym,
                        'Shares': qty_to_sell,
                        'Price': friday_prices.get(sym, 0),
                        'Value': qty_to_sell * friday_prices.get(sym, 0)
                    })
            for sym, target_qty in target_shares.items():
                current_qty = holdings.get(sym, 0)
                if target_qty > current_qty:
                    qty_to_buy = target_qty - current_qty
                    print(f" -> [MUA] {qty_to_buy} cổ phiếu {sym} (Tạm tính theo giá T6: {friday_prices.get(sym, 0):,.0f})")
                    trade_log.append({
                        'Date': 'PENDING',
                        'Signal_Date': friday_date.strftime('%Y-%m-%d'),
                        'Type': 'BUY PENDING',
                        'Symbol': sym,
                        'Shares': qty_to_buy,
                        'Price': friday_prices.get(sym, 0),
                        'Value': qty_to_buy * friday_prices.get(sym, 0)
                    })
            break # End of historical data
            
        exec_day = future_days[0]
        
        # Execute Rebalance on `exec_day` (Usually Monday)
        monday_prices = daily_close.loc[exec_day]
        monday_prices = monday_prices.fillna(0) # Safety
        
        # Track today's trades to avoid modifying dict while iterating correctly
        holds_clone = dict(holdings)
        
        # Phase 1: SELL (Full or Partial)
        for sym in holds_clone.keys():
            current_qty = holdings[sym]
            target_qty = target_shares.get(sym, 0)
            
            if current_qty > target_qty:
                qty_to_sell = current_qty - target_qty
                exec_price = monday_prices.get(sym, 0)
                if exec_price > 0:
                    revenue = qty_to_sell * exec_price
                    cash += revenue
                    holdings[sym] -= qty_to_sell
                    if holdings[sym] == 0:
                        del holdings[sym]
                    
                    trade_log.append({
                        'Date': exec_day.strftime('%Y-%m-%d'),
                        'Signal_Date': friday_date.strftime('%Y-%m-%d'),
                        'Type': 'SELL',
                        'Symbol': sym,
                        'Shares': qty_to_sell,
                        'Price': exec_price,
                        'Value': revenue
                    })
                    
        # Phase 2: BUY
        for sym, target_qty in target_shares.items():
            current_qty = holdings.get(sym, 0)
            if target_qty > current_qty:
                qty_to_buy = target_qty - current_qty
                exec_price = monday_prices.get(sym, 0)
                
                if exec_price > 0:
                    cost = qty_to_buy * exec_price
                    
                    if qty_to_buy > 0:
                        cash -= cost
                        holdings[sym] = holdings.get(sym, 0) + qty_to_buy
                        
                        trade_log.append({
                            'Date': exec_day.strftime('%Y-%m-%d'),
                            'Signal_Date': friday_date.strftime('%Y-%m-%d'),
                            'Type': 'BUY',
                            'Symbol': sym,
                            'Shares': qty_to_buy,
                            'Price': exec_price,
                            'Value': cost
                        })
                        
        # End of day Portfolio Value
        eod_stock_value = sum(holdings.get(sym, 0) * monday_prices.get(sym, 0) for sym in holdings)
        eod_portfolio_value = cash + eod_stock_value
        portfolio_history.append({'Date': exec_day, 'Portfolio_Value': eod_portfolio_value, 'Cash': cash})

    # Record final value based on last available price
    last_day = daily_close.index[-1]
    last_prices = daily_close.loc[last_day]
    final_stock_value = sum(holdings.get(sym, 0) * last_prices.get(sym, 0) for sym in holdings)
    final_value = cash + final_stock_value
    portfolio_history.append({'Date': last_day, 'Portfolio_Value': final_value, 'Cash': cash})
    
    # 6. Reporting
    df_port = pd.DataFrame(portfolio_history).drop_duplicates('Date').set_index('Date')
    df_trades = pd.DataFrame(trade_log)
    
    total_return_pct = (final_value - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
    
    # Daily returns of portfolio for CAGR and Sharpe
    df_port['Weekly_Return_Pct'] = (df_port['Portfolio_Value'].pct_change().fillna(0)) * 100
    df_port['Cumulative_Return_Pct'] = ((df_port['Portfolio_Value'] / INITIAL_CAPITAL) - 1) * 100
    years = TEST_DAYS / 365.25
    cagr_pct = ((final_value / INITIAL_CAPITAL) ** (1 / max(1, years)) - 1) * 100
    
    # Max Drawdown
    roll_max = df_port['Portfolio_Value'].cummax()
    drawdown = (df_port['Portfolio_Value'] - roll_max) / roll_max
    max_drawdown_pct = drawdown.min() * 100
    
    print("\n==========================================================")
    print("BACKTEST RESULTS: WEEKLY TOP 3 MOMENTUM & VOLUME")
    print("==========================================================")
    print(f"Initial Capital : {INITIAL_CAPITAL:,.0f} VND")
    print(f"Final Value     : {final_value:,.0f} VND")
    print(f"Total Return    : {total_return_pct:,.2f}%")
    print(f"CAGR (Annual)   : {cagr_pct:,.2f}%")
    print(f"Max Drawdown    : {max_drawdown_pct:,.2f}%")
    print(f"Total Trades    : {len(df_trades)}")
    print("==========================================================")
    
    if not df_trades.empty:
        export_path = config.EXPORT_DIR
        os.makedirs(export_path, exist_ok=True)
        csv_file = os.path.join(export_path, f"top3_weekly_trades_{weight*100:.0f}pct.csv")
        df_trades.to_csv(csv_file, index=False)
        print(f"Trades logged attached to: {os.path.abspath(csv_file)}")
        
    return df_trades, df_port
        
if __name__ == "__main__":
    return_weight_list = [0.5,0.6,0.7,0.8,0.9]
    for weight in return_weight_list:
        print(f'return weight: {weight:,.1%}')
        df_trades_result, df_port_result = run_backtest(return_weight=weight)
    if df_trades_result is not None and not df_trades_result.empty:
        # Assign to globals so PyCharm Data Viewer can access it
        globals()['df_trades'] = df_trades_result
        globals()['df_portfolio'] = df_port_result
        print("- Bảng df_trades và df_portfolio đã được đưa vào biến toàn cục. Mở SciView/Data Viewer để xem trực tiếp.")
