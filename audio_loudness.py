import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional


@dataclass(frozen=True)
class LoudnessNormalizationResult:
    success: bool
    path: Path
    error: Optional[str] = None
    measurements: Dict[str, str] = field(default_factory=dict)


_AUDIO_CODECS = {
    ".aac": ["-c:a", "aac", "-b:a", "192k", "-f", "adts"],
    ".flac": ["-c:a", "flac"],
    ".m4a": ["-c:a", "aac", "-b:a", "192k"],
    ".mp3": ["-c:a", "libmp3lame", "-b:a", "192k"],
    ".ogg": ["-c:a", "libvorbis", "-q:a", "5"],
    ".opus": ["-c:a", "libopus", "-b:a", "128k"],
    ".wav": ["-c:a", "pcm_s16le"],
}


def _measurement_json(stderr: str) -> Dict[str, str]:
    start = stderr.rfind("{")
    end = stderr.rfind("}")
    if start < 0 or end < start:
        raise ValueError("FFmpeg did not return loudness measurements")
    values = json.loads(stderr[start:end + 1])
    required = {"input_i", "input_tp", "input_lra", "input_thresh", "target_offset"}
    if not required.issubset(values):
        raise ValueError("FFmpeg returned incomplete loudness measurements")
    return {key: str(value) for key, value in values.items()}


def normalize_loudness_in_place(
    audio_path,
    target_lufs: float = -19.0,
    true_peak_db: float = -1.0,
    loudness_range: float = 11.0,
    ffmpeg_executable: Optional[str] = None,
    trim_silence: bool = True,
) -> LoudnessNormalizationResult:
    path = Path(audio_path)
    measurements: Dict[str, str] = {}
    if not path.is_file():
        return LoudnessNormalizationResult(False, path, f"Audio file not found: {path}")

    codec_args = _AUDIO_CODECS.get(path.suffix.lower())
    if codec_args is None:
        return LoudnessNormalizationResult(
            False, path, f"Unsupported audio container: {path.suffix or '(none)'}"
        )

    ffmpeg = ffmpeg_executable or "ffmpeg"
    # A single silenceremove pass with a positive stop_periods does NOT just
    # trim trailing silence: FFmpeg halts output entirely the first time it
    # sees a qualifying silent gap anywhere in the stream, truncating
    # everything after it (this destroyed whole tracks down to ~0.05s).
    # The safe way to strip only leading/trailing silence is to trim the
    # start, reverse, trim the (now-leading) former end, and reverse back —
    # using only start_periods, never stop_periods.
    # trim_silence=False skips this entirely: callers that add their own
    # deliberate lead/trail padding need the exact duration preserved so it
    # stays in sync with a video track that has no equivalent trim applied.
    trim_filter = (
        "silenceremove=start_periods=1:start_duration=0.05:start_threshold=-50dB,"
        "areverse,"
        "silenceremove=start_periods=1:start_duration=0.05:start_threshold=-50dB,"
        "areverse"
    ) if trim_silence else "anull"
    target = f"I={target_lufs}:TP={true_peak_db}:LRA={loudness_range}"

    try:
        measure = subprocess.run(
            [ffmpeg, "-hide_banner", "-nostats", "-i", str(path), "-vn",
             "-af", f"{trim_filter},loudnorm={target}:print_format=json", "-f", "null", "-"],
            capture_output=True,
            text=True,
        )
        if measure.returncode != 0:
            raise RuntimeError(measure.stderr[-2000:].strip() or "FFmpeg measurement failed")
        measurements = _measurement_json(measure.stderr)

        loudnorm = (
            f"loudnorm={target}:measured_I={measurements['input_i']}:"
            f"measured_TP={measurements['input_tp']}:measured_LRA={measurements['input_lra']}:"
            f"measured_thresh={measurements['input_thresh']}:"
            f"offset={measurements['target_offset']}:linear=true:print_format=summary"
        )
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.stem}_normalized_", suffix=path.suffix, dir=str(path.parent)
        )
        os.close(descriptor)
        try:
            normalize = subprocess.run(
                [ffmpeg, "-y", "-hide_banner", "-i", str(path), "-vn", "-af",
                 f"{trim_filter},{loudnorm}", *codec_args, temporary_name],
                capture_output=True,
                text=True,
            )
            if normalize.returncode != 0:
                raise RuntimeError(normalize.stderr[-2000:].strip() or "FFmpeg normalization failed")
            if not os.path.isfile(temporary_name) or os.path.getsize(temporary_name) == 0:
                raise RuntimeError("FFmpeg produced an empty normalized audio file")
            os.replace(temporary_name, path)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        return LoudnessNormalizationResult(False, path, str(exc), measurements)

    return LoudnessNormalizationResult(True, path, measurements=measurements)