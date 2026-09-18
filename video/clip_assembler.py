import os
import subprocess
import tempfile
from typing import Dict, List, Optional, Tuple

_PREVIEW_MODELS = ("schnell", "zimage", "dev", "hidream", "flux2")


def scene_id_from_name(filename: str) -> int:
    try:
        return int(os.path.splitext(filename)[0].split("_")[1])
    except Exception:
        return 0


def clip_sort_key(fname: str) -> tuple:
    """
    Order: scene, beat, model (schnell then zimage then others), variant.

    Supports scene_001.mp4, scene_001_v00.mp4, and
    scene_001_schnell_b02_v2.mp4.
    """
    name = os.path.splitext(os.path.basename(fname))[0]
    parts = name.split("_")
    try:
        sid = int(parts[1])
    except (IndexError, ValueError):
        sid = 0
    beat = 0
    model_rank = 0
    variant = 0
    if len(parts) >= 4 and parts[2].lower() in _PREVIEW_MODELS:
        model_rank = _PREVIEW_MODELS.index(parts[2].lower())
        if parts[3].lower().startswith("b"):
            try:
                beat = int(parts[3][1:])
            except ValueError:
                beat = 0
        if len(parts) > 4 and parts[4].lower().startswith("v"):
            try:
                variant = int(parts[4][1:])
            except ValueError:
                variant = 0
    elif len(parts) > 2 and parts[2].lower().startswith("v"):
        try:
            variant = int(parts[2][1:])
        except ValueError:
            variant = 0
    return (sid, beat, model_rank, variant)


class ClipAssembler:
    """
    Concatenates individual scene clips into a single final video using FFmpeg.
    Each clip is padded (freeze-last-frame) to match its dubbed audio duration
    before concatenation, so the assembled video stays in sync.
    """

    def __init__(self, output_path: str, fps: int = 24,
                 target_resolution: Optional[tuple] = (1920, 1080)):
        self.output_path = output_path
        self.fps = fps
        self.target_resolution = target_resolution  # (width, height) or None to keep source size

    def assemble(self, clips_dir: str, on_progress=None,
                 scene_timings: Optional[Dict] = None) -> str:
        """
        Concatenates all MP4 clips in a directory into a single video.
        If scene_timings is provided ({scene_id: duration_seconds}), each
        scene's clips together match that duration (the last clip of the
        scene is freeze-padded for rounding).
        :param on_progress: optional callback(percent_0_100, 100) called
                            periodically while FFmpeg encodes the concatenated video.
        Returns the output file path.
        """
        clip_files = self._get_sorted_clips(clips_dir)
        if not clip_files:
            raise ValueError(f"No clips found in {clips_dir}")

        total = len(clip_files)
        print(f"Assembling {total} clips via FFmpeg concat…")

        # Pad so each *scene* matches its dubbed audio duration. Multiple
        # clips for one scene already share that duration; only the last
        # clip of the group is freeze-padded for rounding.
        padded_files = []
        temp_files = []
        for sid, group in _clips_grouped_by_scene(clip_files):
            target = None
            if scene_timings and sid is not None:
                target = scene_timings.get(sid) or scene_timings.get(str(sid))
            if not target:
                padded_files.extend(group)
                continue
            target = float(target)
            if len(group) == 1:
                padded = self._pad_clip(group[0], target)
                if padded != group[0]:
                    temp_files.append(padded)
                padded_files.append(padded)
                continue
            used = 0.0
            for path in group[:-1]:
                used += self._clip_duration(path)
                padded_files.append(path)
            last_target = max(0.05, target - used)
            padded = self._pad_clip(group[-1], last_target)
            if padded != group[-1]:
                temp_files.append(padded)
            padded_files.append(padded)

        # Write FFmpeg concat list file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as fh:
            for p in padded_files:
                fh.write(f"file '{p.replace(chr(39), chr(39)+chr(92)+chr(39)+chr(39))}'\n")
            list_path = fh.name

        # Sum clip durations up front so FFmpeg's own "out_time" progress can
        # be turned into a meaningful percentage instead of a static 82%.
        total_duration = 0.0
        for p in padded_files:
            try:
                probe = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                     "-of", "default=noprint_wrappers=1:nokey=1", p],
                    capture_output=True, text=True,
                )
                total_duration += float(probe.stdout.strip())
            except Exception:
                pass

        try:
            if self.target_resolution:
                w, h = self.target_resolution
                # scale to fit inside WxH, then pad with black bars to exact size
                vf = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                      f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,"
                      f"setsar=1")
                cmd = [
                    "ffmpeg", "-y",
                    "-f", "concat", "-safe", "0",
                    "-i", list_path,
                    "-vf", vf,
                    "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                    "-an",
                    self.output_path,
                ]
            else:
                cmd = [
                    "ffmpeg", "-y",
                    "-f", "concat", "-safe", "0",
                    "-i", list_path,
                    "-c", "copy",
                    self.output_path,
                ]
            self._run_ffmpeg_with_progress(cmd, total_duration, on_progress)
        finally:
            os.unlink(list_path)
            for t in temp_files:
                try:
                    os.unlink(t)
                except Exception:
                    pass

        return self.output_path

    @staticmethod
    def _run_ffmpeg_with_progress(cmd: List[str], total_duration: float, on_progress=None) -> None:
        """Run an FFmpeg command, reporting encode progress via on_progress(percent, 100)."""
        if not on_progress or total_duration <= 0:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f"FFmpeg failed:\n{result.stderr[-2000:]}")
            return

        proc = subprocess.Popen(
            cmd + ["-progress", "pipe:1", "-nostats"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
        # stderr is merged into stdout above so a single read loop can't
        # deadlock on a full, undrained stderr pipe during long encodes.
        tail_lines: List[str] = []
        try:
            for line in proc.stdout:
                line = line.strip()
                if line.startswith("out_time_ms="):
                    try:
                        seconds = int(line.split("=", 1)[1]) / 1_000_000
                    except ValueError:
                        continue
                    pct = max(0.0, min(99.0, seconds / total_duration * 100))
                    on_progress(pct, 100)
                else:
                    tail_lines.append(line)
        finally:
            proc.wait()
        if proc.returncode != 0:
            raise RuntimeError("FFmpeg failed:\n" + "\n".join(tail_lines[-100:]))
        on_progress(100, 100)

    def _clip_duration(self, clip_path: str) -> float:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", clip_path],
            capture_output=True, text=True,
        )
        try:
            return float(probe.stdout.strip())
        except ValueError:
            return 0.0

    def _pad_clip(self, clip_path: str, target_duration: float) -> str:
        """
        Freeze-pad the clip's last frame so its duration equals target_duration.
        Returns the original path if no padding is needed, or a temp file path.
        """
        clip_dur = self._clip_duration(clip_path)
        if clip_dur <= 0:
            return clip_path

        pad = round(target_duration - clip_dur, 3)
        if pad <= 0.05:   # already long enough
            return clip_path

        tmp = clip_path.replace(".mp4", f"_padded.mp4")
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", clip_path,
             "-vf", f"tpad=stop_mode=clone:stop_duration={pad}",
             "-c:v", "libx264", "-preset", "fast", "-crf", "18",
             "-an", tmp],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"Warning: pad failed for {clip_path}: {result.stderr[-500:]}")
            return clip_path
        return tmp

    def _get_sorted_clips(self, clips_dir: str) -> List[str]:
        files = [
            f for f in os.listdir(clips_dir)
            if f.lower().endswith(".mp4") and f.startswith("scene_")
        ]

        files.sort(key=clip_sort_key)
        return [os.path.join(clips_dir, f) for f in files]


def _clips_grouped_by_scene(clip_files: List[str]) -> List[Tuple[int, List[str]]]:
    groups: List[Tuple[int, List[str]]] = []
    current_sid: Optional[int] = None
    current: List[str] = []
    for path in clip_files:
        sid = scene_id_from_name(os.path.basename(path))
        if current_sid is not None and sid != current_sid:
            groups.append((current_sid, current))
            current = []
        current_sid = sid
        current.append(path)
    if current:
        groups.append((current_sid if current_sid is not None else 0, current))
    return groups
