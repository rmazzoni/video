"""
Ken Burns effect clip generator.

Produces a video clip from a still image by applying a slow cinematic
pan and/or zoom, with a configurable duration.
"""

import concurrent.futures
import os
import random
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


# Available motion styles.
# Pan values are fractions of image width/height to shift over the FULL clip.
# Rule: pan_x * img_w / (N_frames - 1) must be ≥ 1 px for the longest likely
# clip (6 s × 24 fps = 143 inter-frame steps, img_w ≈ 1024).
# Minimum safe pan_x = 143/1024 ≈ 0.14.  Values below that produce
# sub-pixel-per-frame motion which aliases into visible jitter.
_MOTIONS = [
    {"name": "zoom_in",        "zoom_start": 1.0,   "zoom_end": 1.40,  "pan_x": 0.0,   "pan_y": 0.0},
    {"name": "zoom_out",       "zoom_start": 1.40,  "zoom_end": 1.0,   "pan_x": 0.0,   "pan_y": 0.0},
    {"name": "zoom_in_right",  "zoom_start": 1.0,   "zoom_end": 1.40,  "pan_x": 0.10,  "pan_y": 0.0},
    {"name": "zoom_in_left",   "zoom_start": 1.0,   "zoom_end": 1.40,  "pan_x":-0.10,  "pan_y": 0.0},
    {"name": "zoom_out_right", "zoom_start": 1.40,  "zoom_end": 1.0,   "pan_x": 0.10,  "pan_y": 0.0},
    {"name": "zoom_out_left",  "zoom_start": 1.40,  "zoom_end": 1.0,   "pan_x":-0.10,  "pan_y": 0.0},
]


def _pan_x_for_clip(clip_index: int) -> float:
    return 0.10 if clip_index % 2 == 0 else -0.10


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
        Auto mode: applies a random pan/zoom Ken Burns motion via ffmpeg zoompan filter
        (no Python frame loop — all rendering done natively in ffmpeg).
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
        # crop + LANCZOS — floating-point crop boxes give smooth sub-pixel
        # accuracy; LANCZOS gives high-quality downsample.  Parallel rendering
        # keeps all CPU cores busy so the pipe-write to ffmpeg becomes the
        # wall-clock limit rather than PIL.
        rng = random.Random((self.seed if self.seed is not None else 0) ^ (scene_id * 2654435761))
        motion = rng.choice(_MOTIONS)

        zoom_start = motion["zoom_start"]
        zoom_end   = motion["zoom_end"]
        pan_number = scene_id if motion_index is None else motion_index
        pan_x      = _pan_x_for_clip(pan_number)
        pan_y      = motion["pan_y"]

        MOTION_CAP = 6.0
        motion_dur = min(self.duration, MOTION_CAP)
        hold_dur   = max(0.0, self.duration - motion_dur)
        N          = max(2, round(motion_dur * self.fps))

        image = Image.open(image_path).convert("RGB")
        img_w, img_h = image.size

        def _render(i: int) -> bytes:
            t = i / max(N - 1, 1)
            zoom  = zoom_start + (zoom_end - zoom_start) * t
            src_w = img_w / zoom
            src_h = img_h / zoom
            cx = img_w / 2.0 + pan_x * img_w * t
            cy = img_h / 2.0 + pan_y * img_h * t
            x0 = max(0.0, min(cx - src_w / 2.0, img_w - src_w))
            y0 = max(0.0, min(cy - src_h / 2.0, img_h - src_h))
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

        # Hold segment: crop source image at final zoom/pan position, no piping.
        if hold_dur > 0.05 and motion_tmp:
            final_z  = zoom_end
            crop_w   = img_w / final_z
            crop_h   = img_h / final_z
            final_cx = img_w / 2.0 + pan_x * img_w
            final_cy = img_h / 2.0 + pan_y * img_h
            crop_x   = max(0.0, min(final_cx - crop_w / 2.0, img_w - crop_w))
            crop_y   = max(0.0, min(final_cy - crop_h / 2.0, img_h - crop_h))
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
