from typing import Dict, List, Optional


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
        ollama_model: str = "llama3",
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
            "noir": (
                "black and white photography, dramatic chiaroscuro, deep shadows, "
                "1940s detective atmosphere, high contrast, rain-slicked streets"
            ),
            "baroque": (
                "baroque painting style, ornate composition, dramatic lighting, "
                "rich jewel tones, deep shadow, oil painting texture, Rembrandt lighting"
            ),
            "concept art": (
                "professional concept art, detailed environment design, "
                "matte painting, epic scale, studio quality, bold composition"
            ),
            "oil painting": (
                "oil painting, thick impasto brushwork, rich saturated colour, "
                "canvas texture, classical technique, museum quality"
            ),
            "impressionist": (
                "impressionist painting, loose expressive brushwork, dappled light, "
                "soft edges, vibrant colour palette, plein air atmosphere"
            ),
            "ghibli": (
                "Studio Ghibli style, soft anime aesthetic, lush detailed backgrounds, "
                "warm natural lighting, gentle colour palette, hand-drawn feel"
            ),
            "golden hour": (
                "golden hour lighting, warm orange and amber tones, long soft shadows, "
                "lens flare, photorealistic, rich depth of field"
            ),
            "ethereal": (
                "ethereal dreamlike atmosphere, soft glowing light, pastel mist, "
                "otherworldly beauty, delicate details, surreal fantasy"
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
