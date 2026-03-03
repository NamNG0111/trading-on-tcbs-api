"""
Configuration manager for loading YAML configs and managing credentials securely
"""
import yaml
import os
from typing import Dict, Any, Optional
from pathlib import Path
import logging
from dataclasses import dataclass


@dataclass
class CredentialsConfig:
    """Credentials configuration structure"""
    api_key: str
    custody_code: str
    base_url: str
    account_id: Optional[str] = None
    sub_account_id: Optional[str] = None
    normal_sub_account_id: Optional[str] = None
    normal_sub_account_id: Optional[str] = None
    margin_sub_account_id: Optional[str] = None
    futures_sub_account_id: Optional[str] = None


class ConfigManager:
    """Centralized configuration manager with secure credential handling"""
    
    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)
        self._stock_config: Optional[Dict[str, Any]] = None
        self._credentials: Optional[CredentialsConfig] = None
        
    def load_stock_config(self, config_file: str = "stock_config.yaml") -> Dict[str, Any]:
        """Load stock trading configuration from YAML"""
        if self._stock_config is None:
            config_path = self.config_dir / config_file
            
            if not config_path.exists():
                raise FileNotFoundError(f"Configuration file not found: {config_path}")
            
            with open(config_path, 'r', encoding='utf-8') as f:
                self._stock_config = yaml.safe_load(f)
                
        return self._stock_config
    
    def load_credentials(self, credentials_file: str = "credentials.yaml") -> CredentialsConfig:
        """Load credentials from YAML file with security checks"""
        if self._credentials is None:
            credentials_path = self.config_dir / credentials_file
            
            # Check if credentials file exists
            if not credentials_path.exists():
                # Check for example file and provide helpful error
                example_path = self.config_dir / "credentials.yaml.example"
                if example_path.exists():
                    raise FileNotFoundError(
                        f"Credentials file not found: {credentials_path}\n"
                        f"Please copy {example_path} to {credentials_path} and fill in your credentials"
                    )
                else:
                    raise FileNotFoundError(f"Credentials file not found: {credentials_path}")
            
            # Check file permissions (should not be world-readable)
            file_stat = credentials_path.stat()
            if file_stat.st_mode & 0o044:  # Check if group or others can read
                logging.warning(f"Credentials file {credentials_path} has overly permissive permissions")
            
            with open(credentials_path, 'r', encoding='utf-8') as f:
                cred_data = yaml.safe_load(f)
            
            # Validate required fields
            tcbs_api = cred_data.get('tcbs_api', {})
            # Validate that we have at least SOME account ID
            required_basic = ['api_key', 'custody_code']
            for field in required_basic:
                if not tcbs_api.get(field) or tcbs_api[field] == f"your-{field.replace('_', '-')}-here":
                    raise ValueError(f"Missing or placeholder value for required field: {field}")
            
            # Legacy vs New support
            has_legacy = tcbs_api.get('account_id') and tcbs_api.get('sub_account_id')
            has_new = tcbs_api.get('normal_sub_account_id') or tcbs_api.get('margin_sub_account_id')
            
            if not (has_legacy or has_new):
                 raise ValueError("Must provide either legacy IDs (account_id, sub_account_id) or new IDs (normal_sub_account_id, etc)")
                 
            # Note: We pass None for missing fields, CredentialsConfig dataclass handles type hinting but doesn't force not None at runtime unless checked. 
            # We updated CredentialsConfig to have them as str. We should probably make them Optional in dataclass or default to empty string.
            # Step 1057 showed I didn't verify CredentialsConfig definition fully, just added Optionals.
            # But the 'account_id' field in dataclass was defined as `str` (required).
            # I need to update the dataclass definition too if I pass None.
            
            # Validate base_url is provided in config
            if 'base_url' not in tcbs_api:
                raise ValueError("Missing required field: base_url in tcbs_api configuration")
            
            self._credentials = CredentialsConfig(
                api_key=tcbs_api['api_key'],
                custody_code=tcbs_api['custody_code'],
                account_id=tcbs_api.get('account_id'),
                sub_account_id=tcbs_api.get('sub_account_id'),
                base_url=tcbs_api.get('base_url', 'https://openapi.tcbs.com.vn'),
                normal_sub_account_id=tcbs_api.get('normal_sub_account_id'),
                margin_sub_account_id=tcbs_api.get('margin_sub_account_id'),
                futures_sub_account_id=tcbs_api.get('futures_sub_account_id')
            )
            
        return self._credentials
    
    def get_trading_config(self) -> Dict[str, Any]:
        """Get trading-specific configuration"""
        config = self.load_stock_config()
        return config.get('trading', {})
    
    def get_indicators_config(self) -> Dict[str, Any]:
        """Get indicators configuration"""
        config = self.load_stock_config()
        return config.get('indicators', {})
    
    def get_signal_rules_config(self) -> Dict[str, Any]:
        """Get signal rules configuration"""
        config = self.load_stock_config()
        return config.get('signal_rules', {})
    
    def get_logging_config(self) -> Dict[str, Any]:
        """Get logging configuration"""
        config = self.load_stock_config()
        return config.get('logging', {})
    
    def get_data_storage_config(self) -> Dict[str, Any]:
        """Get data storage configuration"""
        config = self.load_stock_config()
        return config.get('data_storage', {})
    
    def get_performance_config(self) -> Dict[str, Any]:
        """Get performance configuration"""
        config = self.load_stock_config()
        return config.get('performance', {})
    
    def get_development_config(self) -> Dict[str, Any]:
        """Get development configuration"""
        config = self.load_stock_config()
        return config.get('development', {})
    
    def load_futures_config(self) -> Dict[str, Any]:
        """Load futures trading configuration from YAML file"""
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'futures_config.yaml')
        
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Futures config file not found: {config_path}")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def get_futures_contracts(self) -> Dict[str, str]:
        """Get futures contract specifications"""
        config = self.load_futures_config()
        return config.get('contracts', {})
    
    def get_futures_sessions(self) -> Dict[str, Any]:
        """Get futures trading sessions"""
        config = self.load_futures_config()
        return config.get('sessions', {})
    
    def get_futures_risk_management(self) -> Dict[str, Any]:
        """Get futures risk management settings"""
        config = self.load_futures_config()
        return config.get('risk_management', {})
    
    def get_security_config(self) -> Dict[str, Any]:
        """Get security configuration from credentials file"""
        credentials_path = self.config_dir / "credentials.yaml"
        
        if not credentials_path.exists():
            return {}
        
        with open(credentials_path, 'r', encoding='utf-8') as f:
            cred_data = yaml.safe_load(f)
        
        return cred_data.get('security', {})
    
    def update_config(self, section: str, key: str, value: Any, config_file: str = "stock_config.yaml"):
        """Update configuration value and save to file"""
        config = self.load_stock_config(config_file)
        
        if section not in config:
            config[section] = {}
        
        config[section][key] = value
        
        # Save back to file
        config_path = self.config_dir / config_file
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, indent=2)
        
        # Clear cache to reload on next access
        self._stock_config = None
    
    @staticmethod
    def create_secure_credentials_file(credentials_path: str):
        """Create credentials file with secure permissions"""
        # Create the file
        Path(credentials_path).touch()
        
        # Set secure permissions (owner read/write only)
        os.chmod(credentials_path, 0o600)
        
        print(f"Created secure credentials file: {credentials_path}")
        print("Please edit this file and add your TCBS API credentials")
    
    def validate_config(self) -> bool:
        """Validate all configuration files"""
        try:
            # Test loading stock config
            stock_config = self.load_stock_config()
            
            # Test loading credentials
            credentials = self.load_credentials()
            
            # Validate required sections in stock config
            required_sections = ['trading', 'indicators', 'logging']
            for section in required_sections:
                if section not in stock_config:
                    raise ValueError(f"Missing required configuration section: {section}")
            
            # Validate trading config
            trading_config = stock_config['trading']
            required_trading_keys = ['symbols', 'position_limits', 'risk_management']
            for key in required_trading_keys:
                if key not in trading_config:
                    raise ValueError(f"Missing required trading configuration: {key}")
            
            print("✓ Configuration validation successful")
            return True
            
        except Exception as e:
            print(f"✗ Configuration validation failed: {e}")
            return False


# Global config manager instance
config_manager = ConfigManager()


def get_config_manager() -> ConfigManager:
    """Get the global configuration manager instance"""
    return config_manager


def load_trading_config() -> Dict[str, Any]:
    """Convenience function to load trading configuration"""
    return config_manager.get_trading_config()


def load_credentials() -> CredentialsConfig:
    """Convenience function to load credentials"""
    return config_manager.load_credentials()


def load_futures_config() -> Dict[str, Any]:
    """Convenience function to load futures configuration"""
    return config_manager.load_futures_config()


def get_futures_value(key_path: str, default=None):
    """Get a value from futures config using dot notation (e.g., 'contracts.f1m')"""
    config = load_futures_config()
    keys = key_path.split('.')
    
    value = config
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default
    
    return value


def setup_credentials_file():
    """Interactive setup for credentials file"""
    config_dir = Path("config")
    credentials_path = config_dir / "credentials.yaml"
    example_path = config_dir / "credentials.yaml.example"
    
    if credentials_path.exists():
        print(f"Credentials file already exists: {credentials_path}")
        return
    
    if not example_path.exists():
        print(f"Example credentials file not found: {example_path}")
        return
    
    # Copy example to credentials file
    import shutil
    shutil.copy2(example_path, credentials_path)
    
    # Set secure permissions
    os.chmod(credentials_path, 0o600)
    
    print(f"Created credentials file: {credentials_path}")
    print("Please edit this file and replace the placeholder values with your actual TCBS API credentials")
    print("Make sure to never commit this file to version control!")


if __name__ == "__main__":
    # Command-line interface for configuration management
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "setup":
            setup_credentials_file()
        elif command == "validate":
            config_manager.validate_config()
        else:
            print("Usage: python config_manager.py [setup|validate]")
    else:
        print("Configuration Manager")
        print("Commands:")
        print("  setup    - Set up credentials file from example")
        print("  validate - Validate all configuration files")
