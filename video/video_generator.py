import os
import gc
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
        decode_chunk_size: int = 4,
        noise_aug_strength: float = 0.02,
    ):
        """
        :param model_path: path to local SVD model
        :param device: "cuda" or "cpu"
        :param output_dir: where to save generated clips
        :param num_frames: number of frames per clip (SVD default: 14)
        :param motion_bucket_id: controls motion intensity (0–255)
        :param fps: frames per second for output video
        :param seed: optional seed for reproducibility
        :param noise_aug_strength: how far the video may drift from the input
            image (lower = fewer hallucinations, steadier motion)
        """
        self.model_path = model_path
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.output_dir = output_dir
        self.num_frames = num_frames
        self.motion_bucket_id = motion_bucket_id
        self.fps = fps
        self.seed = seed
        self.decode_chunk_size = decode_chunk_size
        self.noise_aug_strength = noise_aug_strength

        # Load SVD model — keep on CPU initially, offload layers to GPU on demand
        # so the full model weight (~8 GB) never sits entirely on the GPU at once.
        self.pipe = StableVideoDiffusionPipeline.from_pretrained(
            self.model_path,
            torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
        )
        if self.device == "cuda":
            self.pipe.enable_model_cpu_offload()
            self.pipe.enable_attention_slicing()
        else:
            self.pipe = self.pipe.to(self.device)

        if self.output_dir:
            os.makedirs(self.output_dir, exist_ok=True)

    # ---------------------------------------------------------
    # PUBLIC API
    # ---------------------------------------------------------

    def generate_clip(self, image_path: str, scene_id: int, target_duration: Optional[float] = None) -> str:
        """
        Generates a short video clip from a single image.
        If target_duration is given, the clip is retimed (sped up or slowed
        down) so its playback length matches that duration in seconds.
        Returns the output video file path.
        """

        # Load image
        image = Image.open(image_path).convert("RGB")

        # Optional seed
        generator = None
        if self.seed is not None:
            generator = torch.Generator(device=self.device).manual_seed(self.seed)

        # Free any leftover VRAM from the previous clip before starting.
        if self.device == "cuda":
            torch.cuda.empty_cache()
            gc.collect()

        # Run SVD. decode_chunk_size limits how many frames are VAE-decoded at
        # once, which is the main cause of out-of-memory on 16 GB GPUs.
        result = self.pipe(
            image,
            num_frames=self.num_frames,
            motion_bucket_id=self.motion_bucket_id,
            decode_chunk_size=self.decode_chunk_size,
            noise_aug_strength=self.noise_aug_strength,
            generator=generator,
        )

        frames = result.frames[0]  # list of PIL images

        # Save as MP4
        output_path = os.path.join(self.output_dir, f"scene_{scene_id:03d}.mp4")
        self._save_frames_as_video(frames, output_path)

        # Free GPU memory before next clip
        del result, frames
        if self.device == "cuda":
            torch.cuda.empty_cache()
            gc.collect()

        # Retime the clip to match the narration duration for this scene.
        if target_duration and target_duration > 0:
            self._retime_video(output_path, target_duration)

        return output_path

    # ---------------------------------------------------------
    # INTERNAL HELPERS
    # ---------------------------------------------------------

    def _save_frames_as_video(self, frames, output_path: str):
        """
        Saves a list of PIL frames as an MP4 video using imageio.
        """
        import imageio
        import numpy as np

        writer = imageio.get_writer(output_path, fps=self.fps)
        for frame in frames:
            if not isinstance(frame, np.ndarray):
                frame = np.array(frame)
            writer.append_data(frame)
        writer.close()

    def _retime_video(self, video_path: str, target_duration: float) -> None:
        """
        Re-encode the given clip so its total playback length equals
        target_duration seconds, using ffmpeg's setpts filter. The motion is
        slowed down or sped up to fill the whole scene narration, avoiding the
        last-frame freeze used during final assembly.
        """
        import subprocess

        native_duration = self.num_frames / float(self.fps)
        if native_duration <= 0:
            return
        factor = target_duration / native_duration
        # Skip negligible changes to avoid a pointless re-encode.
        if abs(factor - 1.0) < 0.02:
            return

        tmp_path = video_path + ".retimed.mp4"
        # Use a smooth output frame rate so the stretched clip plays evenly.
        out_fps = max(int(round(self.num_frames / target_duration)), 24)
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-filter:v", f"setpts={factor:.6f}*PTS",
            "-r", str(out_fps),
            "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            tmp_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            # Leave the original clip in place if retiming fails.
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise RuntimeError(f"ffmpeg retime failed:\n{result.stderr[-2000:]}")
        os.replace(tmp_path, video_path)

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
