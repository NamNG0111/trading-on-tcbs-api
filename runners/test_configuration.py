"""
Test script to validate the new YAML configuration system
"""
import asyncio
import os

# Using proper package structure - no sys.path needed


def test_config_loading():
    """Test loading all configuration files"""
    print("🔧 Testing Configuration Loading")
    print("=" * 40)
    
    try:
        from utils.config_manager import ConfigManager
        
        config_manager = ConfigManager()
        
        # Test stock config loading
        print("📋 Loading stock configuration...")
        stock_config = config_manager.load_stock_config()
        print(f"   ✅ Loaded {len(stock_config)} configuration sections")
        
        # Test individual config sections
        sections = [
            ('trading', config_manager.get_trading_config),
            ('indicators', config_manager.get_indicators_config),
            ('signal_rules', config_manager.get_signal_rules_config),
            ('logging', config_manager.get_logging_config),
            ('data_storage', config_manager.get_data_storage_config),
            ('performance', config_manager.get_performance_config)
        ]
        
        for section_name, getter_func in sections:
            try:
                section_config = getter_func()
                print(f"   ✅ {section_name}: {len(section_config)} settings")
            except Exception as e:
                print(f"   ❌ {section_name}: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ Configuration loading failed: {e}")
        return False


def test_credentials_loading():
    """Test loading credentials (with mock data if needed)"""
    print("\n🔐 Testing Credentials Loading")
    print("=" * 40)
    
    try:
        from utils.config_manager import ConfigManager
        
        config_manager = ConfigManager()
        
        # Try to load credentials
        try:
            credentials = config_manager.load_credentials()
            print("✅ Credentials loaded successfully")
            print(f"   Base URL: {credentials.base_url}")
            print(f"   Account ID: {credentials.account_id[:4]}***")
            return True
            
        except FileNotFoundError as e:
            print("⚠️  Credentials file not found")
            print("   This is expected if you haven't set up credentials yet")
            print("   Run: python examples/setup_credentials.py")
            return False
            
        except ValueError as e:
            print(f"⚠️  Credentials validation failed: {e}")
            print("   Please update your credentials file with actual values")
            return False
            
    except Exception as e:
        print(f"❌ Credentials loading error: {e}")
        return False


def test_api_client_initialization():
    """Test API client initialization with new config system"""
    print("\n🌐 Testing API Client Initialization")
    print("=" * 40)
    
    try:
        # Test with mock credentials if real ones aren't available
        from pathlib import Path
        config_dir = Path("config")
        credentials_path = config_dir / "credentials.yaml"
        
        if not credentials_path.exists():
            print("⚠️  No credentials file found, creating mock for testing...")
            create_mock_credentials()
        
        # Try to initialize API client
        from core.api_client import TCBSClient
        
        try:
            client = TCBSClient()
            print("✅ API Client created successfully")
            print(f"   Base URL: {client.base_url}")
            print(f"   API Key: {client.apiKey[:8]}***")
            return True
            
        except Exception as e:
            print(f"❌ API Client initialization failed: {e}")
            return False
            
    except Exception as e:
        print(f"❌ API Client test error: {e}")
        return False


def create_mock_credentials():
    """Create mock credentials for testing"""
    import yaml
    from pathlib import Path
    
    config_dir = Path("config")
    config_dir.mkdir(exist_ok=True)
    
    mock_credentials = {
        'tcbs_api': {
            'api_key': 'mock-api-key-for-testing',
            'custody_code': 'MOCK123',
            'account_id': 'MOCK123',
            'sub_account_id': 'MOCK123A',
            'base_url': 'https://openapi.tcbs.com.vn'
        },
        'environment': 'testing',
        'security': {
            'token_file': 'config/token.json',
            'token_refresh_interval': 3600,
            'max_retry_attempts': 3,
            'request_timeout': 30
        }
    }
    
    credentials_path = config_dir / "credentials.yaml"
    with open(credentials_path, 'w') as f:
        yaml.dump(mock_credentials, f, default_flow_style=False, indent=2)
    
    # Set secure permissions
    import os
    os.chmod(credentials_path, 0o600)
    
    print(f"   Created mock credentials: {credentials_path}")


def test_stock_trading_config():
    """Test stock trading specific configuration"""
    print("\n📈 Testing Stock Trading Configuration")
    print("=" * 40)
    
    try:
        from utils.config_manager import ConfigManager
        
        config_manager = ConfigManager()
        trading_config = config_manager.get_trading_config()
        
        # Check required trading settings
        required_keys = ['symbols', 'position_limits', 'risk_management', 'market_hours']
        for key in required_keys:
            if key in trading_config:
                print(f"   ✅ {key}: configured")
            else:
                print(f"   ❌ {key}: missing")
        
        # Show some key settings
        if 'symbols' in trading_config:
            symbols = trading_config['symbols']
            print(f"   📊 Trading {len(symbols)} symbols: {', '.join(symbols[:3])}...")
        
        if 'position_limits' in trading_config:
            limits = trading_config['position_limits']
            print(f"   💰 Max portfolio: {limits.get('max_portfolio_value', 'N/A'):,}")
            print(f"   📦 Max per symbol: {limits.get('max_position_per_symbol', 'N/A'):,}")
        
        return True
        
    except Exception as e:
        print(f"❌ Stock trading config test failed: {e}")
        return False


def test_indicators_config():
    """Test indicators configuration"""
    print("\n📊 Testing Indicators Configuration")
    print("=" * 40)
    
    try:
        from utils.config_manager import ConfigManager
        
        config_manager = ConfigManager()
        indicators_config = config_manager.get_indicators_config()
        
        # Check available indicators
        available_indicators = list(indicators_config.keys())
        print(f"   📈 Configured indicators: {', '.join(available_indicators)}")
        
        # Test specific indicator configs
        if 'rsi' in indicators_config:
            rsi_config = indicators_config['rsi']
            print(f"   🔄 RSI: period={rsi_config.get('period')}, oversold={rsi_config.get('oversold')}")
        
        if 'macd' in indicators_config:
            macd_config = indicators_config['macd']
            print(f"   📊 MACD: fast={macd_config.get('fast_period')}, slow={macd_config.get('slow_period')}")
        
        return True
        
    except Exception as e:
        print(f"❌ Indicators config test failed: {e}")
        return False


async def test_integration():
    """Test integration between components"""
    print("\n🔗 Testing Component Integration")
    print("=" * 40)
    
    try:
        # Test if we can create a stock trading strategy with new config
        from core.stock_trading_strategy import TradingConfig
        from utils.config_manager import ConfigManager
        
        config_manager = ConfigManager()
        trading_config = config_manager.get_trading_config()
        
        # Create TradingConfig from YAML
        config = TradingConfig(
            symbols=trading_config['symbols'],
            max_position_per_symbol=trading_config['position_limits']['max_position_per_symbol'],
            max_portfolio_value=trading_config['position_limits']['max_portfolio_value'],
            risk_per_trade=trading_config['risk_management']['risk_per_trade'],
            stop_loss_pct=trading_config['risk_management']['stop_loss_pct'],
            take_profit_pct=trading_config['risk_management']['take_profit_pct'],
            min_signal_strength=trading_config['risk_management']['min_signal_strength']
        )
        
        print("✅ TradingConfig created from YAML successfully")
        print(f"   Symbols: {len(config.symbols)}")
        print(f"   Risk per trade: {config.risk_per_trade:.1%}")
        
        return True
        
    except Exception as e:
        print(f"❌ Integration test failed: {e}")
        return False


async def main():
    """Run all configuration tests"""
    print("TCBS Trading System - Configuration Tests")
    print("=" * 50)
    
    tests = [
        ("Configuration Loading", test_config_loading),
        ("Credentials Loading", test_credentials_loading),
        ("API Client Initialization", test_api_client_initialization),
        ("Stock Trading Config", test_stock_trading_config),
        ("Indicators Config", test_indicators_config),
        ("Component Integration", test_integration)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        try:
            if asyncio.iscoroutinefunction(test_func):
                result = await test_func()
            else:
                result = test_func()
            
            if result:
                passed += 1
        except Exception as e:
            print(f"❌ {test_name} test crashed: {e}")
    
    print(f"\n📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Configuration system is working correctly.")
        print("\nNext steps:")
        print("1. Set up real credentials: python examples/setup_credentials.py")
        print("2. Test indicators: python examples/test_indicators.py")
        print("3. Run strategy validation: python examples/run_stock_strategy.py --validate")
    else:
        print("⚠️  Some tests failed. Please check the configuration files.")
    
    # Cleanup mock credentials if created
    from pathlib import Path
    mock_creds = Path("config/credentials.yaml")
    if mock_creds.exists():
        try:
            import yaml
            with open(mock_creds, 'r') as f:
                creds = yaml.safe_load(f)
            if creds.get('tcbs_api', {}).get('api_key') == 'mock-api-key-for-testing':
                mock_creds.unlink()
                print("\n🧹 Cleaned up mock credentials file")
        except:
            pass


if __name__ == "__main__":
    asyncio.run(main())
