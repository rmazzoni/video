import logging
from typing import Optional

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are an expert at writing prompts for AI image generation models like Stable Diffusion. "
    "When given a scene description, rewrite it as a single, richly detailed image generation prompt. "
    "Focus on visual elements: lighting, atmosphere, colours, composition, and mood. "
    "Do NOT include any explanation, preamble, or multiple options. "
    "Output only the prompt text, on a single line."
)


class PromptEnhancer:
    """
    Enhances plain scene text into optimised image-generation prompts
    using a local Ollama LLM. Falls back silently if Ollama is unavailable.
    """

    def __init__(self, model: str = "llama3", host: str = "http://localhost:11434"):
        self._model = model
        self._host = host
        self._available: Optional[bool] = None  # None = not yet checked

    # ---------------------------------------------------------
    # PUBLIC API
    # ---------------------------------------------------------

    def enhance(self, scene_text: str, style_hint: str = "") -> Optional[str]:
        """
        Return an enhanced prompt string, or None if Ollama is unavailable.

        :param scene_text: raw scene description from the script
        :param style_hint: optional style cue appended to the user message
        :return: enhanced prompt, or None on failure
        """
        if not self._check_available():
            return None

        user_message = scene_text
        if style_hint:
            user_message += f"\n\nStyle: {style_hint}"

        try:
            import ollama
            client = ollama.Client(host=self._host)
            response = client.chat(
                model=self._model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user",   "content": user_message},
                ],
            )
            # SDK >= 0.4 returns a ChatResponse object; older versions return a dict
            msg = getattr(response, "message", None)
            if msg is not None:
                result = getattr(msg, "content", "") or ""
            else:
                result = response["message"]["content"]
            result = " ".join(result.strip().splitlines())
            return result if result else None
        except Exception as exc:
            logger.warning("Ollama prompt enhancement failed: %s", exc)
            self._available = False
            return None

    def is_available(self) -> bool:
        return self._check_available()

    # ---------------------------------------------------------
    # INTERNAL
    # ---------------------------------------------------------

    def _check_available(self) -> bool:
        if self._available is not None:
            return self._available

        try:
            import ollama
            client = ollama.Client(host=self._host)
            response = client.list()
            # SDK >= 0.4: response is a ListResponse with .models list of Model objects
            models_list = getattr(response, "models", None) or response.get("models", [])
            names = []
            for m in models_list:
                # Model object has .model attribute; dict fallback for older SDK
                name = getattr(m, "model", None) or m.get("model", "") or m.get("name", "")
                if name:
                    names.append(name)

            if not any(self._model in n for n in names):
                logger.warning(
                    "Ollama model '%s' not found. Available: %s. "
                    "Falling back to rule-based prompts.",
                    self._model, names,
                )
                self._available = False
            else:
                logger.info("Ollama prompt enhancer ready (model: %s)", self._model)
                self._available = True
        except Exception as exc:
            logger.info("Ollama not available (%s). Using rule-based prompts.", exc)
            self._available = False

        return self._available
