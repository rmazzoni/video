"""
Ken Burns effect clip generator.

Produces a video clip from a still image by applying a slow cinematic
pan and/or zoom, with a configurable duration. Uses only CPU/MoviePy —
no GPU required.
"""

import os
import random
from typing import Optional

import numpy as np
from PIL import Image


# Available motion styles: (zoom_start, zoom_end, pan_x, pan_y)
# pan values are fractions of the image width/height to shift across the clip
_MOTIONS = [
    {"name": "zoom_in",       "zoom_start": 1.0,  "zoom_end": 1.15, "pan_x": 0.0,  "pan_y": 0.0},
    {"name": "zoom_out",      "zoom_start": 1.15, "zoom_end": 1.0,  "pan_x": 0.0,  "pan_y": 0.0},
    {"name": "pan_right",     "zoom_start": 1.1,  "zoom_end": 1.1,  "pan_x": 0.05, "pan_y": 0.0},
    {"name": "pan_left",      "zoom_start": 1.1,  "zoom_end": 1.1,  "pan_x":-0.05, "pan_y": 0.0},
    {"name": "pan_up",        "zoom_start": 1.1,  "zoom_end": 1.1,  "pan_x": 0.0,  "pan_y":-0.04},
    {"name": "pan_down",      "zoom_start": 1.1,  "zoom_end": 1.1,  "pan_x": 0.0,  "pan_y": 0.04},
    {"name": "zoom_pan_right","zoom_start": 1.0,  "zoom_end": 1.12, "pan_x": 0.04, "pan_y": 0.0},
    {"name": "zoom_pan_left", "zoom_start": 1.0,  "zoom_end": 1.12, "pan_x":-0.04, "pan_y": 0.0},
]


class KenBurnsGenerator:
    """
    Generates Ken Burns-style video clips from still images.
    No GPU needed — uses MoviePy and NumPy only.
    """

    def __init__(
        self,
        output_dir: Optional[str] = None,
        fps: int = 24,
        duration: float = 4.0,
        seed: Optional[int] = None,
    ):
        """
        :param output_dir: where to save generated clips
        :param fps: frames per second
        :param duration: clip length in seconds
        :param seed: random seed for motion selection (None = random each time)
        """
        self.output_dir = output_dir
        self.fps = fps
        self.duration = duration
        self.seed = seed

        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

    # ---------------------------------------------------------
    # PUBLIC API
    # ---------------------------------------------------------

    def generate_clip(self, image_path: str, scene_id: int) -> str:
        """
        Generate a Ken Burns clip from a still image.
        Returns the output video file path.
        """
        from moviepy import ImageClip, VideoClip

        image = Image.open(image_path).convert("RGB")
        img_w, img_h = image.size
        img_array = np.array(image)

        rng = random.Random(self.seed if self.seed is not None else scene_id)
        motion = rng.choice(_MOTIONS)

        total_frames = int(self.fps * self.duration)
        out_w, out_h = self._output_size(img_w, img_h)

        zoom_start = motion["zoom_start"]
        zoom_end   = motion["zoom_end"]
        pan_x      = motion["pan_x"]
        pan_y      = motion["pan_y"]

        def make_frame(t: float) -> np.ndarray:
            progress = t / self.duration  # 0 → 1

            zoom = zoom_start + (zoom_end - zoom_start) * progress

            # Size of the crop window in the source image
            crop_w = int(out_w / zoom)
            crop_h = int(out_h / zoom)

            # Centre of the crop window, shifted by pan
            cx = img_w / 2 + pan_x * img_w * progress
            cy = img_h / 2 + pan_y * img_h * progress

            x1 = int(cx - crop_w / 2)
            y1 = int(cy - crop_h / 2)
            x1 = max(0, min(x1, img_w - crop_w))
            y1 = max(0, min(y1, img_h - crop_h))
            x2 = x1 + crop_w
            y2 = y1 + crop_h

            crop = img_array[y1:y2, x1:x2]
            resized = np.array(
                Image.fromarray(crop).resize((out_w, out_h), Image.LANCZOS)
            )
            return resized

        clip = VideoClip(make_frame, duration=self.duration)
        clip = clip.with_fps(self.fps)

        output_path = os.path.join(self.output_dir, f"scene_{scene_id:03d}.mp4")
        clip.write_videofile(
            output_path,
            codec="libx264",
            audio=False,
            logger=None,
            ffmpeg_params=["-crf", "18", "-preset", "fast"],
        )
        clip.close()
        return output_path

    # ---------------------------------------------------------
    # INTERNAL
    # ---------------------------------------------------------

    def _output_size(self, img_w: int, img_h: int):
        """Return (width, height) for the output video at 1920x1080 (or scaled to aspect ratio)."""
        aspect = img_w / img_h
        # Target 1920x1080 for 16:9; scale proportionally for other ratios
        target_w, target_h = 1920, 1080
        if abs(aspect - 16/9) < 0.05:          # 16:9
            out_w, out_h = 1920, 1080
        elif abs(aspect - 9/16) < 0.05:        # 9:16 portrait
            out_w, out_h = 1080, 1920
        elif abs(aspect - 1.0) < 0.05:         # 1:1
            out_w, out_h = 1080, 1080
        else:
            out_w = target_w
            out_h = int(out_w / aspect)
        # ensure even dimensions (required by libx264)
        out_w = out_w if out_w % 2 == 0 else out_w - 1
        out_h = out_h if out_h % 2 == 0 else out_h - 1
        return out_w, out_h
