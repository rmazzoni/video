"""Project-specific fill-in defaults for unspecified wardrobe and architecture.

Each profile is short guidance used only when a locked beat leaves clothing or
place unnamed. It must never add people or replace the beat.
"""

import os
from typing import Dict

import yaml

NONE_KEY = "none"
NONE_LABEL = "None"

DEFAULT_PROJECT_PROFILES: Dict[str, str] = {
    "middle_east_modern": (
        "PROJECT PROFILE: MODERN MIDDLE EAST\n"
        "Fill only unspecified clothing or place. Never add people, crowds, flags, or events.\n"
        "- Clothing, only if the beat already has a person and names no garments: contemporary "
        "role-appropriate wear. No thobe, ghutra, shemagh, agal, abaya, or headscarf unless the beat names them.\n"
        "- Place, only if unnamed: maintained contemporary concrete, glass, or steel. Not ancient, rustic, or ruined."
    ),
    "corporate_global": (
        "PROJECT PROFILE: CORPORATE GLOBAL\n"
        "Fill only unspecified clothing or place. Never add people, logos, or events.\n"
        "- Clothing, only if the beat already has a person and names no garments: restrained professional "
        "or smart-casual wear.\n"
        "- Place, only if unnamed: a used contemporary office, meeting room, lab, or factory."
    ),
    "nature_documentary": (
        "PROJECT PROFILE: NATURE DOCUMENTARY\n"
        "Fill only unspecified habitat. Never add people, clothing, buildings, roads, vehicles, or signs.\n"
        "- Place, only if unnamed: organic wilderness matching the named species or climate."
    ),
}


def profiles_path(config_dir: str) -> str:
    return os.path.join(config_dir, "project_profiles.yaml")


def load_project_profiles(config_dir: str) -> Dict[str, str]:
    """Load project profiles, seeding the file with defaults on first use."""
    path = profiles_path(config_dir)
    if not os.path.exists(path):
        save_project_profiles(config_dir, DEFAULT_PROJECT_PROFILES)
        return dict(DEFAULT_PROJECT_PROFILES)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
        return {str(key): str(value) for key, value in loaded.items()}
    except Exception:
        return dict(DEFAULT_PROJECT_PROFILES)


def save_project_profiles(config_dir: str, profiles: Dict[str, str]) -> None:
    os.makedirs(config_dir, exist_ok=True)

    def _literal_str_representer(dumper: yaml.Dumper, data: str):
        style = "|" if "\n" in data else None
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)

    dumper = yaml.SafeDumper
    dumper.add_representer(str, _literal_str_representer)
    with open(profiles_path(config_dir), "w", encoding="utf-8") as handle:
        yaml.safe_dump(profiles, handle, allow_unicode=True, sort_keys=False, default_flow_style=False)



def get_profile_text(profiles: Dict[str, str], selected_key: str) -> str:
    if not selected_key or selected_key == NONE_KEY:
        return ""
    return profiles.get(selected_key, "")
