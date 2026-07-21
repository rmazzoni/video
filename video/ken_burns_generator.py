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
    {"name": "zoom_in",       "zoom_start": 1.0,   "zoom_end": 1.08,  "pan_x": 0.0,   "pan_y": 0.0},
    {"name": "zoom_out",      "zoom_start": 1.08,  "zoom_end": 1.0,   "pan_x": 0.0,   "pan_y": 0.0},
    {"name": "pan_right",     "zoom_start": 1.05,  "zoom_end": 1.05,  "pan_x": 0.03,  "pan_y": 0.0},
    {"name": "pan_left",      "zoom_start": 1.05,  "zoom_end": 1.05,  "pan_x":-0.03,  "pan_y": 0.0},
    {"name": "pan_up",        "zoom_start": 1.05,  "zoom_end": 1.05,  "pan_x": 0.0,   "pan_y":-0.02},
    {"name": "pan_down",      "zoom_start": 1.05,  "zoom_end": 1.05,  "pan_x": 0.0,   "pan_y": 0.02},
    {"name": "zoom_pan_right","zoom_start": 1.0,   "zoom_end": 1.07,  "pan_x": 0.02,  "pan_y": 0.0},
    {"name": "zoom_pan_left", "zoom_start": 1.0,   "zoom_end": 1.07,  "pan_x":-0.02,  "pan_y": 0.0},
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
        motion_style: str = "auto",
    ):
        """
        :param output_dir: where to save generated clips
        :param fps: frames per second
        :param duration: clip length in seconds
        :param seed: random seed for motion selection (None = random each time)
        :param motion_style: "auto" = random pan/zoom, "static" = no motion
        """
        self.output_dir = output_dir
        self.fps = fps
        self.duration = duration
        self.seed = seed
        self.motion_style = motion_style

        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

    # ---------------------------------------------------------
    # PUBLIC API
    # ---------------------------------------------------------

    def generate_clip(self, image_path: str, scene_id: int, filename_suffix: str = "") -> str:
        """
        Generate a clip from a still image.
        In "static" mode the image is held perfectly still for the full duration.
        In "auto" mode a random pan/zoom motion is applied.
        Returns the output video file path.
        """
        from moviepy import VideoClip

        image = Image.open(image_path).convert("RGB")
        img_w, img_h = image.size
        img_array = np.array(image)
        out_w, out_h = self._output_size(img_w, img_h)

        if self.motion_style == "static":
            # Resize once; every frame is identical
            static_frame = np.array(
                Image.fromarray(img_array).resize((out_w, out_h), Image.LANCZOS)
            )

            def make_frame(_t: float) -> np.ndarray:
                return static_frame
        else:
            rng = random.Random(self.seed if self.seed is not None else scene_id)
            motion = rng.choice(_MOTIONS)

            zoom_start = motion["zoom_start"]
            zoom_end   = motion["zoom_end"]
            pan_x      = motion["pan_x"]
            pan_y      = motion["pan_y"]

            def _ease(t: float) -> float:
                return t * t * (3 - 2 * t)

            def make_frame(t: float) -> np.ndarray:
                progress = _ease(t / self.duration)
                zoom = zoom_start + (zoom_end - zoom_start) * progress
                crop_w = max(1.0, min(img_w / zoom, img_w))
                crop_h = max(1.0, min(img_h / zoom, img_h))
                cx = img_w / 2 + pan_x * img_w * progress
                cy = img_h / 2 + pan_y * img_h * progress
                x1 = max(0.0, min(cx - crop_w / 2, img_w - crop_w))
                y1 = max(0.0, min(cy - crop_h / 2, img_h - crop_h))
                xi, yi = round(x1), round(y1)
                cw, ch = round(crop_w), round(crop_h)
                xi = max(0, min(xi, img_w - cw))
                yi = max(0, min(yi, img_h - ch))
                crop = img_array[yi:yi+ch, xi:xi+cw]
                return np.array(
                    Image.fromarray(crop).resize((out_w, out_h), Image.LANCZOS)
                )

        clip = VideoClip(make_frame, duration=self.duration)
        clip = clip.with_fps(self.fps)

        output_path = os.path.join(self.output_dir, f"scene_{scene_id:03d}{filename_suffix}.mp4")
        try:
            clip.write_videofile(
                output_path,
                codec="libx264",
                audio=False,
                logger=None,
                ffmpeg_params=["-crf", "14", "-preset", "slow", "-tune", "film"],
            )
        finally:
            clip.close()
            del clip
            del img_array

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
