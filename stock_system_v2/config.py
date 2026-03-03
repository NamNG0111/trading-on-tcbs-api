# Stock System V2 Configuration

# List of stocks to scan and trade
SYMBOLS = [
    "TCB", "HPG", "SSI", "VHM", "VIC", "VRE", "VNM", "FPT"
]

# Risk Management Parameters
RISK_PARAMS = {
    "max_capital_per_trade_pct": 0.1,  # Use max 10% of equity per trade
    "stop_loss_pct": 0.05,             # 5% stop loss
    "take_profit_pct": 0.10,           # 10% take profit
    "max_open_positions": 5,           # Max 5 symbols at a time
}

# Trading Timeframes (if applicable for candles)
TIMEFRAME = "1D"  # Daily candles

import os

# System Settings
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # Go up one level to root
DATA_DIR = os.path.join(BASE_DIR, "data", "stocks") # Consolidated data directory
LOG_DIR = os.path.join(BASE_DIR, "trading_on_tcbs_api", "stock_system_v2", "logs")
TOKEN_FILE = os.path.join(BASE_DIR, "config", "token.json")  # Use ROOT token file
CREDENTIALS_FILE = os.path.join(BASE_DIR, "config", "credentials.yaml") # Use ROOT credentials logic

# API Endpoints (TCBS)
BASE_URL = "https://openapi.tcbs.com.vn"  # Standard base URL from credentials
