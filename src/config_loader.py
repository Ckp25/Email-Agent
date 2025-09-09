import yaml
import os
from typing import Dict, Any
from dotenv import load_dotenv

class Config:
    """Centralized configuration manager for the email bot."""
    
    def __init__(self, config_path: str = None):
        # Auto-detect config path relative to this file
        if config_path is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            parent_dir = os.path.dirname(current_dir)
            config_path = os.path.join(parent_dir, "config.yaml")
        
        self.config_path = config_path
        self._config_data = {}
        self._load_config()
        self._load_env_variables()
    
    def _load_config(self):
        """Load configuration from YAML file."""
        try:
            if not os.path.exists(self.config_path):
                raise FileNotFoundError(f"Config file not found: {self.config_path}")
            
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self._config_data = yaml.safe_load(f) or {}
                
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in config file: {e}")
        except Exception as e:
            raise RuntimeError(f"Error loading config file: {e}")
    
    def _load_env_variables(self):
        """Load environment variables from .env file."""
        load_dotenv()
        
        # Validate required environment variables
        required_env_vars = ["EMAIL_ADDRESS", "EMAIL_PASSWORD", "OPENAI_API_KEY"]
        missing_vars = []
        
        for var in required_env_vars:
            if not os.getenv(var):
                missing_vars.append(var)
        
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get configuration value using dot notation.
        
        Args:
            key_path: Dot-separated path (e.g., 'email.imap_server')
            default: Default value if key not found
            
        Returns:
            Configuration value
        """
        keys = key_path.split('.')
        value = self._config_data
        
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default
    
    def get_env(self, key: str, default: str = None) -> str:
        """Get environment variable value."""
        value = os.getenv(key, default)
        if value is None:
            raise ValueError(f"Environment variable {key} not found")
        return value
    
    # Convenience properties for commonly used values
    @property
    def email_address(self) -> str:
        return self.get_env("EMAIL_ADDRESS")
    
    @property
    def email_password(self) -> str:
        return self.get_env("EMAIL_PASSWORD")
    
    @property
    def openai_api_key(self) -> str:
        return self.get_env("OPENAI_API_KEY")
    
    @property
    def imap_server(self) -> str:
        return self.get("email.imap_server", "imap.gmail.com")
    
    @property
    def imap_port(self) -> int:
        return self.get("email.imap_port", 993)
    
    @property
    def label_name(self) -> str:
        return self.get("email.label_name", "AI_PROCESSED")
    
    @property
    def search_days_back(self) -> int:
        return self.get("email.search_days_back", 1)
    
    @property
    def max_thread_history(self) -> int:
        return self.get("threading.max_history", 5)
    
    @property
    def threads_file(self) -> str:
        return self.get("threading.storage_file", "email_threads.json")
    
    @property
    def openai_model(self) -> str:
        return self.get("openai.model", "gpt-4o")
    
    @property
    def openai_temperature(self) -> float:
        return self.get("openai.temperature", 0.4)
    
    @property
    def openai_max_retries(self) -> int:
        return self.get("openai.max_retries", 3)
    
    @property
    def log_level(self) -> str:
        return self.get("logging.level", "INFO")
    
    @property
    def log_to_file(self) -> bool:
        return self.get("logging.file_enabled", True)
    
    @property
    def log_file_path(self) -> str:
        return self.get("logging.file_path", "logs/email_bot.log")
    
    @property
    def require_subject(self) -> bool:
        return self.get("validation.require_subject", True)
    
    def validate_config(self) -> bool:
        """Validate that all required configuration is present and valid."""
        validation_errors = []
        
        # Check required environment variables
        try:
            self.email_address
            self.email_password  
            self.openai_api_key
        except ValueError as e:
            validation_errors.append(str(e))
        
        # Validate config values
        if self.max_thread_history < 1:
            validation_errors.append("threading.max_history must be >= 1")
        
        if self.search_days_back < 1:
            validation_errors.append("email.search_days_back must be >= 1")
        
        if self.openai_temperature < 0 or self.openai_temperature > 2:
            validation_errors.append("openai.temperature must be between 0 and 2")
        
        if validation_errors:
            error_msg = "Configuration validation failed:\n" + "\n".join(f"  - {err}" for err in validation_errors)
            raise ValueError(error_msg)
        
        return True

# Global config instance
config = Config()

if __name__ == "__main__":
    print("Testing configuration loader...")
    
    try:
        # Test config validation
        config.validate_config()
        print(" Configuration validation passed")
        
        # Test some config values
        print(f"Email account: {config.email_address}")
        print(f"IMAP server: {config.imap_server}")
        print(f"OpenAI model: {config.openai_model}")
        print(f"Max thread history: {config.max_thread_history}")
        print(f"Log level: {config.log_level}")
        print(f"Require subject: {config.require_subject}")
        
        print("\n Configuration loaded successfully!")
        
    except Exception as e:
        print(f" Configuration error: {e}")
        exit(1)