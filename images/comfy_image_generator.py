"""Native ComfyUI image generation for the VID pipeline."""

import os
import tempfile
from typing import Callable, Dict, Optional

import yaml

from comfy_bridge.client import ComfyClient


WORKFLOWS = {
    "flux-schnell": "flux1_schnell_image.json",
    "zimage-turbo": "zimage_turbo_image.json",
    "flux-dev": "flux1_dev_image.json",
    "hidream-dev": "hidream_i1_dev_image.json",
    "flux2": "flux2_image.json",
}

ZIMAGE_REQUIREMENTS = (
    ("UNETLoader", "unet_name", "z_image_turbo_bf16.safetensors", "models/diffusion_models"),
    ("CLIPLoader", "clip_name", "qwen_3_4b.safetensors", "models/text_encoders"),
    ("VAELoader", "vae_name", "ae.safetensors", "models/vae"),
)

HIDREAM_REQUIREMENTS = (
    ("UNETLoader", "unet_name", "hidream_i1_dev_fp8.safetensors", "models/diffusion_models"),
    ("QuadrupleCLIPLoader", "clip_name1", "clip_l_hidream.safetensors", "models/text_encoders"),
    ("QuadrupleCLIPLoader", "clip_name2", "clip_g_hidream.safetensors", "models/text_encoders"),
    ("QuadrupleCLIPLoader", "clip_name3", "t5xxl_fp8_e4m3fn_scaled.safetensors", "models/text_encoders"),
    ("QuadrupleCLIPLoader", "clip_name4", "llama_3.1_8b_instruct_fp8_scaled.safetensors", "models/text_encoders"),
    ("VAELoader", "vae_name", "ae.safetensors", "models/vae"),
)


class ComfyImageGenerator:
    def __init__(
        self,
        source_dir: str,
        model_type: str,
        output_dir: str,
        width: int,
        height: int,
        steps: int,
        guidance: float,
        seed: int,
        timeout: float = 900.0,
    ):
        if model_type not in WORKFLOWS:
            raise ValueError(f"Unsupported ComfyUI image model: {model_type}")
        self.source_dir = source_dir
        self.model_type = model_type
        self.output_dir = output_dir
        self.width = width
        self.height = height
        self.steps = steps
        self.guidance = guidance
        self.seed = seed
        self.timeout = timeout

        with open(os.path.join(source_dir, "config", "comfy.yaml"), "r", encoding="utf-8") as handle:
            config = yaml.safe_load(handle) or {}
        self.client = ComfyClient(
            host=str(config.get("host", "127.0.0.1")),
            port=int(config.get("port", 8188)),
        )
        workflow_path = os.path.join(source_dir, "workflows", WORKFLOWS[model_type])
        self.workflow = self.client.load_workflow(workflow_path)
        os.makedirs(output_dir, exist_ok=True)

    def _validate_required_models(self) -> None:
        requirements = {
            "zimage-turbo": ("Z-Image Turbo", ZIMAGE_REQUIREMENTS),
            "hidream-dev": ("HiDream-I1 Dev", HIDREAM_REQUIREMENTS),
        }.get(self.model_type)
        if requirements is None:
            return
        display_name, model_requirements = requirements
        object_info = self.client.get_object_info()
        missing = []
        for node_name, input_name, filename, folder in model_requirements:
            try:
                input_spec = object_info[node_name]["input"]["required"][input_name]
                if input_spec[0] == "COMBO":
                    available = input_spec[1].get("options", [])
                else:
                    available = input_spec[0]
            except (KeyError, IndexError, TypeError):
                available = []
            if filename not in available:
                missing.append(f"{filename} -> ComfyUI/{folder}/")
        if missing:
            raise FileNotFoundError(
                f"{display_name} is enabled but required ComfyUI model files are missing:\n"
                + "\n".join(f"- {item}" for item in missing)
                + "\nInstall the files, then restart or refresh ComfyUI before retrying."
            )

    def generate_image(
        self,
        prompt: str,
        scene_id: int,
        seed_override: Optional[int] = None,
        filename_suffix: str = "",
        cancel_check: Optional[Callable[[], bool]] = None,
        wait_callback: Optional[Callable[[float], None]] = None,
    ) -> str:
        if not self.client.is_alive():
            raise ConnectionError("ComfyUI is not running or is not reachable.")
        self._validate_required_models()
        # Clear any stuck/leftover job from a previous (cancelled or timed-out) generation
        # so it can't block this one from ever showing up in /history.
        self.client.reset_stale_state()
        active_seed = self.seed if seed_override is None else seed_override
        prefix = f"vid/{self.model_type}/scene_{scene_id:03d}{filename_suffix}"
        params: Dict[str, object] = {
            "prompt": prompt,
            "seed": active_seed,
            "width": self.width,
            "height": self.height,
            "steps": self.steps,
            "guidance": self.guidance,
            "filename_prefix": prefix,
        }
        prompt_id = self.client.execute_workflow(self.workflow, params)
        result = self.client.wait_for_result(
            prompt_id,
            timeout=self.timeout,
            cancel_check=cancel_check,
            wait_callback=wait_callback,
        )
        status = result.get("status", {})
        if status.get("status_str") == "error" or not status.get("completed", True):
            messages = status.get("messages", [])
            raise RuntimeError(f"ComfyUI image workflow failed: {messages or status}")
        images = result.get("images", [])
        if not images:
            raise RuntimeError("ComfyUI image workflow completed without an image output.")

        image = images[-1]
        content = self.client.get_image(
            filename=image["filename"],
            subfolder=image.get("subfolder", ""),
            folder_type=image.get("type", "output"),
        )
        destination = os.path.join(
            self.output_dir, f"scene_{scene_id:03d}{filename_suffix}.png")
        handle, temporary = tempfile.mkstemp(suffix=".png", dir=self.output_dir)
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(content)
            if not content:
                raise RuntimeError("ComfyUI returned an empty image file.")
            os.replace(temporary, destination)
        except Exception:
            if os.path.exists(temporary):
                os.remove(temporary)
            raise
        return destination

    def unload(self) -> None:
        """Unload models and cached tensors owned by the external ComfyUI process."""
        try:
            self.client.free_memory(unload_models=True)
        except Exception:
            pass
