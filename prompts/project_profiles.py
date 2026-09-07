"""Project-specific aesthetic/cultural steering profiles for Qwen prompt generation.

Each profile is free-form guidance text (geographic, historical, or stylistic
constraints) that gets appended to the end of the model-specific Qwen system
instructions, uniformly across the Schnell/Dev/FLUX.2 sub-tabs.
"""

import os
from typing import Dict

import yaml

NONE_KEY = "none"
NONE_LABEL = "None"

DEFAULT_PROJECT_PROFILES: Dict[str, str] = {
    "middle_east_modern": (
        "PROJECT GEOGRAPHIC & CULTURAL CONSTRAINTS:\n"
        "- Preserve explicit identity, nationality, role, location, period, and attire; source details override "
        "regional defaults.\n"
        "- Choose contemporary clothing from the specific person, role, activity, and occasion. Do not add "
        "traditional or religious garments merely because a scene is set in the Middle East.\n"
        "- Use Arabian garments only when explicitly stated or clearly appropriate; business suits, smart-casual "
        "clothing, workwear, and uniforms remain valid where context supports them.\n"
        "- Keep foreign participants' identity and attire distinct, and match architecture to the stated location."
    ),
    "corporate_global": (
        "PROJECT GEOGRAPHIC & CULTURAL CONSTRAINTS:\n"
        "- All characters must be in sharp, modern business attire (charcoal gray suits, crisp ties).\n"
        "- Architecture must feature minimalist glass skyscrapers and modern steel boardrooms."
    ),
    "nature_documentary": (
        "PROJECT GEOGRAPHIC & CULTURAL CONSTRAINTS:\n"
        "- Focus entirely on organic wilderness, dense vegetation, or pristine natural landscapes.\n"
        "- No human structures, roads, vehicles, or clothing should ever be visible."
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
