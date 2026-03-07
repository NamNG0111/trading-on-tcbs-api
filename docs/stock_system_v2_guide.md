
# TCBS Automated Trading System - Final Walkthrough

## 1. System Overview
We have built a complete **Automated Trading System** for the TCBS platform. It covers the entire lifecycle of algorithmic trading:
1.  **Market Data**: Fetches historical data (vnstock) and real-time prices (TCBS).
2.  **Analysis**: Generating signals using MA, RSI, and Volume strategies.
3.  **Execution**: Placing orders via TCBS API (with Safe Mode).
4.  **Financials**: Tracking Cash, Positions, and Buying Power.
5.  **Analytics**: Calculating Realized P&L and Win Rates.

## 2. Key Components

### A. The "Brain": `auto_trader.py`
This is the main entry point. It runs the entire loop:
```bash
python3 -m trading_on_tcbs_api.stock_system_v2.core.auto_trader
```
*   **Startup**: Attempts to sync with your **Real TCBS Account**.
    *   *If Permission Denied*: Falls back to **Mock Mode** (100M VND Virtual Cash).
*   **Scan**: Checks `config.SYMBOLS` (e.g., HPG, VIC, VNM) for signals.
*   **Execute**: Places orders (Safe Mode by default requires confirmation).
*   **Log**: Saves every trade to `data/ledger.csv`.

### B. The "Eyes": `scan_market.py`
Use this for a quick manual check of the market without trading.
```bash
python3 -m trading_on_tcbs_api.stock_system_v2.scripts.scan_market
```

### C. The "Scoreboard": `analyze_performance.py`
View your trading performance (P&L, Win Rate) based on your ledger.
```bash
python3 -m trading_on_tcbs_api.stock_system_v2.scripts.analyze_performance
```
*   Uses **FIFO** matching logic to calculate realized gains/losses.
*   Reports Win Rate, Profit Factor, and Drawdown.

### D. The "Probe": `fetch_real_assets.py`
A diagnostic tool to check your connection to real TCBS holdings.
```bash
python3 -m trading_on_tcbs_api.stock_system_v2.scripts.fetch_real_assets
```
*   Configured to assume your specific Account IDs (`0001262203` Normal, `0001262204` Margin).
*   *Note*: Currently returns Empty Data due to Token Scope limitations.

---

## 3. Configuration & Security

*   **Credentials**: Stored in `config/credentials.yaml`. We updated this with your correct Sub-Account IDs found via the Profile endpoint.
*   **Token**: `token.json` (Auto-renewing).
*   **Safe Mode**: `config.py` sets strict limits (max order value, prohibited stocks).

## 4. How to Use

1.  **Start the Bot**: Run `auto_trader.py`.
2.  **Monitor**: Watch the logs. It will print "[Account] Sync Warning" if using Mock Mode.
3.  **Trade**: If a signal is found, it will ask for confirmation (in Safe Mode) or trade automatically (if disabled).
4.  **Review**: Run `analyze_performance.py` after a few days of trading to see your P&L.

## 5. Future Step: Real Money
To switch from Mock to Real Money fully:
1.  Obtain a **TCBS Token with `account.view` scope** (contact TCBS or check Wealth API docs).
2.  Once the token allows reading assets, `auto_trader.py` will automatically switch to **Real Mode** at startup.
3.  No code changes needed!

**Enjoy your trading robot!**
