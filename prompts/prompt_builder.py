from typing import Dict, List, Optional


class PromptBuilder:
    """
    Builds image-generation prompts from scene text.
    Supports style presets, camera direction, and optional character consistency.
    """

    def __init__(
        self,
        style_preset: str = "cinematic",
        default_aspect_ratio: str = "16:9",
        character_refs: Optional[List[str]] = None,
    ):
        """
        :param style_preset: visual style to apply to all prompts
        :param default_aspect_ratio: e.g. "16:9", "9:16", "1:1"
        :param character_refs: optional list of character reference descriptions
        """
        self.style_preset = style_preset
        self.aspect_ratio = default_aspect_ratio
        self.character_refs = character_refs or []

        # Predefined style presets
        self.style_presets = {
            "cinematic": (
                "cinematic lighting, volumetric light, high detail, 35mm lens, "
                "soft shadows, realistic textures, depth of field, dramatic atmosphere"
            ),
            "realistic": (
                "ultra realistic, natural lighting, detailed textures, photographic quality"
            ),
            "anime": (
                "anime style, vibrant colors, clean line art, expressive characters"
            ),
            "watercolor": (
                "soft watercolor painting, gentle brush strokes, pastel tones"
            ),
            "illustration": (
                "digital illustration, clean shading, stylized shapes, bold colors"
            ),
        }

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
        Default cinematic camera motion.
        Later you can make this dynamic based on emotion or scene type.
        """
        return "cinematic composition, subtle camera motion, soft depth of field"
