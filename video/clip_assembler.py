import os
import subprocess
import tempfile
from typing import List


class ClipAssembler:
    """
    Concatenates individual scene clips into a single final video using FFmpeg.
    Uses stream-copy (no re-encode) for maximum speed and zero quality loss.
    """

    def __init__(self, output_path: str, fps: int = 24):
        self.output_path = output_path
        self.fps = fps

    def assemble(self, clips_dir: str, on_progress=None) -> str:
        """
        Concatenates all MP4 clips in a directory into a single video.
        :param on_progress: optional callback(loaded, total)
        Returns the output file path.
        """
        clip_files = self._get_sorted_clips(clips_dir)
        if not clip_files:
            raise ValueError(f"No clips found in {clips_dir}")

        total = len(clip_files)
        print(f"Assembling {total} clips via FFmpeg concat…")

        # Write FFmpeg concat list file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as fh:
            for path in clip_files:
                fh.write(f"file '{path.replace(chr(39), chr(39)+chr(92)+chr(39)+chr(39))}'\n")
            list_path = fh.name

        if on_progress:
            on_progress(total, total)   # mark clips as loaded instantly

        try:
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", list_path,
                "-c", "copy",           # stream copy — no re-encode
                self.output_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f"FFmpeg failed:\n{result.stderr[-2000:]}")
        finally:
            os.unlink(list_path)

        return self.output_path

    def _get_sorted_clips(self, clips_dir: str) -> List[str]:
        files = [
            f for f in os.listdir(clips_dir)
            if f.lower().endswith(".mp4") and f.startswith("scene_")
        ]
        files.sort(key=lambda f: int(f.split("_")[1].split(".")[0]))
        return [os.path.join(clips_dir, f) for f in files]
        ]

        # Sort by scene number
        files.sort(key=lambda x: int(x.split("_")[1].split(".")[0]))

        return [os.path.join(clips_dir, f) for f in files]
