"""
Configuration loader for the trading bot.
Loads settings from YAML config files and environment variables.
"""

import os
import yaml
from pathlib import Path
from typing import Any, Dict
from dotenv import load_dotenv

class ConfigLoader:
    """Loads and manages configuration settings."""
    
    def __init__(self, config_path: str = None):
        """
        Initialize configuration loader.
        
        Args:
            config_path: Path to configuration file. If None, uses default location.
        """
        # Load environment variables
        load_dotenv()
        
        # Determine config file path
        if config_path is None:
            base_dir = Path(__file__).parent.parent
            config_path = base_dir / "config" / "config.yaml"
        
        self.config_path = Path(config_path)
        self.config = self._load_config()
        
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
        
        with open(self.config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Override with environment variables if present
        config = self._apply_env_overrides(config)
        
        return config
    
    def _apply_env_overrides(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Apply environment variable overrides to config."""
        # API keys from environment
        if 'COINBASE_API_KEY' in os.environ:
            if 'api' not in config:
                config['api'] = {}
            config['api']['key'] = os.getenv('COINBASE_API_KEY')
            config['api']['secret'] = os.getenv('COINBASE_API_SECRET')
        
        # Paper trading mode override
        if 'PAPER_TRADING_MODE' in os.environ:
            paper_mode = os.getenv('PAPER_TRADING_MODE', 'true').lower() == 'true'
            config['trading']['paper_trading_mode'] = paper_mode
        
        return config
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get configuration value using dot notation.
        
        Args:
            key_path: Dot-separated path to config value (e.g., 'trading.candle_granularity')
            default: Default value if key not found
            
        Returns:
            Configuration value
        """
        keys = key_path.split('.')
        value = self.config
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        
        return value
    
    def get_api_credentials(self) -> tuple:
        """Get API credentials from environment variables."""
        api_key = os.getenv("COINBASE_API_KEY")
        api_secret = os.getenv("COINBASE_API_SECRET")
        
        if not api_key or not api_secret:
            raise ValueError("API credentials not found in environment variables")
        
        return api_key, api_secret
    
    def reload(self):
        """Reload configuration from file."""
        self.config = self._load_config()
    
    def __getitem__(self, key: str) -> Any:
        """Allow dictionary-style access."""
        return self.config[key]
    
    def __contains__(self, key: str) -> bool:
        """Check if key exists in config."""
        return key in self.config


# Global config instance
_config_instance = None

def get_config(config_path: str = None) -> ConfigLoader:
    """
    Get or create global configuration instance.
    
    Args:
        config_path: Path to configuration file
        
    Returns:
        ConfigLoader instance
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = ConfigLoader(config_path)
    return _config_instance
