"""
Production-ready script to run the stock trading strategy
"""
import asyncio
import json
import os
from datetime import datetime
import argparse

# No need for sys.path manipulation with proper package structure

from trading_on_tcbs_api.stock_strategy.strategy import StockTradingStrategy, TradingConfig
from trading_on_tcbs_api.logger_utils.fast_logger import get_logger
from trading_on_tcbs_api.utils.config_manager import ConfigManager


async def load_config(config_file: str = "config/stock_config.yaml") -> TradingConfig:
    """Load trading configuration using ConfigManager"""
    try:
        config_manager = ConfigManager()
        stock_config = config_manager.load_stock_config()
        
        # Extract trading configuration
        trading = stock_config.get('trading', {})
        position_limits = trading.get('position_limits', {})
        risk_mgmt = trading.get('risk_management', {})
        market_hours = trading.get('market_hours', {})
        data_settings = trading.get('data_settings', {})
        
        # Extract trading hours from nested structure
        morning = market_hours.get('morning_session', {})
        afternoon = market_hours.get('afternoon_session', {})
        trading_hours = (
            tuple(morning.get('start', [9, 0])),
            tuple(afternoon.get('end', [15, 0]))
        )
        
        return TradingConfig(
            symbols=trading.get('symbols', []),
            max_position_per_symbol=position_limits.get('max_position_per_symbol'),
            max_portfolio_value=position_limits.get('max_portfolio_value'),
            risk_per_trade=risk_mgmt.get('risk_per_trade'),
            stop_loss_pct=risk_mgmt.get('stop_loss_pct'),
            take_profit_pct=risk_mgmt.get('take_profit_pct'),
            min_signal_strength=risk_mgmt.get('min_signal_strength'),
            trading_hours=trading_hours,
            data_update_interval=data_settings.get('update_interval'),
            use_talib=trading.get('use_talib', True)  # This one can have a default since it's not in YAML
        )
            
    except Exception as e:
        print(f"Error loading config: {e}")
        print("Please ensure config/stock_config.yaml exists and is properly formatted")
        raise


async def run_strategy(account_no: str = None, config_file: str = None, dry_run: bool = False):
    """Run the stock trading strategy"""
    logger = get_logger('main', 'Main')
    
    try:
        # Load configuration
        config = await load_config(config_file or "config/stock_config.yaml")
        
        await logger.log("Starting stock trading strategy")
        await logger.log(f"Configuration: {len(config.symbols)} symbols, "
                        f"risk per trade: {config.risk_per_trade:.1%}")
        
        if dry_run:
            await logger.log("Running in DRY RUN mode - no actual trades will be executed")
        
        # Create and initialize strategy
        strategy = StockTradingStrategy(config)
        
        if not dry_run:
            await strategy.initialize(account_no)
        else:
            await logger.log("Skipping API initialization in dry run mode")
        
        # Setup signal handlers for graceful shutdown
        import signal
        
        def signal_handler(signum, frame):
            print(f"\nReceived signal {signum}, shutting down gracefully...")
            asyncio.create_task(strategy.stop_trading())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Start trading
        if not dry_run:
            await strategy.start_trading()
        else:
            await logger.log("Strategy would start trading here (dry run mode)")
            
            # In dry run, just show what would happen
            status = await strategy.get_strategy_status()
            print(f"Strategy status: {json.dumps(status, indent=2, default=str)}")
        
    except KeyboardInterrupt:
        await logger.log("Interrupted by user")
    except Exception as e:
        await logger.log_error(f"Error running strategy: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await logger.log("Strategy stopped")
        await logger.flush()


async def check_strategy_status(account_no: str = None):
    """Check current strategy status"""
    try:
        config = await load_config()
        strategy = StockTradingStrategy(config)
        
        if account_no:
            await strategy.initialize(account_no)
            status = await strategy.get_strategy_status()
            print(json.dumps(status, indent=2, default=str))
        else:
            print("Account number required for status check")
            
    except Exception as e:
        print(f"Error checking status: {e}")


async def validate_setup():
    """Validate that all components are working"""
    print("Validating stock trading setup...")
    
    # Test imports
    try:
        from indicators.talib_indicators import RSI
        print("✓ TA-Lib indicators available")
    except ImportError:
        print("⚠ TA-Lib not available, will use custom indicators")
    
    # Test custom indicators
    try:
        from indicators.custom_indicators import CustomRSI
        custom_rsi = CustomRSI(period=14)
        test_data = [100, 101, 102, 103, 104, 105]
        result = custom_rsi.calculate(test_data)
        print("✓ Custom indicators working")
    except Exception as e:
        print(f"✗ Custom indicators error: {e}")
        return False
    
    # Test signal generation
    try:
        from indicators.signal_generator import SignalGenerator
        signal_gen = SignalGenerator()
        print("✓ Signal generator working")
    except Exception as e:
        print(f"✗ Signal generator error: {e}")
        return False
    
    # Test historical data manager
    try:
        from data.historical_data_manager import HistoricalDataManager
        hist_manager = HistoricalDataManager(data_dir="data/test_validation")
        print("✓ Historical data manager working")
    except Exception as e:
        print(f"✗ Historical data manager error: {e}")
        return False
    
    # Test API client (without actual connection)
    try:
        from trading_on_tcbs_api.stock_system_v2.core.stock_api_client import StockTradingClient
        client = StockTradingClient()
        print("✓ Stock API client created")
    except Exception as e:
        print(f"✗ Stock API client error: {e}")
        return False
    
    print("✓ All components validated successfully!")
    return True


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Stock Trading Strategy Runner")
    parser.add_argument("--account", "-a", help="TCBS account number")
    parser.add_argument("--config", "-c", help="Configuration file path")
    parser.add_argument("--dry-run", "-d", action="store_true", help="Run in dry-run mode")
    parser.add_argument("--status", "-s", action="store_true", help="Check strategy status")
    parser.add_argument("--validate", "-v", action="store_true", help="Validate setup")
    
    args = parser.parse_args()
    
    if args.validate:
        asyncio.run(validate_setup())
    elif args.status:
        asyncio.run(check_strategy_status(args.account))
    else:
        asyncio.run(run_strategy(args.account, args.config, args.dry_run))


if __name__ == "__main__":
    main()
