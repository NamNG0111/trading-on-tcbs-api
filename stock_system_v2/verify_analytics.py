
import os
import sys
import pandas as pd
from datetime import datetime, timedelta

# Ensure path is correct
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from stock_system_v2.performance_analyzer import PerformanceAnalyzer
from stock_system_v2 import config

def verify_analytics():
    print("--- VERIFYING ANALYTICS LOGIC ---")
    
    # 1. Create Mock Ledger
    mock_file = "data/ledger_test.csv"
    data_root = os.path.dirname(config.DATA_DIR)
    full_path = os.path.join(data_root, "ledger_test.csv")
    
    # Scenario:
    # 1. Buy 100 HPG @ 20,000 -> Hold
    # 2. Sell 100 HPG @ 22,000 -> Profit 200,000 (Closed)
    # 3. Buy 100 VIC @ 50,000 -> Hold
    # 4. Sell 50 VIC @ 45,000 -> Loss 250,000 (Partial Close)
    # 5. Buy 100 VNM @ 70,000 -> Hold (Open)
    
    t0 = datetime.now()
    data = [
        # Win
        {'time': t0, 'order_id': '1', 'symbol': 'HPG', 'side': 'BUY', 'price': 20000, 'volume': 100, 'status': 'success'},
        {'time': t0 + timedelta(minutes=1), 'order_id': '2', 'symbol': 'HPG', 'side': 'SELL', 'price': 22000, 'volume': 100, 'status': 'success'},
        
        # Loss (Partial)
        {'time': t0 + timedelta(minutes=2), 'order_id': '3', 'symbol': 'VIC', 'side': 'BUY', 'price': 50000, 'volume': 100, 'status': 'success'},
        {'time': t0 + timedelta(minutes=3), 'order_id': '4', 'symbol': 'VIC', 'side': 'SELL', 'price': 45000, 'volume': 50, 'status': 'success'},
        
        # Open Position (Should be ignored by realized P&L)
        {'time': t0 + timedelta(minutes=4), 'order_id': '5', 'symbol': 'VNM', 'side': 'BUY', 'price': 70000, 'volume': 100, 'status': 'success'},
    ]
    
    df = pd.DataFrame(data)
    df.to_csv(full_path, index=False)
    print(f"Created mock ledger at {full_path}")
    
    # 2. Run Analyzer
    analyzer = PerformanceAnalyzer(full_path)
    metrics = analyzer.calculate_performance()
    
    # 3. Validate
    print("\n[Metrics Calculated]")
    for k, v in metrics.items():
        print(f"{k}: {v}")
        
    # Expectations
    # Trade 1: +200,000
    # Trade 2: -250,000 (50 * -5000)
    # Net: -50,000
    
    expected_pnl = -50000
    if metrics['total_pnl'] == expected_pnl:
        print("\n[SUCCESS] P&L matches expected value (-50,000).")
    else:
        print(f"\n[FAILURE] P&L mismatch. Expected {expected_pnl}, got {metrics['total_pnl']}")
        
    print("\n[Report View]")
    print(analyzer.generate_report())
    
    # Cleanup
    if os.path.exists(full_path):
        os.remove(full_path)
        print("Cleaned up mock file.")

if __name__ == "__main__":
    verify_analytics()
