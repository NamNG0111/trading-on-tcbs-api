"""
Interactive script to help users set up their credentials properly
"""
import os
import yaml
from pathlib import Path


def setup_credentials():
    """Interactive setup for TCBS API credentials"""
    print("🔐 TCBS API Credentials Setup")
    print("=" * 40)
    
    config_dir = Path("config")
    credentials_path = config_dir / "credentials.yaml"
    example_path = config_dir / "credentials.yaml.example"
    
    # Check if credentials file already exists
    if credentials_path.exists():
        print(f"✓ Credentials file already exists: {credentials_path}")
        
        # Ask if user wants to update
        update = input("Do you want to update the existing credentials? (y/N): ").lower().strip()
        if update != 'y':
            print("Keeping existing credentials.")
            return
    
    # Load example template
    if not example_path.exists():
        print(f"❌ Example file not found: {example_path}")
        return
    
    with open(example_path, 'r') as f:
        config = yaml.safe_load(f)
    
    print("\nPlease provide your TCBS API credentials:")
    print("(You can find these in your TCBS OpenAPI account)")
    print()
    
    # Get credentials from user
    api_key = input("API Key: ").strip()
    if not api_key:
        print("❌ API Key is required")
        return
    
    custody_code = input("Custody Code: ").strip()
    if not custody_code:
        print("❌ Custody Code is required")
        return
    
    account_id = input("Account ID: ").strip()
    if not account_id:
        print("❌ Account ID is required")
        return
    
    sub_account_id = input("Sub Account ID: ").strip()
    if not sub_account_id:
        print("❌ Sub Account ID is required")
        return
    
    # Optional settings
    base_url = input("Base URL [https://openapi.tcbs.com.vn]: ").strip()
    if not base_url:
        base_url = "https://openapi.tcbs.com.vn"
    
    environment = input("Environment (production/sandbox) [production]: ").strip()
    if not environment:
        environment = "production"
    
    # Update config
    config['tcbs_api']['api_key'] = api_key
    config['tcbs_api']['custody_code'] = custody_code
    config['tcbs_api']['account_id'] = account_id
    config['tcbs_api']['sub_account_id'] = sub_account_id
    config['tcbs_api']['base_url'] = base_url
    config['environment'] = environment
    
    # Save credentials file
    with open(credentials_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, indent=2)
    
    # Set secure permissions
    os.chmod(credentials_path, 0o600)
    
    print(f"\n✅ Credentials saved to: {credentials_path}")
    print("🔒 File permissions set to 600 (owner read/write only)")
    print("\n⚠️  IMPORTANT: Never commit this file to version control!")
    print("   The file is already in .gitignore for your protection.")


def test_credentials():
    """Test if credentials are properly configured"""
    print("\n🧪 Testing Credentials Configuration")
    print("=" * 40)
    
    try:
        from utils.config_manager import ConfigManager
        
        config_manager = ConfigManager()
        
        # Test loading credentials
        credentials = config_manager.load_credentials()
        print("✅ Credentials loaded successfully")
        
        # Test loading stock config
        stock_config = config_manager.load_stock_config()
        print("✅ Stock configuration loaded successfully")
        
        # Validate configuration
        if config_manager.validate_config():
            print("✅ All configuration validation passed")
            
            # Show summary (without sensitive data)
            print(f"\n📋 Configuration Summary:")
            print(f"   Base URL: {credentials.base_url}")
            print(f"   Account ID: {credentials.account_id[:4]}***")
            print(f"   Trading Symbols: {stock_config['trading']['symbols']}")
            print(f"   Max Portfolio Value: {stock_config['trading']['position_limits']['max_portfolio_value']:,}")
            
            return True
        else:
            print("❌ Configuration validation failed")
            return False
            
    except Exception as e:
        print(f"❌ Error testing credentials: {e}")
        return False


def main():
    """Main setup function"""
    print("TCBS Trading System - Credentials Setup")
    print("=" * 50)
    
    # Setup credentials
    setup_credentials()
    
    # Test credentials
    if test_credentials():
        print("\n🎉 Setup completed successfully!")
        print("\nNext steps:")
        print("1. Run: python examples/test_indicators.py")
        print("2. Run: python examples/run_stock_strategy.py --validate")
        print("3. Run: python examples/run_stock_strategy.py --dry-run")
    else:
        print("\n❌ Setup incomplete. Please check your credentials and try again.")


if __name__ == "__main__":
    main()
