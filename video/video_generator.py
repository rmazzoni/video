import os
from typing import Optional
from diffusers import StableVideoDiffusionPipeline
import torch
from PIL import Image


class VideoGenerator:
    """
    Generates short video clips from images using Stable Video Diffusion (SVD).
    """

    def __init__(
        self,
        model_path: str,
        device: Optional[str] = None,
        output_dir: Optional[str] = None,
        num_frames: int = 14,
        motion_bucket_id: int = 127,
        fps: int = 8,
        seed: Optional[int] = None,
    ):
        """
        :param model_path: path to local SVD model
        :param device: "cuda" or "cpu"
        :param output_dir: where to save generated clips
        :param num_frames: number of frames per clip (SVD default: 14)
        :param motion_bucket_id: controls motion intensity (0–255)
        :param fps: frames per second for output video
        :param seed: optional seed for reproducibility
        """
        self.model_path = model_path
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.output_dir = output_dir
        self.num_frames = num_frames
        self.motion_bucket_id = motion_bucket_id
        self.fps = fps
        self.seed = seed

        # Load SVD model
        self.pipe = StableVideoDiffusionPipeline.from_pretrained(
            self.model_path,
            torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
        ).to(self.device)

        if self.output_dir:
            os.makedirs(self.output_dir, exist_ok=True)

    # ---------------------------------------------------------
    # PUBLIC API
    # ---------------------------------------------------------

    def generate_clip(self, image_path: str, scene_id: int) -> str:
        """
        Generates a short video clip from a single image.
        Returns the output video file path.
        """

        # Load image
        image = Image.open(image_path).convert("RGB")

        # Optional seed
        generator = None
        if self.seed is not None:
            generator = torch.Generator(device=self.device).manual_seed(self.seed)

        # Run SVD
        result = self.pipe(
            image,
            num_frames=self.num_frames,
            motion_bucket_id=self.motion_bucket_id,
            generator=generator,
        )

        frames = result.frames[0]  # list of PIL images

        # Save as MP4
        output_path = os.path.join(self.output_dir, f"scene_{scene_id:03d}.mp4")
        self._save_frames_as_video(frames, output_path)

        return output_path

    # ---------------------------------------------------------
    # INTERNAL HELPERS
    # ---------------------------------------------------------

    def _save_frames_as_video(self, frames, output_path: str):
        """
        Saves a list of PIL frames as an MP4 video using imageio.
        """
        import imageio

        writer = imageio.get_writer(output_path, fps=self.fps)
        for frame in frames:
            writer.append_data(frame)
        writer.close()

    # ---------------------------------------------------------
    # BATCH GENERATION
    # ---------------------------------------------------------

    def generate_batch(self, image_dir: str) -> None:
        """
        Generates video clips for all images in a directory.
        """
        for filename in sorted(os.listdir(image_dir)):
            if filename.lower().endswith((".png", ".jpg", ".jpeg")):
                scene_id = int(filename.split("_")[1].split(".")[0])
                image_path = os.path.join(image_dir, filename)
                print(f"Generating video clip for scene {scene_id}...")
                self.generate_clip(image_path, scene_id)
