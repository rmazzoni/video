import os
import subprocess
import tempfile
from typing import List, Dict, Optional


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
        If scene_timings is provided ({scene_id: duration_seconds}), each clip
        is padded with a freeze of its last frame to match that duration.
        :param on_progress: optional callback(loaded, total)
        Returns the output file path.
        """
        clip_files = self._get_sorted_clips(clips_dir)
        if not clip_files:
            raise ValueError(f"No clips found in {clips_dir}")

        total = len(clip_files)
        print(f"Assembling {total} clips via FFmpeg concat…")

        # Pad clips to match dubbed audio duration when timings are available
        padded_files = []
        temp_files = []
        for path in clip_files:
            try:
                scene_id = int(os.path.basename(path).split("_")[1].split(".")[0])
            except Exception:
                scene_id = None

            target = (scene_timings or {}).get(scene_id) or (scene_timings or {}).get(str(scene_id))
            if target:
                padded = self._pad_clip(path, float(target))
                if padded != path:
                    temp_files.append(padded)
                padded_files.append(padded)
            else:
                padded_files.append(path)

        # Write FFmpeg concat list file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as fh:
            for p in padded_files:
                fh.write(f"file '{p.replace(chr(39), chr(39)+chr(92)+chr(39)+chr(39))}'\n")
            list_path = fh.name

        if on_progress:
            on_progress(total, total)

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
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f"FFmpeg failed:\n{result.stderr[-2000:]}")
        finally:
            os.unlink(list_path)
            for t in temp_files:
                try:
                    os.unlink(t)
                except Exception:
                    pass

        return self.output_path

    def _pad_clip(self, clip_path: str, target_duration: float) -> str:
        """
        Freeze-pad the clip's last frame so its duration equals target_duration.
        Returns the original path if no padding is needed, or a temp file path.
        """
        # Get clip duration via ffprobe
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", clip_path],
            capture_output=True, text=True
        )
        try:
            clip_dur = float(probe.stdout.strip())
        except ValueError:
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

        def _sort_key(fname: str) -> tuple:
            # Strip extension first so 'scene_001.mp4' and 'scene_001_v00.mp4'
            # both parse correctly.
            name = os.path.splitext(fname)[0]   # e.g. 'scene_001_v00'
            parts = name.split("_")             # ['scene', '001', 'v00']
            try:
                sid = int(parts[1])
            except (IndexError, ValueError):
                sid = 0
            vidx = 0
            if len(parts) > 2:
                v_part = parts[2]
                if v_part.startswith("v"):
                    try:
                        vidx = int(v_part[1:])
                    except ValueError:
                        pass
            return (sid, vidx)

        files.sort(key=_sort_key)
        return [os.path.join(clips_dir, f) for f in files]
