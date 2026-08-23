import json
from typing import Dict, List, Optional

from prompts.style_presets import STYLE_PRESETS


def structure_prompt_for_model(prompt_text: str, model_type: str, style_preset: str = "cinematic") -> str:
    """
    Reformat a plain descriptive prompt for a specific image model.

    FLUX.2 (Klein) follows structured prompts more reliably than long free-text
    sentences (per BFL's official prompting guide), so scene/style/composition
    are broken out into separate JSON fields. Other models receive the prompt
    text unchanged.
    """
    if model_type != "flux2":
        return prompt_text
    style_desc = STYLE_PRESETS.get(style_preset, STYLE_PRESETS["cinematic"])
    payload = {
        "scene": prompt_text,
        "style": style_desc,
        "composition": (
            "characters facing the camera, front or three-quarter view, "
            "faces clearly visible, medium shot"
        ),
    }
    return json.dumps(payload, ensure_ascii=False)


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

        prompt = (
            f"{scene_text}. "
            f"{style}. "
            f"{characters}"
            f"{camera}. "
            f"Aspect ratio {self.aspect_ratio}."
        )

        # Clean up double spaces
        return " ".join(prompt.split())

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
