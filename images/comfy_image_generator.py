"""Native ComfyUI image generation for the VID pipeline.

ComfyUI is the GPU render backend. Prompt lock stays in prompts/.
"""

import os
import tempfile
from typing import Callable, Dict, Optional

import yaml

from comfy_bridge.client import ComfyClient
from comfy_bridge.graphs import (
    WORKFLOWS,
    leftover_placeholders,
    params_for_spec,
    spec_for_model,
)

# Re-export for callers that still import WORKFLOWS from here.
__all__ = ["ComfyImageGenerator", "WORKFLOWS"]


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
        sampler: str = "euler",
        scheduler: str = "normal",
        shift: float = 3.0,
        timeout: float = 900.0,
    ):
        self.spec = spec_for_model(model_type)
        self.source_dir = source_dir
        self.model_type = model_type
        self.output_dir = output_dir
        self.width = width
        self.height = height
        self.steps = steps
        self.guidance = guidance
        self.seed = seed
        self.sampler = sampler
        self.scheduler = scheduler
        self.shift = shift
        self.timeout = timeout

        with open(os.path.join(source_dir, "config", "comfy.yaml"), "r", encoding="utf-8") as handle:
            config = yaml.safe_load(handle) or {}
        self.client = ComfyClient(
            host=str(config.get("host", "127.0.0.1")),
            port=int(config.get("port", 8188)),
        )
        workflow_path = os.path.join(source_dir, "workflows", self.spec.filename)
        self.workflow = self.client.load_workflow(workflow_path)
        declared = leftover_placeholders(self.workflow)
        extra = declared - self.spec.params
        missing = self.spec.params - declared
        if extra or missing:
            parts = []
            if extra:
                parts.append("graph-only " + ", ".join(f"@{key}" for key in sorted(extra)))
            if missing:
                parts.append("spec-only " + ", ".join(f"@{key}" for key in sorted(missing)))
            raise ValueError(
                f"{self.spec.filename} does not match the product still contract: "
                + "; ".join(parts)
            )
        os.makedirs(output_dir, exist_ok=True)

    def _validate_required_models(self) -> None:
        if not self.spec.requirements:
            return
        display_name = self.spec.display_name
        object_info = self.client.get_object_info()
        missing = []
        for node_name, input_name, filename, folder in self.spec.requirements:
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
            raise ConnectionError(
                f"ComfyUI is not running at {self.client.host}:{self.client.port}. "
                "Start the app with launch_with_comfy.py so the render server is up "
                "before generating stills."
            )
        self._validate_required_models()
        # Clear any stuck/leftover job from a previous (cancelled or timed-out) generation
        # so it can't block this one from ever showing up in /history.
        self.client.reset_stale_state()
        from prompts.prompt_builder import structure_prompt_for_model
        prompt = structure_prompt_for_model(prompt, self.model_type)
        active_seed = self.seed if seed_override is None else seed_override
        prefix = f"vid/{self.model_type}/scene_{scene_id:03d}{filename_suffix}"
        available: Dict[str, object] = {
            "prompt": prompt,
            "seed": active_seed,
            "width": self.width,
            "height": self.height,
            "steps": self.steps,
            "guidance": self.guidance,
            "sampler": self.sampler,
            "scheduler": self.scheduler,
            "shift": self.shift,
            "filename_prefix": prefix,
        }
        params = params_for_spec(self.spec, available)
        prompt_id = self.client.execute_workflow(self.workflow, params, strict=True)
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
