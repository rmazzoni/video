"""Native ComfyUI image generation for the VID pipeline."""

import os
import tempfile
from typing import Callable, Dict, Optional

import yaml

from comfy_bridge.client import ComfyClient


WORKFLOWS = {
    "flux-schnell": "flux1_schnell_image.json",
    "flux-dev": "flux1_dev_image.json",
    "flux2": "flux2_image.json",
}


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

    def generate_image(
        self,
        prompt: str,
        scene_id: int,
        seed_override: Optional[int] = None,
        filename_suffix: str = "",
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> str:
        if not self.client.is_alive():
            raise ConnectionError("ComfyUI is not running or is not reachable.")
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
        result = self.client.wait_for_result(prompt_id, timeout=self.timeout, cancel_check=cancel_check)
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
        """ComfyUI owns model lifetime; retained for the pipeline generator contract."""
