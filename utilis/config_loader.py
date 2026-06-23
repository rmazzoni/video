import os
import yaml
from typing import Any, Dict, Optional


class ConfigLoader:
    """
    Loads YAML configuration files and provides access to their values.
    """

    def __init__(self, base_config_dir: str):
        """
        :param base_config_dir: directory containing YAML config files
        """
        self.base_config_dir = base_config_dir

    # ---------------------------------------------------------
    # PUBLIC API
    # ---------------------------------------------------------

    def load(
        self,
        filename: str,
        default: Optional[Dict[str, Any]] = None,
        create_if_missing: bool = False,
    ) -> Dict[str, Any]:
        """
        Loads a YAML file from the config directory.
        """
        path = os.path.join(self.base_config_dir, filename)

        if not os.path.exists(path):
            if create_if_missing:
                seed = default or {}
                self.save(filename, seed)
                return dict(seed)
            if default is not None:
                return dict(default)
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f)
            if loaded is None:
                return dict(default or {})
            return loaded

    def load_settings(
        self,
        default: Optional[Dict[str, Any]] = None,
        create_if_missing: bool = False,
    ) -> Dict[str, Any]:
        """
        Loads settings.yaml
        """
        return self.load("settings.yaml", default=default, create_if_missing=create_if_missing)

    def load_models(self) -> Dict[str, Any]:
        """
        Loads models.yaml
        """
        return self.load("models.yaml")

    def save(self, filename: str, data: Dict[str, Any]) -> str:
        """
        Saves a YAML file to the config directory.
        Returns the written file path.
        """
        os.makedirs(self.base_config_dir, exist_ok=True)
        path = os.path.join(self.base_config_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False)
        return path

    def save_settings(self, data: Dict[str, Any]) -> str:
        """
        Saves settings.yaml
        """
        return self.save("settings.yaml", data)

    # ---------------------------------------------------------
    # OPTIONAL: MERGING MULTIPLE CONFIGS
    # ---------------------------------------------------------

    @staticmethod
    def merge(*configs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Merges multiple config dictionaries.
        Later configs override earlier ones.
        """
        merged = {}
        for cfg in configs:
            merged.update(cfg)
        return merged
