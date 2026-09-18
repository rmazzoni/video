"""
Ken Burns effect clip generator.

Produces a video clip from a still image by applying a slow cinematic
zoom-in and a single left-or-right pan. Consecutive clips alternate
direction so the cut does not reverse mid-shot.
"""

import concurrent.futures
import os
import subprocess
import tempfile as _tf
from typing import Optional

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


def _enc_args(nvenc: bool) -> list:
    """Return ffmpeg encoder arguments: NVENC when available, libx264 ultrafast otherwise."""
    if nvenc:
        return ["-c:v", "h264_nvenc", "-preset", "p1", "-rc", "vbr",
                "-cq", "24", "-pix_fmt", "yuv420p",
                "-vsync", "cfr", "-video_track_timescale", "12288"]
    return ["-c:v", "libx264", "-crf", "14", "-preset", "ultrafast",
            "-pix_fmt", "yuv420p", "-vsync", "cfr",
            "-video_track_timescale", "12288"]


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


class KenBurnsGenerator:
    """Generates Ken Burns-style video clips from still images."""

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
        :param seed: kept for caller compatibility; auto motion is deterministic
        :param motion_style: "auto" = one-way pan + slight zoom-in, "static" = no motion
        """
        self.output_dir = output_dir
        self.fps = fps
        self.duration = duration
        self.seed = seed
        self.motion_style = motion_style

        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        # Detect NVENC once at construction time so every clip reuses the result.
        self._nvenc: bool = _nvenc_available()

    # ---------------------------------------------------------
    # PUBLIC API
    # ---------------------------------------------------------

    def generate_clip(
        self,
        image_path: str,
        scene_id: int,
        filename_suffix: str = "",
        motion_index: Optional[int] = None,
    ) -> str:
        """
        Generate a clip from a still image.
        Static mode: holds the image still for the full duration.
        Auto mode: slight zoom-in with a single left-or-right pan. Even
        ``motion_index`` (or ``scene_id``) pans right; the next clip pans left.
        Returns the output video file path.
        """
        image = Image.open(image_path)
        img_w, img_h = image.size
        image.close()
        out_w, out_h = self._output_size(img_w, img_h)

        output_path = os.path.join(self.output_dir, f"scene_{scene_id:03d}{filename_suffix}.mp4")

        if self.motion_style == "static":
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-loop", "1", "-i", image_path,
                    "-vf", f"scale={out_w}:{out_h},setsar=1",
                    "-t", str(round(self.duration, 3)),
                    "-r", str(self.fps),
                ] + _enc_args(self._nvenc) + [output_path],
                check=True,
                capture_output=True,
            )
            return output_path

        # ── Animated (auto) mode ──────────────────────────────────────────────
        # Frames are rendered in parallel (ThreadPoolExecutor) using PIL
        # affine + BICUBIC. The crop rectangle is interpolated from a start
        # window to an end window so the pan never reverses mid-clip.
        pan_number = scene_id if motion_index is None else motion_index

        MOTION_CAP = 6.0
        motion_dur = min(self.duration, MOTION_CAP)
        hold_dur   = max(0.0, self.duration - motion_dur)
        N          = max(2, round(motion_dur * self.fps))

        image = Image.open(image_path).convert("RGB")
        img_w, img_h = image.size

        def _render(i: int) -> bytes:
            t = i / max(N - 1, 1)
            src_w, src_h, x0, y0 = interpolated_crop(img_w, img_h, t, pan_number)
            return (
                image.transform(
                    (out_w, out_h),
                    Image.AFFINE,
                    (src_w / out_w, 0.0, x0, 0.0, src_h / out_h, y0),
                    resample=Image.BICUBIC,
                )
                .tobytes()
            )

        # If there is a hold segment encode motion to a temp file first.
        motion_target = output_path
        motion_tmp: str | None = None
        if hold_dur > 0.05:
            motion_tmp = _tf.mktemp(suffix=".mp4")
            motion_target = motion_tmp

        workers = min(8, os.cpu_count() or 4)
        proc = subprocess.Popen(
            [
                "ffmpeg", "-y",
                "-f", "rawvideo", "-vcodec", "rawvideo",
                "-s", f"{out_w}x{out_h}", "-pix_fmt", "rgb24",
                "-r", str(self.fps), "-i", "pipe:0",
            ] + _enc_args(self._nvenc) + [motion_target],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(_render, i) for i in range(N)]
                for fut in futures:
                    proc.stdin.write(fut.result())
            proc.stdin.close()
            proc.wait()
        except Exception:
            proc.stdin.close()
            proc.kill()
            proc.wait()
            if motion_tmp:
                try:
                    os.unlink(motion_tmp)
                except Exception:
                    pass
            raise
        finally:
            image.close()

        # Hold segment: freeze the end crop (last motion frame), no piping.
        if hold_dur > 0.05 and motion_tmp:
            crop_w, crop_h, crop_x, crop_y = interpolated_crop(
                img_w, img_h, 1.0, pan_number
            )
            hold_vf  = (
                f"crop={crop_w:.2f}:{crop_h:.2f}:{crop_x:.2f}:{crop_y:.2f}"
                f",scale={out_w}:{out_h},setsar=1"
            )
            try:
                subprocess.run(
                    [
                        "ffmpeg", "-y",
                        "-i", motion_tmp,
                        "-loop", "1", "-t", str(round(hold_dur, 3)), "-i", image_path,
                        "-filter_complex", f"[1:v]{hold_vf}[hold];[0:v][hold]concat=n=2:v=1:a=0[v]",
                        "-map", "[v]",
                    ] + _enc_args(self._nvenc) + [output_path],
                    check=True, capture_output=True,
                )
            finally:
                try:
                    os.unlink(motion_tmp)
                except Exception:
                    pass

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
