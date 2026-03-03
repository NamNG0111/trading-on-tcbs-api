"""
Default configuration data for the trading system
"""
import json
from pathlib import Path


def create_default_files():
    """Create default configuration files if they don't exist"""
    
    # Default token.json (moved to config/)
    token_file = Path("config/token.json")
    if not token_file.exists():
        default_token = {
            "token": "your_jwt_token_here",
            "expiry": "2024-12-31"
        }
        with open(token_file, 'w') as f:
            json.dump(default_token, f, indent=4)
        print("Created default config/token.json - please update with your actual token")
    
    # Default spread_dca.json (moved to config/)
    spread_file = Path("config/spread_dca.json")
    if not spread_file.exists():
        default_spread = {
            "prev_spread_long": -0.5,
            "prev_spread_short": 0.5
        }
        with open(spread_file, 'w') as f:
            json.dump(default_spread, f, indent=4)
        print("Created default config/spread_dca.json")
    
    # Default tick_data.json (moved to data/)
    tick_file = Path("data/tick_data.json")
    if not tick_file.exists():
        # Create empty tick data array
        default_tick_data = []
        with open(tick_file, 'w') as f:
            json.dump(default_tick_data, f)
        print("Created default data/tick_data.json")


if __name__ == "__main__":
    create_default_files()
