
import sys
import os

# Ensure path is correct
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from trading_on_tcbs_api.stock_system_v2.finance.performance_analyzer import PerformanceAnalyzer
from trading_on_tcbs_api.stock_system_v2 import config

def main():
    print("--- Performance Analytics Tool ---")
    
    # Locate Ledger
    # Tracker puts it in os.path.dirname(config.DATA_DIR) / "ledger.csv"
    data_root = os.path.dirname(config.DATA_DIR)
    ledger_path = os.path.join(data_root, "ledger.csv")
    
    print(f"Target Ledger: {ledger_path}")
    
    analyzer = PerformanceAnalyzer(ledger_path)
    report = analyzer.generate_report()
    
    print(report)
    
    # Optional: Save stats to file?
    # stats = analyzer.calculate_performance()
    # if stats:
    #     print("\n[Detailed Metrics]")
    #     for k, v in stats.items():
    #         print(f"{k}: {v}")

if __name__ == "__main__":
    main()
