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
        "- All civilian and official figures must wear traditional modern Arabian garments "
        "(e.g., pristine white thobes, ghutras, and agals for men). Never depict Western business suits.\n"
        "- All military or militia personnel must wear contemporary arid/desert digital camouflage uniforms "
        "or local tactical gear suitable for the Sahel or Arabian peninsula.\n"
        "- Architecture must feature flat-roofed concrete structures, sandy limestone walls, and contemporary "
        "Gulf urban elements."
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
    with open(profiles_path(config_dir), "w", encoding="utf-8") as handle:
        yaml.safe_dump(profiles, handle, allow_unicode=True, sort_keys=False)


def get_profile_text(profiles: Dict[str, str], selected_key: str) -> str:
    if not selected_key or selected_key == NONE_KEY:
        return ""
    return profiles.get(selected_key, "")
