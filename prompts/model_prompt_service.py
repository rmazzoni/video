"""Profile-driven generation and persistence for model-specific scene prompts."""

import json
import logging
import os
from typing import Any, Dict, List, Sequence, Tuple, Union

import yaml

from prompts.prompt_builder import join_prompt_parts
from prompts.prompt_grounding import check_prompt, retry_instruction
from prompts.response_sanitizer import sanitize_generated_prompt
from prompts.visual_identity import apply_visual_identity
from prompts.visual_beats import (
    VisualBeat,
    extract_structured_beats,
    fallback_beat,
    normalize_stored_beats,
)
from prompts.visual_styles import (
    DEFAULT_VISUAL_STYLE,
    visual_style_fallback_preset,
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
    "The locked visual beat is the only image content. Depict its subject, action, "
    "setting, and objects. If a field is empty, it is absent from the image.\n\n"
    "Do not add people, crowds, extra faces, unnamed buildings, devices, text, "
    "flags, or places that are not in the locked visual beat. If the beat has "
    "no person, the image has no person and no clothing.\n\n"
    "If the beat names a nationality, ethnicity, or country of origin, describe "
    "the visible face and complexion of that named person. Do not leave identity "
    "as a caption such as 'from the UAE'. Clothing of a named person should match "
    "that country and role; this depicts the named subject, not a new person.\n\n"
    "If the beat names a person, use a medium or medium-full shot with the face "
    "clearly visible and detailed unless the beat is a distant figure in a "
    "landscape. If the beat names a direction of travel, keep that destination "
    "in the background or to the side. Toward an exit means walking to a doorway "
    "with the face still readable, not receding from the camera as a small figure.\n\n"
    "Do not copy the beat sentence verbatim and do not wrap it in quality tags "
    "or photographic keyword lists. Write one English photograph prompt using "
    "camera distance, light, and materials of named things only. Do not add "
    "haze, fog, bloom, bokeh, volumetric light, or soft focus unless the beat "
    "names weather.\n\n"
    "Do not mention aspect ratio, resolution, seed, sampler, or step count. A "
    "short model style phrase is appended after the scene. Start with the "
    "subject, not a style slogan. Output one English paragraph."
)

PROJECT_PROFILE_WRAPPER = (
    "PROJECT PROFILE — UNSPECIFIED WARDROBE AND ARCHITECTURE ONLY:\n"
    "Use the following only when the locked beat leaves clothing or place unnamed. "
    "Never add a person, crowd, event, or prop. Never replace the beat. If the "
    "beat has no person, ignore clothing rules. If the beat names a place, ignore "
    "architecture rules.\n\n"
)

BeatInput = Union[str, Dict[str, Any], VisualBeat]


def wrap_project_profile(profile_text: str) -> str:
    text = str(profile_text or "").strip()
    if not text:
        return ""
    return f"{PROJECT_PROFILE_WRAPPER}{text}"


def beat_needs_profile_defaults(beat: VisualBeat) -> bool:
    """Skip the project profile when the beat already names who and where."""
    has_subject = bool(str(beat.subject or "").strip())
    has_setting = bool(str(beat.setting or "").strip())
    return not (has_subject and has_setting)


def build_prompt_user_payload(scene: Dict[str, Any], beat: VisualBeat) -> Dict[str, Any]:
    return {
        "scene_id": int(scene.get("id") or 0),
        "locked_visual_beat": beat.to_dict(),
        "source_fidelity": (
            "Depict only the locked visual beat. Do not invent a person, object, "
            "or place when the beat does not name one."
        ),
        "writing_rules": (
            "Write one English photograph prompt of the locked beat. "
            "If a nationality is named, state visible appearance of that person. "
            "If motion has a direction, state body orientation and destination. "
            "Do not quote the beat verbatim. Do not mention aspect ratio or "
            "generation parameters. Return JSON with a single 'prompt' string."
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
        profile["model_instruction"] = str(profile.get("system_instruction", "")).strip()
        return profile

    def _system_instruction_for_beat(
        self,
        profile: Dict[str, Any],
        beat: VisualBeat,
    ) -> str:
        parts = [LOCKED_BEAT_INSTRUCTION]
        model_instruction = str(
            profile.get("model_instruction") or profile.get("system_instruction") or ""
        ).strip()
        if model_instruction:
            parts.append(model_instruction)
        if beat_needs_profile_defaults(beat):
            wrapped = wrap_project_profile(self.project_profile_text)
            if wrapped:
                parts.append(wrapped)
        return "\n\n".join(parts)

    def _profile_text_for_grounding(self, beat: VisualBeat) -> str:
        if not beat_needs_profile_defaults(beat):
            return ""
        return self.project_profile_text

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
        prompt, source, error = self._generate_prompt_for_beat(
            scene, self.load_profile(model_key), beat
        )
        row = {
            "id": f"scene_{int(scene['id']):03d}_beat_{int(beat_index):02d}_{model_key}",
            "beat": int(beat_index),
            "visual_beat": beat.beat,
            "text": prompt,
            "source": source,
        }
        if source == "generated":
            row["generated_prompt"] = prompt
        if error:
            row["grounding_error"] = error
        return row

    def regenerate_prompt(
        self,
        scene: Dict[str, Any],
        model_key: str,
        visual_beat: BeatInput,
    ) -> Tuple[str, str, str]:
        """Generate one replacement prompt while keeping the selected visual beat fixed.

        Returns (prompt_text, source, grounding_error). source is generated,
        ungrounded, or fallback.
        """
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
                "temperature": 0.0,
                "top_p": 0.8,
                "stop": ["\nScript Segment", "\nNarration:", "\nUser:"],
            },
            allow_prose=True,
        )
        if not isinstance(payload, dict):
            return ""
        text = (
            payload.get("prompt")
            or payload.get("image_prompt")
            or payload.get("text")
            or ""
        )
        return sanitize_generated_prompt(str(text))

    def _generate_prompt_for_beat(
        self,
        scene: Dict[str, Any],
        profile: Dict[str, Any],
        beat: VisualBeat,
    ) -> Tuple[str, str, str]:
        model_key = str(profile.get("model_key", ""))
        user_payload = json.dumps(build_prompt_user_payload(scene, beat), ensure_ascii=False)
        system_instruction = self._system_instruction_for_beat(profile, beat)
        profile_text = self._profile_text_for_grounding(beat)
        style_anchor = visual_style_prompt_anchor(self.visual_style_key, model_key)

        try:
            prompt = self._chat_prompt(system_instruction, user_payload)
            result = check_prompt(prompt, beat, profile_text=profile_text)
            if prompt and result.ok:
                return self._finalize_prompt(prompt, beat, style_anchor), "generated", ""
            logger.info("Prompt failed grounding (%s); retrying once", result.summary())
            retry_payload = json.dumps({
                **build_prompt_user_payload(scene, beat),
                "correction": retry_instruction(result),
                "previous_prompt": prompt,
            }, ensure_ascii=False)
            retry_prompt = self._chat_prompt(system_instruction, retry_payload)
            retry_result = check_prompt(retry_prompt, beat, profile_text=profile_text)
            if retry_prompt and retry_result.ok:
                return self._finalize_prompt(retry_prompt, beat, style_anchor), "generated", ""
            error = (
                retry_result.summary() if retry_prompt else result.summary()
            ) or "empty retry"
            logger.warning("Prompt still ungrounded after retry (%s); keeping locked beat", error)
            return str(beat.beat or "").strip(), "ungrounded", error
        except Exception:
            logger.exception("Locked prompt generation failed; using beat template")
            return self._template_prompt(scene, profile, beat), "fallback", ""

    def _template_prompt(
        self,
        scene: Dict[str, Any],
        profile: Dict[str, Any],
        beat: VisualBeat,
    ) -> str:
        """Fallback when Qwen is unavailable: staged beat, then a short style phrase.

        Do not append aspect ratio or a second cinematic keyword list. Canvas
        size is already set in application settings.
        """
        return self._finalize_prompt(
            self._staged_beat_text(scene, beat),
            beat,
            visual_style_prompt_anchor(
                self.visual_style_key, str(profile.get("model_key", ""))
            ),
        )

    @staticmethod
    def _finalize_prompt(prompt: str, beat: VisualBeat, style_anchor: str) -> str:
        """Scene and visible identity first; style slogan last."""
        scene = apply_visual_identity(prompt, beat.beat)
        return join_prompt_parts(scene, style_anchor)

    @staticmethod
    def _staged_beat_text(scene: Dict[str, Any], beat: VisualBeat) -> str:
        if beat.subject and beat.action:
            parts = [f"{beat.subject} {beat.action}".strip()]
            if beat.setting:
                setting = beat.setting.strip()
                if setting.lower().startswith(("in ", "on ", "at ", "near ")):
                    parts.append(setting)
                else:
                    parts.append(f"in {setting}")
            if beat.objects:
                parts.append("with " + ", ".join(beat.objects))
            return " ".join(parts)
        return str(beat.beat or scene.get("text") or "").strip()


def effective_prompt(entry: Dict[str, Any]) -> str:
    """Return the first usable manual or generated prompt from a model entry."""
    from prompts.visual_beats import prompt_row_is_ready

    prompts = entry.get("prompts", []) if isinstance(entry, dict) else []
    for prompt in prompts:
        if prompt_row_is_ready(prompt):
            return str(prompt["text"]).strip()
    return ""
