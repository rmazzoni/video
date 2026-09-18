"""Canonical project output folders and assembled media names."""

from __future__ import annotations

import os
import re
from typing import List

import yaml

# Current folder names under output/.
DIR_DRAFT = "draft_video"          # preview stills (was "draft")
DIR_DRAFT_CLIPS = "draft_clips"
DIR_PREVIEW = "preview_video"      # assembled preview (was "preview")
DIR_LIGHTBOX = "lightbox"
DIR_FINAL_CLIPS = "final_clips"    # Ken Burns / SVD clips (was "clips")
DIR_FINAL = "final_video"          # assembled final (was "final")
DIR_AUDIO = "audio"
DIR_IMAGES = "images"

LEGACY_DIR_NAMES = {
    DIR_DRAFT: "draft",
    DIR_PREVIEW: "preview",
    DIR_FINAL_CLIPS: "clips",
    DIR_FINAL: "final",
}

# Unprefixed assembled files, rewritten to {slug}_<name> on migrate.
_PREVIEW_MEDIA_STEMS = (
    "preview_video.mp4",
    "preview_with_audio.mp4",
    "narration_combined.mp3",
)
_FINAL_MEDIA_STEMS = (
    "final_video.mp4",
    "final_with_audio.mp4",
    "final_audio.mp3",
)
_UNPREFIXED_MEDIA = set(_PREVIEW_MEDIA_STEMS + _FINAL_MEDIA_STEMS)

_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_project_slug(name: str) -> str:
    """Filesystem-safe prefix for assembled preview/final media."""
    text = _UNSAFE_CHARS.sub("", (name or "").strip())
    text = re.sub(r"\s+", "_", text)
    text = text.rstrip(" .")
    return text or "project"


def project_name(project_path: str) -> str:
    """Prefer vid_project.yaml name, else the project folder name."""
    root = os.path.normpath(os.path.abspath(project_path))
    manifest_path = os.path.join(root, "vid_project.yaml")
    if os.path.isfile(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as handle:
                data = yaml.safe_load(handle) or {}
            name = str(data.get("name") or "").strip()
            if name:
                return name
        except Exception:
            pass
    return os.path.basename(root) or "project"


def project_slug(project_path: str) -> str:
    return sanitize_project_slug(project_name(project_path))


def prefixed_media_name(slug: str, basename: str) -> str:
    """Prefix a media basename unless this slug was already applied."""
    safe = sanitize_project_slug(slug)
    prefix = f"{safe}_"
    if basename.startswith(prefix):
        rest = basename[len(prefix):]
        if rest in _UNPREFIXED_MEDIA or rest.startswith("final_audio."):
            return basename
    return prefix + basename


def migrate_legacy_output_dirs(project_path: str) -> List[str]:
    """
    Rename leftover output folders/files from the previous layout.

    Safe to call repeatedly. Does not create empty destination folders
    (that would block a later rename of a populated legacy folder).
    """
    notes: List[str] = []
    output = os.path.join(os.path.normpath(os.path.abspath(project_path)), "output")
    if not os.path.isdir(output):
        return notes

    for new_name, old_name in LEGACY_DIR_NAMES.items():
        new_path = os.path.join(output, new_name)
        old_path = os.path.join(output, old_name)
        if os.path.isdir(old_path) and not os.path.exists(new_path):
            try:
                os.rename(old_path, new_path)
                notes.append(f"Renamed output/{old_name} → output/{new_name}")
            except OSError as exc:
                notes.append(f"Could not rename output/{old_name} → output/{new_name}: {exc}")

    slug = project_slug(project_path)
    notes.extend(_prefix_legacy_media(os.path.join(output, DIR_PREVIEW), slug, _PREVIEW_MEDIA_STEMS))
    notes.extend(_prefix_legacy_media(os.path.join(output, DIR_FINAL), slug, _FINAL_MEDIA_STEMS))
    notes.extend(_prefix_glob_stem(os.path.join(output, DIR_FINAL), slug, "final_audio."))
    return notes


def _prefix_legacy_media(folder: str, slug: str, basenames: tuple) -> List[str]:
    notes: List[str] = []
    if not os.path.isdir(folder):
        return notes
    for basename in basenames:
        src = os.path.join(folder, basename)
        dest_name = prefixed_media_name(slug, basename)
        dest = os.path.join(folder, dest_name)
        if os.path.isfile(src) and src != dest and not os.path.exists(dest):
            try:
                os.rename(src, dest)
                notes.append(f"Renamed {os.path.basename(folder)}/{basename} → {dest_name}")
            except OSError as exc:
                notes.append(
                    f"Could not rename {os.path.basename(folder)}/{basename}: {exc}"
                )
    return notes


def _prefix_glob_stem(folder: str, slug: str, stem: str) -> List[str]:
    """Prefix leftover final_audio.* copies (wav/mp3/etc.) that are not already slugged."""
    notes: List[str] = []
    if not os.path.isdir(folder):
        return notes
    prefix = f"{sanitize_project_slug(slug)}_"
    for name in os.listdir(folder):
        if not name.startswith(stem) or name.startswith(prefix):
            continue
        src = os.path.join(folder, name)
        dest = os.path.join(folder, prefix + name)
        if os.path.isfile(src) and not os.path.exists(dest):
            try:
                os.rename(src, dest)
                notes.append(f"Renamed {os.path.basename(folder)}/{name} → {prefix}{name}")
            except OSError as exc:
                notes.append(f"Could not rename {os.path.basename(folder)}/{name}: {exc}")
    return notes


class ProjectLayout:
    """Resolved output paths for one project folder."""

    def __init__(self, project_path: str):
        self.project_path = os.path.normpath(os.path.abspath(project_path))
        self.slug = project_slug(self.project_path)
        self.output = os.path.join(self.project_path, "output")
        self.draft = os.path.join(self.output, DIR_DRAFT)
        self.draft_clips = os.path.join(self.output, DIR_DRAFT_CLIPS)
        self.preview = os.path.join(self.output, DIR_PREVIEW)
        self.lightbox = os.path.join(self.output, DIR_LIGHTBOX)
        self.final_clips = os.path.join(self.output, DIR_FINAL_CLIPS)
        self.final = os.path.join(self.output, DIR_FINAL)
        self.audio = os.path.join(self.output, DIR_AUDIO)
        self.images = os.path.join(self.output, DIR_IMAGES)
        self.preview_video = os.path.join(
            self.preview, prefixed_media_name(self.slug, "preview_video.mp4")
        )
        self.preview_with_audio = os.path.join(
            self.preview, prefixed_media_name(self.slug, "preview_with_audio.mp4")
        )
        self.preview_audio = os.path.join(
            self.preview, prefixed_media_name(self.slug, "narration_combined.mp3")
        )
        self.final_video = os.path.join(
            self.final, prefixed_media_name(self.slug, "final_video.mp4")
        )
        self.final_with_audio = os.path.join(
            self.final, prefixed_media_name(self.slug, "final_with_audio.mp4")
        )
        self.final_audio = os.path.join(
            self.final, prefixed_media_name(self.slug, "final_audio.mp3")
        )

    def migrate_legacy(self) -> List[str]:
        return migrate_legacy_output_dirs(self.project_path)

    def ensure_dirs(self) -> None:
        for path in (
            self.draft,
            self.draft_clips,
            self.preview,
            self.lightbox,
            self.final_clips,
            self.final,
            self.audio,
            self.images,
        ):
            os.makedirs(path, exist_ok=True)

    def combined_audio_name(self, normalize_audio: bool, extension: str = ".mp3") -> str:
        if not extension.startswith("."):
            extension = f".{extension}"
        if normalize_audio:
            return prefixed_media_name(self.slug, f"final_audio{extension}")
        return prefixed_media_name(self.slug, "narration_combined.mp3")
