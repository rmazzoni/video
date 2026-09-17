import re
from typing import Dict, List, Optional, Tuple

from prompts.style_presets import STYLE_PRESETS

_MODEL_TYPE_KEYS = {
    "flux-schnell": "schnell",
    "schnell": "schnell",
    "zimage-turbo": "zimage",
    "zimage": "zimage",
    "flux-dev": "dev",
    "dev": "dev",
    "hidream-dev": "hidream",
    "hidream": "hidream",
    "flux2": "flux2",
}

# Older slogans that made Z-Image Turbo hazy/soft. Still stripped from stored prompts.
_LEGACY_STYLE_ANCHORS = (
    "Cinematic photograph, natural materials, photographic depth, motivated light.",
    "Cinematic photograph, natural materials, photographic lighting and depth.",
    "Photographic scene, realistic materials, directional light, spatial depth.",
    "Clear photograph, distinct faces, natural materials, directional room light.",
    "Precise photographic scene, realistic surfaces, directional light.",
)

_HAZE_RE = re.compile(
    r"\b(?:photographic\s+depth|motivated\s+light|"
    r"volumetric(?:\s+(?:light|fog|haze))?|"
    r"(?:soft|shallow)\s+depth\s+of\s+field|depth\s+of\s+field|"
    r"bokeh|atmospheric\s+haze|cinematic\s+atmosphere|god\s+rays|"
    r"bloom|hazy|dreamy|soft\s+focus)\b[,.]?",
    re.IGNORECASE,
)


def join_prompt_parts(*parts: str) -> str:
    """Join prompt fragments into one paragraph without doubled periods or spaces."""
    sentences: List[str] = []
    for part in parts:
        text = " ".join(str(part or "").split()).strip(" ,;")
        if not text:
            continue
        text = text.rstrip(".")
        if text:
            sentences.append(text)
    if not sentences:
        return ""
    return ". ".join(sentences) + "."


def _style_anchor_values() -> List[str]:
    from prompts.visual_styles import VISUAL_STYLES

    anchors: List[str] = []
    for style in VISUAL_STYLES.values():
        raw = style.get("prompt_anchors") or {}
        if not isinstance(raw, dict):
            continue
        for value in raw.values():
            text = str(value or "").strip().rstrip(".")
            if text:
                anchors.append(text)
    for value in _LEGACY_STYLE_ANCHORS:
        text = value.strip().rstrip(".")
        if text:
            anchors.append(text)
    # Unique, longest first so short slogans cannot eat longer ones.
    unique = sorted(set(anchors), key=len, reverse=True)
    return unique


def split_leading_style_anchor(prompt_text: str) -> Tuple[str, str]:
    """Move a known cinematic style slogan off the front of the prompt."""
    text = str(prompt_text or "").strip()
    if not text:
        return "", ""
    lower = text.lower()
    for anchor in _style_anchor_values():
        needle = anchor.lower()
        if lower.startswith(needle):
            rest = text[len(anchor):].lstrip(" .,")
            return rest, anchor
        prefixed = needle + "."
        if lower.startswith(prefixed):
            rest = text[len(anchor) + 1:].lstrip(" .,")
            return rest, anchor
    return text, ""


def strip_known_style_anchors(prompt_text: str) -> Tuple[str, bool]:
    """Remove known style slogans anywhere in the prompt.

    Returns (body, used_illustration_style).
    """
    text = str(prompt_text or "").strip()
    illustration = False
    for anchor in _style_anchor_values():
        pattern = re.compile(re.escape(anchor.rstrip(".")) + r"\.?", re.IGNORECASE)
        if pattern.search(text):
            lower = anchor.lower()
            if "illustration" in lower or "painted" in lower:
                illustration = True
            text = pattern.sub(" ", text)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\s+([,.;])", r"\1", text).strip(" ,.")
    return text, illustration


def strip_haze_phrases(prompt_text: str) -> str:
    """Drop cinematic haze/DoF slogans that make Turbo images look foggy."""
    text = _HAZE_RE.sub(" ", str(prompt_text or ""))
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\s+([,.;])", r"\1", text)
    text = re.sub(r"\.{2,}", ".", text)
    return text.strip(" ,.")


def _style_for_render(illustration: bool, model_type: str) -> str:
    from prompts.visual_styles import visual_style_prompt_anchor

    model_key = _MODEL_TYPE_KEYS.get(str(model_type or "").lower(), "")
    if not model_key:
        return ""
    style_key = "cinematic_editorial_illustrator" if illustration else "cinematic"
    return visual_style_prompt_anchor(style_key, model_key)


def structure_prompt_for_model(prompt_text: str, model_type: str, style_preset: str = "cinematic") -> str:
    """Shape stored prompt text for the image model at render time.

    Distilled models (especially Z-Image Turbo) follow early subject tokens
    and ignore negative prompts. Put visible identity first, keep the scene,
    then append a sharp style phrase and Turbo constraints. Idempotent.
    """
    from prompts.visual_identity import (
        ZIMAGE_RENDER_CONSTRAINTS,
        apply_visual_identity,
    )

    if not str(prompt_text or "").strip():
        return ""
    scene, illustration = strip_known_style_anchors(prompt_text)
    scene = apply_visual_identity(scene)
    if str(model_type or "").lower() in {"zimage-turbo", "zimage"}:
        scene = strip_haze_phrases(scene)
    style = _style_for_render(illustration, model_type)
    parts = [scene]
    if style and style.rstrip(".").lower() not in scene.lower():
        parts.append(style)
    if str(model_type or "").lower() in {"zimage-turbo", "zimage"}:
        if "sharp focus, clear air" not in scene.lower():
            parts.append(ZIMAGE_RENDER_CONSTRAINTS)
    return join_prompt_parts(*parts)


class PromptBuilder:
    """
    Builds image-generation prompts from scene text.
    Supports style presets, camera direction, and optional character consistency.
    Optionally enhances prompts via a local Ollama LLM.
    """

    def __init__(
        self,
        style_preset: str = "cinematic",
        default_aspect_ratio: str = "16:9",
        character_refs: Optional[List[str]] = None,
        use_ollama: bool = False,
        ollama_model: str = "qwen3:8b",
        ollama_host: str = "http://localhost:11434",
    ):
        """
        :param style_preset: visual style to apply to all prompts
        :param default_aspect_ratio: e.g. "16:9", "9:16", "1:1"
        :param character_refs: optional list of character reference descriptions
        :param use_ollama: whether to enhance prompts via Ollama
        :param ollama_model: Ollama model name
        :param ollama_host: Ollama server URL
        """
        self.style_preset = style_preset
        self.aspect_ratio = default_aspect_ratio
        self.character_refs = character_refs or []

        self._enhancer = None
        if use_ollama:
            from prompts.prompt_enhancer import PromptEnhancer
            self._enhancer = PromptEnhancer(model=ollama_model, host=ollama_host)

        # Style presets are defined once in prompts/style_presets.py (shared with the Settings UI)
        self.style_presets = STYLE_PRESETS

    # ---------------------------------------------------------
    # PUBLIC API
    # ---------------------------------------------------------

    def build_prompt(self, scene: Dict) -> str:
        """
        Build a full image prompt from a scene dict:
        {
            "id": 1,
            "text": "The fisherman walked along the pier at sunrise."
        }
        """
        scene_text = scene["text"]

        # Try Ollama enhancement first
        if self._enhancer:
            style_hint = self._get_style_preset()
            enhanced = self._enhancer.enhance(scene_text, style_hint=style_hint)
            if enhanced:
                return enhanced

        # Fall back to rule-based prompt
        style = self._get_style_preset()
        characters = self._get_character_references()
        camera = self._get_default_camera_direction()

        return join_prompt_parts(scene_text, style, characters, camera)

    # ---------------------------------------------------------
    # INTERNAL HELPERS
    # ---------------------------------------------------------

    def _get_style_preset(self) -> str:
        return self.style_presets.get(self.style_preset, self.style_presets["cinematic"])

    def _get_character_references(self) -> str:
        if not self.character_refs:
            return ""
        refs = ", ".join(self.character_refs)
        return f"Featuring characters: {refs}. "

    def _get_default_camera_direction(self) -> str:
        """
        Default cinematic camera framing. Biases towards showing characters
        facing the camera rather than from behind.
        """
        return (
            "cinematic composition, characters facing the camera, "
            "front or three-quarter view, faces clearly visible, "
            "medium shot, soft depth of field"
        )
