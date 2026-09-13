"""Profile-driven generation and persistence for model-specific scene prompts."""

import json
import logging
import os
from typing import Any, Dict, List, Sequence, Union

import yaml

from prompts.prompt_builder import PromptBuilder, structure_prompt_for_model
from prompts.prompt_grounding import check_prompt, retry_instruction
from prompts.response_sanitizer import sanitize_generated_prompt
from prompts.visual_beats import (
    VisualBeat,
    extract_structured_beats,
    fallback_beat,
    normalize_stored_beats,
)
from prompts.visual_styles import (
    DEFAULT_VISUAL_STYLE,
    visual_style_fallback_preset,
    visual_style_instruction,
    visual_style_prompt_anchor,
)


logger = logging.getLogger(__name__)

MODEL_KEYS = ("schnell", "zimage", "dev", "hidream", "flux2")
MODEL_TYPES = {
    "schnell": "flux-schnell",
    "zimage": "zimage-turbo",
    "dev": "flux-dev",
    "hidream": "hidream-dev",
    "flux2": "flux2",
}

PROMPT_ONLY_SCHEMA = {
    "type": "object",
    "properties": {
        "prompt": {"type": "string"},
    },
    "required": ["prompt"],
    "additionalProperties": False,
}

LOCKED_BEAT_INSTRUCTION = (
    "LOCKED VISUAL BEAT:\n"
    "The locked visual beat is the entire image content. Preserve its subject, "
    "action, setting, and objects. Do not add people, events, props, text, "
    "devices, crowds, or places that are absent from the locked visual beat and "
    "the original narration. You may add camera, lighting, materials, and "
    "atmosphere only. Output one image prompt paragraph; do not redefine the beat."
)

PROJECT_PROFILE_WRAPPER = (
    "PROJECT PROFILE — UNSPECIFIED DEFAULTS ONLY:\n"
    "Use the following only to fill wardrobe, architecture, or regional appearance "
    "when the locked visual beat does not specify them. They must not replace the "
    "beat, add characters, or introduce objects or events that are not in the "
    "locked beat and narration.\n\n"
)

BeatInput = Union[str, Dict[str, Any], VisualBeat]


def wrap_project_profile(profile_text: str) -> str:
    text = str(profile_text or "").strip()
    if not text:
        return ""
    return f"{PROJECT_PROFILE_WRAPPER}{text}"


def build_prompt_user_payload(scene: Dict[str, Any], beat: VisualBeat) -> Dict[str, Any]:
    return {
        "scene_id": int(scene.get("id") or 0),
        "narration": scene.get("text", ""),
        "locked_visual_beat": beat.to_dict(),
        "source_fidelity": (
            "Depict only the locked visual beat. Use the narration as supporting "
            "context. Do not reuse generic content from other scenes or invent a "
            "person, object, or place when none is described."
        ),
    }


class ModelPromptService:
    def __init__(self, profiles_dir: str, ollama_model: str, ollama_host: str,
                 max_visual_beats: int = None, project_profile_text: str = "",
                 visual_style_key: str = DEFAULT_VISUAL_STYLE,
                 extraction_guidance: str = ""):
        self.profiles_dir = profiles_dir
        self.ollama_model = ollama_model
        self.ollama_host = ollama_host
        self.max_visual_beats = max_visual_beats
        self.project_profile_text = (project_profile_text or "").strip()
        self.visual_style_key = visual_style_key
        self.extraction_guidance = (extraction_guidance or "").strip()

    def load_profile(self, model_key: str) -> Dict[str, Any]:
        if model_key not in MODEL_KEYS:
            raise ValueError(f"Unknown prompt profile: {model_key}")
        path = os.path.join(self.profiles_dir, f"{model_key}.yaml")
        with open(path, "r", encoding="utf-8") as handle:
            profile = yaml.safe_load(handle) or {}
        profile["model_key"] = model_key
        if self.max_visual_beats is not None:
            profile["max_prompts_per_scene"] = int(self.max_visual_beats)
        profile["style_preset"] = visual_style_fallback_preset(self.visual_style_key)
        system_parts = [LOCKED_BEAT_INSTRUCTION]
        base_instruction = str(profile.get("system_instruction", "")).strip()
        if base_instruction:
            system_parts.append(base_instruction)
        style_instruction = visual_style_instruction(self.visual_style_key, model_key)
        if style_instruction:
            system_parts.append(f"GLOBAL VISUAL STYLE:\n{style_instruction}")
        wrapped_profile = wrap_project_profile(self.project_profile_text)
        if wrapped_profile:
            system_parts.append(wrapped_profile)
        profile["system_instruction"] = "\n\n".join(system_parts)
        return profile

    def generate(self, scene: Dict[str, Any], model_key: str) -> List[Dict[str, Any]]:
        beats = self.extract_structured_beats(scene)
        return self.generate_for_beats(scene, model_key, beats)

    def extract_structured_beats(self, scene: Dict[str, Any]) -> List[VisualBeat]:
        return extract_structured_beats(
            scene,
            ollama_model=self.ollama_model,
            ollama_host=self.ollama_host,
            max_visual_beats=self.max_visual_beats,
            extra_system=self.extraction_guidance,
        )

    def extract_visual_beats(self, scene: Dict[str, Any]) -> List[str]:
        """Identify model-independent shots once for reuse by every image model."""
        return [beat.beat for beat in self.extract_structured_beats(scene)]

    def generate_for_beats(
        self,
        scene: Dict[str, Any],
        model_key: str,
        visual_beats: Sequence[BeatInput],
    ) -> List[Dict[str, Any]]:
        """Generate model-specific wording without allowing the model to redefine shots."""
        beats = normalize_stored_beats(visual_beats)
        if not beats:
            beats = [fallback_beat(str(scene.get("text") or ""))]
        rows = []
        for index, beat in enumerate(beats, 1):
            rows.append(self.prompt_row_for_beat(scene, model_key, beat, index))
        return rows

    def prompt_row_for_beat(
        self,
        scene: Dict[str, Any],
        model_key: str,
        visual_beat: BeatInput,
        beat_index: int,
    ) -> Dict[str, Any]:
        beat = VisualBeat.from_stored(visual_beat) or fallback_beat(str(scene.get("text") or ""))
        prompt = self.regenerate_prompt(scene, model_key, beat)
        return {
            "id": f"scene_{int(scene['id']):03d}_beat_{int(beat_index):02d}_{model_key}",
            "beat": int(beat_index),
            "visual_beat": beat.beat,
            "text": prompt,
            "generated_prompt": prompt,
            "source": "generated",
        }

    def regenerate_prompt(
        self,
        scene: Dict[str, Any],
        model_key: str,
        visual_beat: BeatInput,
    ) -> str:
        """Generate one replacement prompt while keeping the selected visual beat fixed."""
        profile = self.load_profile(model_key)
        beat = VisualBeat.from_stored(visual_beat)
        if beat is None:
            beat = fallback_beat(str(scene.get("text") or ""))
        return self._generate_prompt_for_beat(scene, profile, beat)

    def _chat_prompt(self, system_instruction: str, user_content: str) -> str:
        from prompts.ollama_runtime import chat_json_object

        payload = chat_json_object(
            host=self.ollama_host,
            model=self.ollama_model,
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_content},
            ],
            options={
                "temperature": 0.35,
                "top_p": 0.85,
                "stop": ["\nScript Segment", "\nNarration:", "\nUser:"],
            },
        )
        return sanitize_generated_prompt(payload.get("prompt", ""))

    def _generate_prompt_for_beat(
        self,
        scene: Dict[str, Any],
        profile: Dict[str, Any],
        beat: VisualBeat,
    ) -> str:
        narration = str(scene.get("text") or "")
        model_key = str(profile.get("model_key", ""))
        user_payload = json.dumps(build_prompt_user_payload(scene, beat), ensure_ascii=False)
        system_instruction = str(profile.get("system_instruction", ""))

        prompt = ""
        try:
            prompt = self._chat_prompt(system_instruction, user_payload)
            result = check_prompt(prompt, beat, narration)
            if prompt and not result.ok:
                logger.info("Prompt failed grounding (%s); retrying once", result.summary())
                retry_payload = json.dumps({
                    **build_prompt_user_payload(scene, beat),
                    "correction": retry_instruction(result),
                    "previous_prompt": prompt,
                }, ensure_ascii=False)
                retry_prompt = self._chat_prompt(system_instruction, retry_payload)
                retry_result = check_prompt(retry_prompt, beat, narration)
                if retry_prompt and retry_result.ok:
                    prompt = retry_prompt
                else:
                    logger.warning(
                        "Prompt still ungrounded after retry (%s); using template",
                        retry_result.summary() if retry_prompt else "empty retry",
                    )
                    prompt = ""
        except Exception:
            logger.exception("Locked prompt generation failed; using template fallback")
            prompt = ""

        if not prompt:
            prompt = self._template_prompt(scene, profile, beat)
        else:
            anchor = visual_style_prompt_anchor(self.visual_style_key, model_key)
            if anchor:
                prompt = f"{anchor} {prompt}"
        return prompt

    def _template_prompt(
        self,
        scene: Dict[str, Any],
        profile: Dict[str, Any],
        beat: VisualBeat,
    ) -> str:
        builder = PromptBuilder(
            style_preset=str(profile.get("style_preset", "cinematic")),
            default_aspect_ratio=str(profile.get("aspect_ratio", "16:9")),
        )
        focused_scene = dict(scene)
        focused_scene["text"] = beat.beat or scene.get("text", "")
        prompt = builder.build_prompt(focused_scene)
        anchor = visual_style_prompt_anchor(
            self.visual_style_key, str(profile.get("model_key", ""))
        )
        if anchor:
            prompt = f"{anchor} {prompt}"
        return structure_prompt_for_model(
            prompt,
            MODEL_TYPES[profile["model_key"]],
            str(profile.get("style_preset", "cinematic")),
        )


def effective_prompt(entry: Dict[str, Any]) -> str:
    """Return the first usable manual or generated prompt from a model entry."""
    prompts = entry.get("prompts", []) if isinstance(entry, dict) else []
    for prompt in prompts:
        if isinstance(prompt, dict) and str(prompt.get("text", "")).strip():
            return str(prompt["text"]).strip()
    return ""
