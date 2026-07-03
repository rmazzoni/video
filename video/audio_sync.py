import os
import subprocess
import tempfile


class AudioSync:
    """
    Syncs narration audio with the final assembled video.
    """

    def __init__(
        self,
        output_path: str,
        audio_volume: float = 1.0,
        fade_in: float = 0.0,
        fade_out: float = 0.0,
    ):
        """
        :param output_path: path to save the final video with audio
        :param audio_volume: volume multiplier for narration (1.0 = normal)
        :param fade_in: audio fade-in duration (seconds)
        :param fade_out: audio fade-out duration (seconds)
        """
        self.output_path = output_path
        self.audio_volume = audio_volume
        self.fade_in = fade_in
        self.fade_out = fade_out

    # ---------------------------------------------------------
    # PUBLIC API
    # ---------------------------------------------------------

    def merge(self, video_path: str, audio_path: str) -> str:
        """
        Merges the narration audio with the final video using ffmpeg directly.
        Avoids MoviePy's audio-frame iterator which over-reads past clip duration
        on long files, causing 'Accessing time t=X seconds' errors.
        Returns the output file path.
        """

        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video not found: {video_path}")

        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio not found: {audio_path}")

        print("Loading video...")
        print("Loading audio...")
        print("Merging audio with video...")

        # Probe audio duration for fade-out start calculation
        audio_duration = None
        if self.fade_out > 0:
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
                capture_output=True, text=True,
            )
            try:
                audio_duration = float(probe.stdout.strip())
            except ValueError:
                audio_duration = None

        # Build audio filter chain
        audio_filters = []
        if self.audio_volume != 1.0:
            audio_filters.append(f"volume={self.audio_volume}")
        if self.fade_in > 0:
            audio_filters.append(f"afade=t=in:st=0:d={self.fade_in}")
        if self.fade_out > 0 and audio_duration is not None:
            fade_start = max(audio_duration - self.fade_out, 0)
            audio_filters.append(f"afade=t=out:st={fade_start}:d={self.fade_out}")

        cmd = ["ffmpeg", "-y", "-i", video_path, "-i", audio_path]

        if audio_filters:
            cmd += ["-af", ",".join(audio_filters)]

        cmd += [
            "-c:v", "copy",       # never re-encode video
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",          # stop at the shorter stream (prevents overrun)
            "-map", "0:v:0",
            "-map", "1:a:0",
            self.output_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg audio merge failed:\n{result.stderr[-2000:]}"
            )

        return self.output_path


