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
    {"name": "zoom_in",       "zoom_start": 1.0,   "zoom_end": 1.35,  "pan_x": 0.0,   "pan_y": 0.0},
    {"name": "zoom_out",      "zoom_start": 1.35,  "zoom_end": 1.0,   "pan_x": 0.0,   "pan_y": 0.0},
    {"name": "pan_right",     "zoom_start": 1.15,  "zoom_end": 1.15,  "pan_x": 0.08,  "pan_y": 0.0},
    {"name": "pan_left",      "zoom_start": 1.15,  "zoom_end": 1.15,  "pan_x":-0.08,  "pan_y": 0.0},
    {"name": "zoom_pan_right","zoom_start": 1.0,   "zoom_end": 1.25,  "pan_x": 0.07,  "pan_y": 0.0},
    {"name": "zoom_pan_left", "zoom_start": 1.0,   "zoom_end": 1.25,  "pan_x":-0.07,  "pan_y": 0.0},
    {"name": "zoom_out_right","zoom_start": 1.35,  "zoom_end": 1.0,   "pan_x": 0.06,  "pan_y": 0.0},
    {"name": "zoom_out_left", "zoom_start": 1.35,  "zoom_end": 1.0,   "pan_x":-0.06,  "pan_y": 0.0},
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
            # For a perfectly still clip bypass MoviePy entirely and ask ffmpeg
            # to loop a single JPEG frame.  There are zero inter-frames, so
            # there is no motion estimation, no deblocking smear and no codec
            # shimmer — the image is bit-identical across the whole clip.
            import subprocess, tempfile as _tf
            still = Image.fromarray(img_array).resize((out_w, out_h), Image.LANCZOS)
            with _tf.NamedTemporaryFile(suffix=".jpg", delete=False) as _tmp:
                tmp_path = _tmp.name
            try:
                still.save(tmp_path, "JPEG", quality=95)
                output_path = os.path.join(
                    self.output_dir, f"scene_{scene_id:03d}{filename_suffix}.mp4"
                )
                subprocess.run(
                    [
                        "ffmpeg", "-y",
                        "-loop", "1",
                        "-i", tmp_path,
                        "-t", str(round(self.duration, 3)),
                        "-c:v", "libx264",
                        "-tune", "stillimage",
                        "-crf", "12",
                        "-preset", "slow",
                        "-pix_fmt", "yuv420p",
                        "-r", str(self.fps),
                        output_path,
                    ],
                    check=True,
                    capture_output=True,
                )
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
            del img_array
            return output_path

        # ── Animated (auto) mode — ffmpeg zoompan filter ─────────────────────
        # Mix global seed with scene_id so each scene gets a different motion
        rng = random.Random((self.seed if self.seed is not None else 0) ^ (scene_id * 2654435761))
        motion = rng.choice(_MOTIONS)

        zoom_start = motion["zoom_start"]
        zoom_end   = motion["zoom_end"]
        pan_x      = motion["pan_x"]
        pan_y      = motion["pan_y"]

        import subprocess, tempfile as _tf

        out_w, out_h = self._output_size(img_w, img_h)
        # Save still as temp JPEG (same as static branch)
        still = Image.fromarray(img_array).resize((out_w, out_h), Image.LANCZOS)
        with _tf.NamedTemporaryFile(suffix=".jpg", delete=False) as _tmp:
            tmp_path = _tmp.name
        output_path = os.path.join(self.output_dir, f"scene_{scene_id:03d}{filename_suffix}.mp4")
        N = max(2, round(self.duration * self.fps))
        # Linear zoom expression (ffmpeg zoompan 'on' = 1-based frame number)
        denom = f"max({N}-1,1)"
        z_expr  = f"{zoom_start}+({zoom_end}-{zoom_start})*(on-1)/{denom}"
        # x,y: crop-window top-left in scaled image (iw=out_w after scale step)
        # center shifts by pan fraction of image width/height
        cx_expr = f"iw*(0.5+({pan_x})*(on-1)/{denom})"
        cy_expr = f"ih*(0.5+({pan_y})*(on-1)/{denom})"
        x_expr  = f"max(0,min({cx_expr}-iw/zoom/2,iw-iw/zoom))"
        y_expr  = f"max(0,min({cy_expr}-ih/zoom/2,ih-ih/zoom))"
        vf = (
            f"scale={out_w}:{out_h},"
            f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}'"
            f":d={N}:s={out_w}x{out_h}:fps={self.fps}"
        )
        try:
            still.save(tmp_path, "JPEG", quality=95)
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-loop", "1", "-i", tmp_path,
                    "-vf", vf,
                    "-t", str(round(self.duration, 3)),
                    "-c:v", "libx264",
                    "-crf", "14",
                    "-preset", "fast",
                    "-pix_fmt", "yuv420p",
                    "-r", str(self.fps),
                    output_path,
                ],
                check=True,
                capture_output=True,
            )
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
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
