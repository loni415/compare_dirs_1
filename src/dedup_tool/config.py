"""Configuration management for deduplication tool."""

import os
from pathlib import Path

from platformdirs import user_config_dir


APP_NAME = "dedup-tool"


def get_config_dir() -> Path:
    """Get configuration directory."""
    config_dir = Path(user_config_dir(APP_NAME))
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_default_credentials_path() -> Path | None:
    """Get default Google Drive credentials path."""
    config_dir = get_config_dir()
    default_path = config_dir / "gdrive_credentials.json"
    if default_path.exists():
        return default_path
    
    # Check environment variable
    env_path = os.environ.get('DEDUP_GDRIVE_CREDENTIALS')
    if env_path and Path(env_path).exists():
        return Path(env_path)
    
    return None


def load_config() -> dict:
    """Load configuration from file."""
    config_file = get_config_dir() / "config.json"
    if config_file.exists():
        import json
        with open(config_file) as f:
            return json.load(f)
    return {}
