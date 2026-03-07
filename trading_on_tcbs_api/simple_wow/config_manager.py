import yaml
import os
from typing import Dict, Any, Optional
from pathlib import Path
from dataclasses import dataclass

@dataclass
class CredentialsConfig:
    api_key: str
    custody_code: str
    account_id: str
    sub_account_id: str
    base_url: str

class ConfigManager:
    def __init__(self, config_dir: str = "."):
        self.config_dir = Path(config_dir)
        self._stock_config: Optional[Dict[str, Any]] = None
        self._credentials: Optional[CredentialsConfig] = None
    def load_stock_config(self, config_file: str = "stock_config.yaml") -> Dict[str, Any]:
        if self._stock_config is None:
            config_path = self.config_dir / config_file
            if not config_path.exists():
                raise FileNotFoundError(f"Configuration file not found: {config_path}")
            with open(config_path, 'r', encoding='utf-8') as f:
                self._stock_config = yaml.safe_load(f)
        return self._stock_config
    def load_credentials(self, credentials_file: str = "credentials.yaml") -> CredentialsConfig:
        if self._credentials is None:
            config_path = self.config_dir / credentials_file
            if not config_path.exists():
                raise FileNotFoundError(f"Credentials file not found: {config_path}")
            with open(config_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            required_fields = ["api_key", "custody_code", "account_id", "sub_account_id", "base_url"]
            for field in required_fields:
                if field not in data or not data[field] or "YOUR_" in str(data[field]):
                    raise ValueError(f"Missing or placeholder value for required field: {field}")
            self._credentials = CredentialsConfig(
                api_key=data["api_key"],
                custody_code=data["custody_code"],
                account_id=data["account_id"],
                sub_account_id=data["sub_account_id"],
                base_url=data["base_url"]
            )
        return self._credentials
