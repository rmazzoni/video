"""
Ken Burns effect clip generator.

Produces a video clip from a still image by applying a slow cinematic
zoom-in and a single left-or-right pan. Consecutive clips alternate
direction so the cut does not reverse mid-shot.

Motion is a single ffmpeg crop/scale graph (no Python frame loop).
"""

import os
import subprocess
from typing import Optional, Tuple

from PIL import Image


def _nvenc_available() -> bool:
    """Return True if ffmpeg was built with h264_nvenc and a capable GPU is present."""
    try:
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-f", "lavfi", "-i", "nullsrc=s=16x16:d=0.1",
             "-c:v", "h264_nvenc", "-f", "null", "-"],
            capture_output=True, timeout=8,
        )
        return r.returncode == 0
    except Exception:
        return False


def max_parallel_encodes(nvenc: bool) -> int:
    """How many ffmpeg encodes to run at once. NVENC has a low session cap."""
    if nvenc:
        return 3
    cpu = os.cpu_count() or 4
    return max(2, min(8, cpu))


def _enc_args(nvenc: bool, x264_threads: Optional[int] = None) -> list:
    """Return ffmpeg encoder arguments: NVENC when available, libx264 ultrafast otherwise."""
    if nvenc:
        return ["-c:v", "h264_nvenc", "-preset", "p1", "-rc", "vbr",
                "-cq", "24", "-pix_fmt", "yuv420p",
                "-vsync", "cfr", "-video_track_timescale", "12288"]
    args = ["-c:v", "libx264", "-crf", "18", "-preset", "ultrafast",
            "-pix_fmt", "yuv420p", "-vsync", "cfr",
            "-video_track_timescale", "12288"]
    if x264_threads:
        args.extend(["-threads", str(int(x264_threads))])
    return args


# Bump when crop math changes so clip sidecars force a re-render.
MOTION_VERSION = 2

# Stay above 1.0 for the whole clip. Zoom 1.0 has zero horizontal slack, so
# the window can only shrink from one side and the center reverses (wobble).
ZOOM_START = 1.12
ZOOM_END = 1.38


def pan_direction(clip_index: int) -> str:
    """Even clips pan right; the next clip pans left."""
    return "right" if int(clip_index) % 2 == 0 else "left"


def motion_cache_key(motion_style: str, fps: int = 24) -> dict:
    """Sidecar payload so a math/settings change regenerates existing clips."""
    return {
        "motion_style": str(motion_style),
        "fps": int(fps),
        "engine": "ken_burns",
        "motion_version": MOTION_VERSION,
    }


def _pan_aligns(clip_index: int) -> tuple:
    """Crop x origin as a 0=left … 1=right fraction at start and end."""
    if pan_direction(clip_index) == "right":
        return 0.0, 1.0
    return 1.0, 0.0


def crop_window(
    img_w: float,
    img_h: float,
    zoom: float,
    pan_align: float,
    v_align: float = 0.5,
) -> tuple:
    """Return (src_w, src_h, x0, y0) for a zoomed window on the source image."""
    src_w = img_w / zoom
    src_h = img_h / zoom
    x0 = max(0.0, img_w - src_w) * pan_align
    y0 = max(0.0, img_h - src_h) * v_align
    return src_w, src_h, x0, y0


def interpolated_crop(
    img_w: float,
    img_h: float,
    t: float,
    clip_index: int,
    zoom_start: float = ZOOM_START,
    zoom_end: float = ZOOM_END,
) -> tuple:
    """
    Linearly interpolate the crop rectangle from the start window to the end
    window. Interpolating the rectangle (not slack × progress) keeps the
    frame center moving in one direction for the whole clip.
    """
    t = max(0.0, min(1.0, float(t)))
    start_align, end_align = _pan_aligns(clip_index)
    start = crop_window(img_w, img_h, zoom_start, start_align)
    end = crop_window(img_w, img_h, zoom_end, end_align)
    return tuple(a + (b - a) * t for a, b in zip(start, end))


MOTION_CAP = 6.0


def ken_burns_vf(
    img_w: float,
    img_h: float,
    out_w: int,
    out_h: int,
    duration: float,
    clip_index: int,
) -> str:
    """ffmpeg crop+scale that matches interpolated_crop, with hold after MOTION_CAP."""
    duration = max(float(duration), 1e-3)
    motion_dur = min(duration, MOTION_CAP)
    sw0, sh0, x0, y0 = interpolated_crop(img_w, img_h, 0.0, clip_index)
    sw1, sh1, x1, y1 = interpolated_crop(img_w, img_h, 1.0, clip_index)
    p = f"min(1\\,t/{motion_dur:.6f})"
    w = f"{sw0:.4f}+({sw1 - sw0:.4f})*{p}"
    h = f"{sh0:.4f}+({sh1 - sh0:.4f})*{p}"
    x = f"{x0:.4f}+({x1 - x0:.4f})*{p}"
    y = f"{y0:.4f}+({y1 - y0:.4f})*{p}"
    return (
        f"crop=w='max(2\\,trunc(({w})/2)*2)':h='max(2\\,trunc(({h})/2)*2)':"
        f"x='max(0\\,trunc({x}))':y='max(0\\,trunc({y}))',"
        f"scale={int(out_w)}:{int(out_h)}:flags=bilinear,setsar=1"
    )


class KenBurnsGenerator:
    """Generates Ken Burns-style video clips from still images."""

    def __init__(
        self,
        output_dir: Optional[str] = None,
        fps: int = 24,
        duration: float = 4.0,
        seed: Optional[int] = None,
        motion_style: str = "auto",
        output_size: Optional[Tuple[int, int]] = None,
    ):
        """
        :param output_dir: where to save generated clips
        :param fps: frames per second
        :param duration: clip length in seconds
        :param seed: kept for caller compatibility; auto motion is deterministic
        :param motion_style: "auto" = one-way pan + slight zoom-in, "static" = no motion
        :param output_size: optional (width, height); default is 1920x1080 for 16:9
        """
        self.output_dir = output_dir
        self.fps = fps
        self.duration = duration
        self.seed = seed
        self.motion_style = motion_style
        self.output_size = output_size

        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        # Detect NVENC once at construction time so every clip reuses the result.
        self._nvenc: bool = _nvenc_available()
        self._x264_threads = max(1, (os.cpu_count() or 4) // max_parallel_encodes(self._nvenc))

    # ---------------------------------------------------------
    # PUBLIC API
    # ---------------------------------------------------------

    def generate_clip(
        self,
        image_path: str,
        scene_id: int,
        filename_suffix: str = "",
        motion_index: Optional[int] = None,
        duration: Optional[float] = None,
    ) -> str:
        """
        Generate a clip from a still image.
        Static mode: holds the image still for the full duration.
        Auto mode: slight zoom-in with a single left-or-right pan. Even
        ``motion_index`` (or ``scene_id``) pans right; the next clip pans left.
        Returns the output video file path.
        """
        clip_dur = float(self.duration if duration is None else duration)
        with Image.open(image_path) as image:
            img_w, img_h = image.size
        if self.output_size:
            out_w, out_h = self.output_size
            out_w = out_w if out_w % 2 == 0 else out_w - 1
            out_h = out_h if out_h % 2 == 0 else out_h - 1
        else:
            out_w, out_h = self._output_size(img_w, img_h)

        output_path = os.path.join(self.output_dir, f"scene_{scene_id:03d}{filename_suffix}.mp4")
        enc = _enc_args(self._nvenc, None if self._nvenc else self._x264_threads)
        dur = str(round(max(clip_dur, 0.05), 3))

        if self.motion_style == "static":
            vf = f"scale={out_w}:{out_h}:flags=bilinear,setsar=1"
        else:
            pan_number = scene_id if motion_index is None else motion_index
            vf = ken_burns_vf(img_w, img_h, out_w, out_h, clip_dur, pan_number)

        result = subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-loop", "1", "-framerate", str(self.fps), "-i", image_path,
                "-t", dur, "-vf", vf, "-an",
                "-r", str(self.fps),
            ] + enc + [output_path],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip()[-1500:]
            raise RuntimeError(f"ffmpeg Ken Burns failed for {image_path}: {err}")
        return output_path

    # ---------------------------------------------------------
    # INTERNAL
    # ---------------------------------------------------------

    def _output_size(self, img_w: int, img_h: int):
        """Return (width, height) for the output video at 1920x1080 (or scaled to aspect ratio)."""
        aspect = img_w / img_h
        target_w = 1920
        if abs(aspect - 16/9) < 0.05:
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
