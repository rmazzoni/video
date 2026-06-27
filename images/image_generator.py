import os
import gc
from typing import Optional
import torch
from PIL import Image

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

        dtype = torch.bfloat16 if self.device == "cuda" else torch.float32

        if self.model_type.startswith("flux"):
            from diffusers import FluxPipeline
            self.pipe = FluxPipeline.from_pretrained(
                self.model_path,
                torch_dtype=dtype,
            ).to(self.device)
            # Enable memory efficient attention for large images
            if hasattr(self.pipe, "enable_model_cpu_offload") and self.device == "cuda":
                pass  # 24 GB can hold it all; skip offload for speed
        else:
            from diffusers import StableDiffusionXLPipeline
            self.pipe = StableDiffusionXLPipeline.from_pretrained(
                self.model_path,
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
            ).to(self.device)

        if self.output_dir:
            os.makedirs(self.output_dir, exist_ok=True)

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