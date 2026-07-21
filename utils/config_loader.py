# config_loader.py
# Loads YAML configurations dynamically for the framework.

import yaml
from pathlib import Path
from typing import Dict, Any

def load_yaml_config(config_path: Path) -> Dict[str, Any]:
    """
    Loads and parses a YAML configuration file.
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config or {}

def get_full_config(configs_dir: Path) -> Dict[str, Any]:
    """
    Combines all configurations under the configs/ directory.
    """
    full_config = {}
    for filename in ["model_config.yaml", "training_config.yaml", "api_config.yaml", "frontend_config.yaml"]:
        path = configs_dir / filename
        if path.exists():
            config_name = filename.split("_")[0]
            full_config[config_name] = load_yaml_config(path)
    return full_config
