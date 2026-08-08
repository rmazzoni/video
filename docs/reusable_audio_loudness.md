# Reusable Export Loudness Normalization

The implementation is in `audio_loudness.py`. It is independent of Qt and the
Dubbing Editor, so the file can be copied directly into another Python project.

## What it does

1. Removes leading and trailing silence from the completed audio mix.
2. Measures integrated loudness with FFmpeg's EBU R128 `loudnorm` filter.
3. Applies a second, linear normalization pass using the measured values.
4. Replaces the original only after FFmpeg succeeds.
5. Preserves common containers: WAV, MP3, FLAC, OGG, Opus, AAC, and M4A.

The defaults match the Dubbing Editor: `-19 LUFS`, `-1 dBTP`, and `11 LU` LRA.

## Basic use

```python
from audio_loudness import normalize_loudness_in_place

result = normalize_loudness_in_place("completed_mix.wav")
if not result.success:
    raise RuntimeError(result.error)
```

FFmpeg must be available on `PATH` when `ffmpeg_executable` is omitted.

## Packaged application

Pass the resolved or bundled FFmpeg executable explicitly:

```python
result = normalize_loudness_in_place(
    output_audio_path,
    ffmpeg_executable=bundled_ffmpeg_path,
)
```

## Different delivery target

For example, a `-16 LUFS` target with a `-1.5 dBTP` ceiling:

```python
result = normalize_loudness_in_place(
    output_audio_path,
    target_lufs=-16.0,
    true_peak_db=-1.5,
    loudness_range=11.0,
    ffmpeg_executable=ffmpeg_path,
)
```

## Export pipeline placement

Normalize the fully assembled mix before encoding or muxing the final video:

```python
mix_path = assemble_audio_mix(segments)
result = normalize_loudness_in_place(
    mix_path,
    ffmpeg_executable=ffmpeg_path,
)
if not result.success:
    raise RuntimeError(f"Audio normalization failed: {result.error}")

mux_video_with_audio(source_video, mix_path, destination_video)
```

Measuring the complete programme is important. Normalizing every segment
separately can flatten intentional level differences and produce audible jumps.

## Return value

`LoudnessNormalizationResult` contains:

- `success`: whether the original was replaced with normalized audio.
- `path`: the requested audio path as a `Path`.
- `error`: an actionable error message on failure.
- `measurements`: FFmpeg's first-pass loudness values when available.

The source file remains untouched if validation or either FFmpeg pass fails.
