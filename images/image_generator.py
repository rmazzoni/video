import os
import gc
from typing import Optional
import torch
from PIL import Image
import gpu_registry

# Reduce CUDA memory fragmentation
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

# Supported model types
MODEL_TYPES = {
    "sdxl":          "Stable Diffusion XL",
    "flux-dev":      "FLUX.1-dev  (best quality, ~24 GB)",
    "flux-schnell":  "FLUX.1-schnell  (fast, 4 steps)",
}


class ImageGenerator:
    """
    Generates images from prompts.
    Supports SDXL, FLUX.1-dev and FLUX.1-schnell.
    """

    def __init__(
        self,
        model_path: str,
        model_type: str = "sdxl",
        device: Optional[str] = None,
        output_dir: Optional[str] = None,
        guidance_scale: float = 7.5,
        num_inference_steps: int = 30,
        seed: Optional[int] = None,
        width: int = 1344,
        height: int = 768,
        enable_cpu_offload: Optional[bool] = None,
    ):
        self.model_path = model_path
        self.model_type = model_type.lower()
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.output_dir = output_dir
        self.guidance_scale = guidance_scale
        self.num_inference_steps = num_inference_steps
        self.seed = seed
        self.width = width
        self.height = height

        # Enable CPU offload for all FLUX models on CUDA — the transformer alone
        # is ~24 GiB in bfloat16 which exceeds 16 GiB GPUs without offloading.
        if enable_cpu_offload is None:
            enable_cpu_offload = self.model_type.startswith("flux") and self.device == "cuda"
        self.enable_cpu_offload = enable_cpu_offload

        dtype = torch.bfloat16 if self.device == "cuda" else torch.float32

        # Evict any previously loaded GPU model before loading this one
        gpu_registry.evict()

        if not os.path.isdir(self.model_path):
            raise FileNotFoundError(
                f"Model directory not found: '{self.model_path}'. "
                f"The '{self.model_type}' model has not been downloaded. "
                f"Download it into this folder or choose a different image model in Settings."
            )

        if self.model_type.startswith("flux"):
            from diffusers import FluxPipeline
            self.pipe = FluxPipeline.from_pretrained(
                self.model_path,
                torch_dtype=dtype,
            )
            if self.device == "cuda":
                if self.enable_cpu_offload:
                    # sequential_cpu_offload moves one layer at a time to GPU (~1 GiB peak)
                    # vs model_cpu_offload which moves the whole transformer (~24 GiB peak).
                    self.pipe.enable_sequential_cpu_offload()
                else:
                    self.pipe.to(self.device)
                # Slice attention to reduce per-operation VRAM further
                try:
                    self.pipe.enable_attention_slicing(1)
                except Exception:
                    pass
                # Reduce VAE memory during high-resolution decode.
                self.pipe.vae.enable_tiling()
                self.pipe.vae.enable_slicing()
            else:
                self.pipe.to(self.device)
        else:
            from diffusers import StableDiffusionXLPipeline
            self.pipe = StableDiffusionXLPipeline.from_pretrained(
                self.model_path,
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
            )
            if self.device == "cuda":
                self.pipe.enable_model_cpu_offload()
                try:
                    self.pipe.enable_attention_slicing(1)
                except Exception:
                    pass

        if self.output_dir:
            os.makedirs(self.output_dir, exist_ok=True)

        # Register as the active GPU model
        gpu_registry.register(self)

    # ---------------------------------------------------------
    # PUBLIC API
    # ---------------------------------------------------------

    def generate_image(self, prompt: str, scene_id: int) -> Image.Image:
        generator = None
        if self.seed is not None:
            generator = torch.Generator(device=self.device).manual_seed(self.seed)

        if self.model_type.startswith("flux"):
            # FLUX.1: no negative_prompt; guidance_scale=0 for schnell, ~3.5 for dev
            gs = 0.0 if self.model_type == "flux-schnell" else self.guidance_scale
            result = self.pipe(
                prompt,
                guidance_scale=gs,
                num_inference_steps=self.num_inference_steps,
                width=self.width,
                height=self.height,
                generator=generator,
                max_sequence_length=512,
            )
        else:
            result = self.pipe(
                prompt,
                guidance_scale=self.guidance_scale,
                num_inference_steps=self.num_inference_steps,
                width=self.width,
                height=self.height,
                generator=generator,
            )
        image = result.images[0]

        if self.output_dir:
            output_path = os.path.join(self.output_dir, f"scene_{scene_id:03d}.png")
            image.save(output_path)

        # Free intermediate CUDA tensors between generations
        if self.device == "cuda":
            torch.cuda.empty_cache()
            gc.collect()

        return image

    def unload(self) -> None:
        """Fully release VRAM: remove offload hooks, move every component to CPU, then delete."""
        if hasattr(self, "pipe") and self.pipe is not None:
            try:
                from accelerate.hooks import remove_hook_from_module
                remove_hook_from_module(self.pipe, recurse=True)
            except Exception:
                pass
            # Move each named component to CPU individually
            for name in getattr(self.pipe, "components", {}):
                component = getattr(self.pipe, name, None)
                if component is not None and hasattr(component, "to"):
                    try:
                        component.to("cpu")
                    except Exception:
                        pass
            # Move any remaining parameters/buffers
            try:
                self.pipe.to("cpu")
            except Exception:
                pass
            del self.pipe
            self.pipe = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
            gc.collect()  # second pass after cache clear

    # ---------------------------------------------------------
    # BATCH GENERATION
    # ---------------------------------------------------------

    def generate_batch(self, scenes, prompt_builder) -> None:
        """
        Generates images for all scenes using a PromptBuilder instance.
        """
        for scene in scenes:
            scene_id = int(scene["id"])
            prompt = prompt_builder.build_prompt(scene)
            print(f"Generating image for scene {scene_id}...")
            self.generate_image(prompt, scene_id)