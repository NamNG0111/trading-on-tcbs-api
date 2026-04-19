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
import json

# System Settings
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # Go up one level to root
DATA_DIR = os.path.join(BASE_DIR, "data", "stocks") # Consolidated data directory
LOG_DIR = os.path.join(BASE_DIR, "logs")
TOKEN_FILE = os.path.join(BASE_DIR, "config", "token.json")  # Use ROOT token file
CREDENTIALS_FILE = os.path.join(BASE_DIR, "config", "credentials.yaml") # Use ROOT credentials logic
LOCAL_CONFIG_FILE = os.path.join(BASE_DIR, "config", "local_config.json")

# Load Local Config for Export Paths
EXPORT_DIR = os.path.join(BASE_DIR, "data", "exports") # Fallback export dir
if os.path.exists(LOCAL_CONFIG_FILE):
    try:
        with open(LOCAL_CONFIG_FILE, "r") as f:
            _local_config = json.load(f)
            if "EXPORT_DIR" in _local_config:
                EXPORT_DIR = _local_config["EXPORT_DIR"]
            if "DATA_DIR" in _local_config:
                DATA_DIR = _local_config["DATA_DIR"]
    except Exception as e:
        print(f"Warning: Failed to load local_config.json: {e}")

# Ensure export and data dirs exist
os.makedirs(EXPORT_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# API Endpoints (TCBS)
BASE_URL = "https://openapi.tcbs.com.vn"  # Standard base URL from credentials
