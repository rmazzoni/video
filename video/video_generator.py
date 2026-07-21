import os
import gc
from typing import Optional
from diffusers import StableVideoDiffusionPipeline
import torch
from PIL import Image
import gpu_registry

# Reduce CUDA memory fragmentation
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

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

        # Evict any previously loaded GPU model before loading this one
        gpu_registry.evict()

        # Load SVD model — keep on CPU initially, offload layers to GPU on demand
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

        # Register as the active GPU model
        gpu_registry.register(self)

    # ---------------------------------------------------------
    # PUBLIC API
    # ---------------------------------------------------------

    def generate_clip(
        self,
        image_path: str,
        scene_id: int,
        target_duration: Optional[float] = None,
        motion_bucket_id: Optional[int] = None,
        noise_aug_strength: Optional[float] = None,
        filename_suffix: str = "",
    ) -> str:
        """
        Generates a short video clip from a single image.
        motion_bucket_id and noise_aug_strength override the instance defaults
        when provided (useful for per-scene tuning).
        Returns the output video file path.
        """

        effective_motion = motion_bucket_id if motion_bucket_id is not None else self.motion_bucket_id
        effective_noise  = noise_aug_strength if noise_aug_strength is not None else self.noise_aug_strength

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
            motion_bucket_id=effective_motion,
            decode_chunk_size=self.decode_chunk_size,
            noise_aug_strength=effective_noise,
            generator=generator,
        )

        frames = result.frames[0]  # list of PIL images

        # Save as MP4
        output_path = os.path.join(self.output_dir, f"scene_{scene_id:03d}{filename_suffix}.mp4")
        self._save_frames_as_video(frames, output_path)

        # Free GPU memory before next clip
        del result, frames
        if self.device == "cuda":
            torch.cuda.empty_cache()
            gc.collect()

        # Pad the clip to match the dubbed audio duration (freeze last frame).
        if target_duration and target_duration > 0:
            self._pad_to_duration(output_path, target_duration)

        return output_path

    def unload(self) -> None:
        """Fully release VRAM: remove offload hooks, move every component to CPU, then delete."""
        if hasattr(self, "pipe") and self.pipe is not None:
            # 1. Remove accelerate CPU-offload hooks (they keep CUDA streams alive)
            try:
                from accelerate.hooks import remove_hook_from_module
                remove_hook_from_module(self.pipe, recurse=True)
            except Exception:
                pass

            # 2. Move each named sub-model to CPU explicitly
            for name in list(getattr(self.pipe, "components", {}).keys()):
                component = getattr(self.pipe, name, None)
                if component is not None and hasattr(component, "to"):
                    try:
                        component.to("cpu")
                    except Exception:
                        pass
                # Also delete the attribute so Python can GC the tensor data
                try:
                    setattr(self.pipe, name, None)
                except Exception:
                    pass

            try:
                self.pipe.to("cpu")
            except Exception:
                pass

            del self.pipe
            self.pipe = None

        gpu_registry.deregister()

        # 3. Force Python GC twice — first pass releases tensor wrappers,
        #    second pass catches cyclic references exposed by the first.
        gc.collect()
        gc.collect()

        if torch.cuda.is_available():
            torch.cuda.synchronize()   # wait for all pending CUDA kernels
            torch.cuda.empty_cache()   # release cached allocator blocks
            # A final collect after empty_cache can free any remaining
            # Python-held CUDA tensors that synchronize flushed.
            gc.collect()
            torch.cuda.empty_cache()

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

    def _pad_to_duration(self, video_path: str, target_duration: float) -> None:
        """
        Extend the clip to target_duration by freezing its last frame.
        Replaces the original file in-place.
        """
        import subprocess

        # Get actual clip duration
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            capture_output=True, text=True
        )
        try:
            clip_dur = float(probe.stdout.strip())
        except ValueError:
            return

        pad = round(target_duration - clip_dur, 3)
        if pad <= 0.05:
            return   # already long enough

        tmp = video_path + ".padded.mp4"
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", video_path,
             "-vf", f"tpad=stop_mode=clone:stop_duration={pad}",
             "-c:v", "libx264", "-preset", "fast", "-crf", "18",
             "-an", tmp],
            capture_output=True, text=True
        )
        if result.returncode == 0 and os.path.exists(tmp):
            os.replace(tmp, video_path)
        else:
            if os.path.exists(tmp):
                os.unlink(tmp)

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
