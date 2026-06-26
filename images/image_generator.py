import os
from typing import Optional
from diffusers import StableDiffusionXLPipeline
import torch
from PIL import Image


class ImageGenerator:
    """
    Generates images from prompts using a local Stable Diffusion model.
    """

    def __init__(
        self,
        model_path: str,
        device: Optional[str] = None,
        output_dir: Optional[str] = None,
        guidance_scale: float = 7.5,
        num_inference_steps: int = 30,
        seed: Optional[int] = None,
        width: int = 1024,
        height: int = 576,
    ):
        """
        :param model_path: path to the local SD3 or Flux model
        :param device: "cuda" or "cpu"
        :param output_dir: where to save generated images
        :param guidance_scale: classifier-free guidance
        :param num_inference_steps: diffusion steps
        :param seed: optional seed for reproducibility
        :param width: output image width in pixels
        :param height: output image height in pixels
        """
        self.model_path = model_path
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.output_dir = output_dir
        self.guidance_scale = guidance_scale
        self.num_inference_steps = num_inference_steps
        self.seed = seed
        self.width = width
        self.height = height

        # Load model
        self.pipe = StableDiffusionXLPipeline.from_pretrained(
            self.model_path,
            torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
        ).to(self.device)

        # Create output directory if needed
        if self.output_dir:
            os.makedirs(self.output_dir, exist_ok=True)

    # ---------------------------------------------------------
    # PUBLIC API
    # ---------------------------------------------------------

    def generate_image(self, prompt: str, scene_id: int) -> Image.Image:
        """
        Generates a single image from a prompt.
        Returns a PIL Image object.
        """
        generator = None
        if self.seed is not None:
            generator = torch.Generator(device=self.device).manual_seed(self.seed)

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