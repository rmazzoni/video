"""Qwen3-TTS voice-clone worker.

Run this only with F:\\VID\\voice\\venv\\Scripts\\python.exe.
The VID application must not import qwen_tts. Heavy imports stay inside main().
Streaming mode stays off: upstream bug makes streaming run too fast.
"""

from __future__ import annotations

import json
import sys


def _fail(message: str) -> None:
    print(f"ERROR {message}", flush=True)
    print(message, file=sys.stderr, flush=True)
    raise SystemExit(1)


def _silence(sample_rate: int, seconds: float):
    import numpy as np
    count = int(round(float(sample_rate) * max(0.0, float(seconds))))
    return np.zeros(count, dtype=np.float32)


def _as_mono(wav):
    import numpy as np
    audio = np.asarray(wav, dtype=np.float32).reshape(-1)
    return np.clip(audio, -1.0, 1.0)


def main() -> None:
    if len(sys.argv) != 2:
        _fail("Voice worker expects one job json path.")
    try:
        with open(sys.argv[1], "r", encoding="utf-8") as handle:
            job = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        _fail(f"Could not read the voice job: {exc}")

    import numpy as np
    import soundfile as sf
    import torch
    from qwen_tts import Qwen3TTSModel

    if not torch.cuda.is_available():
        _fail("CUDA is not available. The cloned voice runs on the GPU.")

    torch.manual_seed(int(job.get("seed", 42)))
    try:
        model = Qwen3TTSModel.from_pretrained(
            str(job["model"]),
            device_map="cuda:0",
            dtype=torch.bfloat16,
            attn_implementation="sdpa",
        )
        prompt = model.create_voice_clone_prompt(
            ref_audio=str(job["ref_audio"]),
            ref_text=str(job["ref_text"]),
            x_vector_only_mode=False,
        )
    except Exception as exc:
        _fail(f"Could not load the cloned voice: {exc}")

    scenes = job.get("scenes") or []
    total = len(scenes)
    for index, scene in enumerate(scenes, start=1):
        scene_id = int(scene["id"])
        chunks = scene.get("chunks") or []
        if not chunks:
            _fail(f"Scene {scene_id} has nothing to speak.")
        pieces = []
        sample_rate = None
        try:
            for chunk in chunks:
                text = str(chunk.get("text") or "").strip()
                if not text:
                    _fail(f"Scene {scene_id} has an empty voice chunk.")
                wavs, rate = model.generate_voice_clone(
                    text=text,
                    language=str(job["language"]),
                    voice_clone_prompt=prompt,
                    non_streaming_mode=True,
                    max_new_tokens=1024,
                )
                if sample_rate is None:
                    sample_rate = int(rate)
                elif int(rate) != sample_rate:
                    _fail(f"Scene {scene_id} changed sample rate mid-scene.")
                pieces.append(_as_mono(wavs[0]))
                pause = float(chunk.get("pause_after_s") or 0.0)
                if pause > 0:
                    pieces.append(_silence(sample_rate, pause))
        except SystemExit:
            raise
        except Exception as exc:
            message = str(exc)
            if "out of memory" in message.lower():
                _fail(
                    "The voice model ran out of GPU memory. "
                    "Wait until HiDream has unloaded, then speak again."
                )
            _fail(f"Scene {scene_id} failed: {exc}")
        if sample_rate is None or not pieces:
            _fail(f"Scene {scene_id} produced no audio.")
        audio = np.concatenate(pieces)
        sf.write(str(scene["wav"]), audio, sample_rate, subtype="PCM_16")
        print(f"PROGRESS {index} {total} {scene_id}", flush=True)

    del model
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
