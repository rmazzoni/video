"""ComfyUI nodes that expose the VID pipeline stages."""

import os
from typing import Any, Dict, Tuple

import yaml


STAGES = (
    "narration",
    "scenes",
    "prompts",
    "tts",
    "preview_images",
    "preview_clips",
    "preview_video",
    "final_images",
    "final_clips",
    "final_video",
)


def _run_stage(config: Dict[str, Any], stage: str) -> str:
    source_dir = os.path.abspath(config["source_dir"])
    if source_dir not in os.sys.path:
        os.sys.path.insert(0, source_dir)

    from ui.pipeline_controller import PipelineController, PipelineWorker

    settings = dict(PipelineController.DEFAULT_SETTINGS)
    settings_path = os.path.join(source_dir, "config", "settings.yaml")
    if os.path.isfile(settings_path):
        with open(settings_path, "r", encoding="utf-8") as handle:
            settings.update(yaml.safe_load(handle) or {})
    settings.update(config["overrides"])

    result: Dict[str, Any] = {}
    worker = PipelineWorker(
        project_path=os.path.abspath(config["project_path"]),
        config=settings,
        root_dir=os.path.dirname(source_dir),
        stage=stage,
    )
    worker.log.connect(lambda message: print(f"[VID:{stage}] {message}"))
    worker.finished.connect(
        lambda success, payload: result.update(success=success, payload=payload)
    )
    worker.run()
    if not result.get("success"):
        raise RuntimeError(result.get("payload") or f"VID stage failed: {stage}")
    return str(result.get("payload", ""))


class VIDPipelineConfig:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "project_path": ("STRING", {"default": "F:/VID/projects/project"}),
                "source_dir": ("STRING", {"default": "F:/VID/src"}),
                "prompt_profiles_dir": ("STRING", {"default": "F:/VID/src/config/prompt_profiles"}),
                "ollama_model": ("STRING", {"default": "qwen3:8b"}),
                "ollama_host": ("STRING", {"default": "http://localhost:11434"}),
                "max_visual_beats": ("INT", {"default": 3, "min": 1, "max": 8}),
                "style_preset": ("STRING", {"default": "cinematic"}),
                "aspect_ratio": (["16:9", "4:3", "1:1", "9:16"],),
                "scene_split_method": (["paragraph", "sentence"],),
                "min_sentence_length": ("INT", {"default": 20, "min": 1}),
                "seed": ("INT", {"default": 42, "min": 0, "max": 0xffffffffffffffff}),
                "image_width": ("INT", {"default": 1344, "min": 64, "step": 8}),
                "image_height": ("INT", {"default": 768, "min": 64, "step": 8}),
                "schnell_steps": ("INT", {"default": 4, "min": 1, "max": 100}),
                "schnell_guidance": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 20.0, "step": 0.1}),
                "dev_steps": ("INT", {"default": 20, "min": 1, "max": 100}),
                "dev_guidance": ("FLOAT", {"default": 3.5, "min": 0.0, "max": 20.0, "step": 0.1}),
                "flux2_steps": ("INT", {"default": 4, "min": 1, "max": 100}),
                "flux2_guidance": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 20.0, "step": 0.1}),
                "clip_engine": (["ken_burns", "svd"],),
                "ken_burns_motion": (["static", "auto", "zoom_in", "zoom_out", "pan_left", "pan_right"],),
                "fps": ("INT", {"default": 8, "min": 1, "max": 120}),
                "num_frames": ("INT", {"default": 14, "min": 1}),
                "motion_bucket_id": ("INT", {"default": 127, "min": 1, "max": 255}),
                "tts_voice": ("STRING", {"default": "it-IT-DiegoNeural"}),
                "tts_rate": ("STRING", {"default": "+0%"}),
                "tts_pitch": ("STRING", {"default": "+0Hz"}),
                "tts_volume": ("STRING", {"default": "+0%"}),
                "output_width": ("INT", {"default": 1920, "min": 64, "step": 8}),
                "output_height": ("INT", {"default": 1080, "min": 64, "step": 8}),
                "audio_volume": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 4.0, "step": 0.05}),
                "fade_in": ("FLOAT", {"default": 0.0, "min": 0.0, "step": 0.1}),
                "fade_out": ("FLOAT", {"default": 0.0, "min": 0.0, "step": 0.1}),
            }
        }

    RETURN_TYPES = ("VID_PIPELINE_CONFIG",)
    RETURN_NAMES = ("config",)
    FUNCTION = "build"
    CATEGORY = "VID Pipeline"

    def build(self, project_path: str, source_dir: str, **overrides) -> Tuple[Dict[str, Any]]:
        return ({
            "project_path": project_path,
            "source_dir": source_dir,
            "overrides": overrides,
        },)


class VIDPipelineStage:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "config": ("VID_PIPELINE_CONFIG",),
                "stage": (STAGES,),
            },
            "optional": {"previous": ("VID_PIPELINE_STATE",)},
        }

    RETURN_TYPES = ("VID_PIPELINE_STATE",)
    RETURN_NAMES = ("state",)
    FUNCTION = "run"
    CATEGORY = "VID Pipeline"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def run(self, config: Dict[str, Any], stage: str, previous=None):
        if stage not in STAGES:
            raise ValueError(f"Unknown VID pipeline stage: {stage}")
        payload = _run_stage(config, stage)
        return ({"stage": stage, "payload": payload, "previous": previous},)


class VIDPipelineOutput:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"state": ("VID_PIPELINE_STATE",)}}

    RETURN_TYPES = ()
    FUNCTION = "finish"
    OUTPUT_NODE = True
    CATEGORY = "VID Pipeline"

    def finish(self, state):
        print(f"[VID] Pipeline complete: {state.get('payload', '')}")
        return {}


NODE_CLASS_MAPPINGS = {
    "VIDPipelineConfig": VIDPipelineConfig,
    "VIDPipelineStage": VIDPipelineStage,
    "VIDPipelineOutput": VIDPipelineOutput,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "VIDPipelineConfig": "VID Pipeline Settings",
    "VIDPipelineStage": "VID Pipeline Stage",
    "VIDPipelineOutput": "VID Pipeline Output",
}