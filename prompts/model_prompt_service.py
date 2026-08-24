"""Profile-driven generation and persistence for model-specific scene prompts."""

import json
import os
from typing import Any, Dict, List

import yaml

from prompts.prompt_builder import PromptBuilder, structure_prompt_for_model
from prompts.response_sanitizer import sanitize_generated_prompt


MODEL_KEYS = ("schnell", "dev", "flux2")
MODEL_TYPES = {"schnell": "flux-schnell", "dev": "flux-dev", "flux2": "flux2"}

DEV_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "prompts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "visual_beat": {"type": "string"},
                    "prompt": {"type": "string"},
                },
                "required": ["visual_beat", "prompt"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["prompts"],
    "additionalProperties": False,
}


class ModelPromptService:
    def __init__(self, profiles_dir: str, ollama_model: str, ollama_host: str,
                 max_visual_beats: int = None, project_profile_text: str = ""):
        self.profiles_dir = profiles_dir
        self.ollama_model = ollama_model
        self.ollama_host = ollama_host
        self.max_visual_beats = max_visual_beats
        self.project_profile_text = (project_profile_text or "").strip()

    def load_profile(self, model_key: str) -> Dict[str, Any]:
        if model_key not in MODEL_KEYS:
            raise ValueError(f"Unknown prompt profile: {model_key}")
        path = os.path.join(self.profiles_dir, f"{model_key}.yaml")
        with open(path, "r", encoding="utf-8") as handle:
            profile = yaml.safe_load(handle) or {}
        profile["model_key"] = model_key
        if self.max_visual_beats is not None:
            profile["max_prompts_per_scene"] = int(self.max_visual_beats)
        if self.project_profile_text:
            base_instruction = str(profile.get("system_instruction", ""))
            profile["system_instruction"] = f"{base_instruction}\n\n{self.project_profile_text}"
        return profile

    def generate(self, scene: Dict[str, Any], model_key: str) -> List[Dict[str, Any]]:
        profile = self.load_profile(model_key)
        generated = self._generate_with_ollama(scene, profile)
        if not generated:
            generated = self._fallback(scene, profile)
        return [
            {
                "id": f"scene_{int(scene['id']):03d}_beat_{index:02d}_{model_key}",
                "beat": index,
                "visual_beat": item["visual_beat"],
                "text": item["prompt"],
                "generated_prompt": item["prompt"],
                "source": "generated",
            }
            for index, item in enumerate(generated, 1)
        ]

    def regenerate_prompt(self, scene: Dict[str, Any], model_key: str, visual_beat: str) -> str:
        """Generate one replacement prompt while keeping the selected visual beat fixed."""
        profile = self.load_profile(model_key)
        focused_scene = dict(scene)
        focused_scene["text"] = (
            f"Original script:\n{scene['text']}\n\nVisual beat to depict:\n{visual_beat}"
        )
        focused_profile = dict(profile)
        focused_profile["max_prompts_per_scene"] = 1
        generated = self._generate_with_ollama(focused_scene, focused_profile)
        if generated:
            return generated[0]["prompt"]
        return self._fallback(focused_scene, profile)[0]["prompt"]

    def _generate_with_ollama(self, scene: Dict[str, Any], profile: Dict[str, Any]) -> List[Dict[str, str]]:
        try:
            import ollama

            model_key = str(profile.get("model_key", ""))
            system_instruction = str(profile.get("system_instruction", ""))
            response_format = "json"
            if model_key == "dev":
                response_format = DEV_RESPONSE_SCHEMA
                system_instruction += (
                    "\n\nThe Ollama API wraps your answer in JSON. Return one object in the enforced "
                    "schema. Put only clean FLUX Dev visual prose in each prompt field and the "
                    "concise shot description in visual_beat. Do not place JSON, field names, "
                    "script labels, commentary, or markdown inside either string."
                )

            client = ollama.Client(host=self.ollama_host)
            response = client.chat(
                model=self.ollama_model,
                format=response_format,
                options={
                    "temperature": 0.6,
                    "top_p": 0.85,
                    "stop": ["\nScript Segment", "\nNarration:", "\nUser:"],
                },
                messages=[
                    {"role": "system", "content": system_instruction},
                    {
                        "role": "user",
                        "content": json.dumps({
                            "scene_id": int(scene["id"]),
                            "scene": scene["text"],
                            "maximum_visual_beats": int(profile.get("max_prompts_per_scene", 3)),
                            "requirements": profile.get("requirements", []),
                            "response_schema": {"prompts": [{"visual_beat": "string", "prompt": "string"}]},
                        }, ensure_ascii=False),
                    },
                ],
            )
            message = getattr(response, "message", None)
            content = getattr(message, "content", "") if message is not None else response["message"]["content"]
            payload = json.loads(content)
            limit = int(profile.get("max_prompts_per_scene", 3))
            prompts = []
            for item in payload.get("prompts", [])[:limit]:
                if not isinstance(item, dict):
                    continue
                clean_prompt = sanitize_generated_prompt(item.get("prompt", ""))
                if clean_prompt:
                    prompts.append({
                        "visual_beat": str(item.get("visual_beat", "")).strip() or str(scene["text"]),
                        "prompt": clean_prompt,
                    })
            return prompts
        except Exception:
            return []

    def _fallback(self, scene: Dict[str, Any], profile: Dict[str, Any]) -> List[Dict[str, str]]:
        builder = PromptBuilder(
            style_preset=str(profile.get("style_preset", "cinematic")),
            default_aspect_ratio=str(profile.get("aspect_ratio", "16:9")),
        )
        prompt = builder.build_prompt(scene)
        prompt = structure_prompt_for_model(prompt, MODEL_TYPES[profile["model_key"]],
                                            str(profile.get("style_preset", "cinematic")))
        return [{"visual_beat": str(scene["text"]), "prompt": prompt}]


def effective_prompt(entry: Dict[str, Any]) -> str:
    """Return the first usable manual or generated prompt from a model entry."""
    prompts = entry.get("prompts", []) if isinstance(entry, dict) else []
    for prompt in prompts:
        if isinstance(prompt, dict) and str(prompt.get("text", "")).strip():
            return str(prompt["text"]).strip()
    return ""