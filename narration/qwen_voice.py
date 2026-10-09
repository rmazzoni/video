"""Speak Sleepy scenes with the Qwen3-TTS clone.

The Qt process does not import qwen_tts. Synthesis runs in
F:\\VID\\voice\\venv and returns one MP3 plus a duration per scene.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import yaml

from sleepy.chapter import normalize_language

MAX_CHUNK_CHARS = 300
SENTENCE_PAUSE_S = 0.8
PARAGRAPH_PAUSE_S = 2.5
_SHORT_TOKEN = {"mr", "dr", "st", "sr", "jr", "vs", "ecc"}


class VoiceCancelled(RuntimeError):
    """The user stopped a clone run."""


class VoiceRun:
    """Cancel handle shared by the panel and the subprocess reader."""

    def __init__(self) -> None:
        self._cancel = threading.Event()
        self._process: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()

    def bind(self, process: subprocess.Popen) -> None:
        with self._lock:
            self._process = process
            if self._cancel.is_set() and process.poll() is None:
                process.kill()

    def stop(self) -> None:
        self._cancel.set()
        with self._lock:
            process = self._process
        if process is not None and process.poll() is None:
            process.kill()

    def cancelled(self) -> bool:
        return self._cancel.is_set()


def vid_root() -> Path:
    return Path(__file__).resolve().parents[2]


def voice_python() -> Path:
    return vid_root() / "voice" / "venv" / "Scripts" / "python.exe"


def default_model_dir() -> Path:
    return vid_root() / "voice" / "models" / "Qwen3-TTS-12Hz-1.7B-Base"


def worker_script() -> Path:
    return Path(__file__).resolve().with_name("qwen_voice_worker.py")


def _split_sentences(paragraph: str) -> List[str]:
    raw = re.split(r"(?<=[.!?…])\s+", paragraph.strip())
    merged: List[str] = []
    for part in raw:
        part = part.strip()
        if not part:
            continue
        if merged:
            previous = merged[-1]
            words = previous.rstrip(".!?…").split()
            token = words[-1].strip("(\"") if words else ""
            short = len(token) == 1 or token.lower() in _SHORT_TOKEN
            if previous.endswith(".") and short and token[:1].isalpha():
                merged[-1] = previous + " " + part
                continue
        merged.append(part)
    return merged


def _fit_chunk(text: str, limit: int = MAX_CHUNK_CHARS) -> List[str]:
    remaining = " ".join(text.split())
    if len(remaining) <= limit:
        return [remaining] if remaining else []
    chunks: List[str] = []
    while len(remaining) > limit:
        window = remaining[:limit]
        cut = window.rfind(" ")
        if cut < limit // 2:
            cut = limit
        chunks.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    if remaining:
        chunks.append(remaining)
    return [chunk for chunk in chunks if chunk]


def chunk_narration(text: str) -> List[tuple]:
    """Return (chunk, pause_after_seconds). The last pause is 0.

    Sentences stay under 300 characters. A sentence boundary waits 0.8 s.
    A blank line waits 2.5 s. A hard split inside one long sentence does not.
    """
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", str(text or "").strip()) if part.strip()]
    pieces: List[tuple] = []
    for paragraph_index, paragraph in enumerate(paragraphs):
        sentences = _split_sentences(paragraph) or [" ".join(paragraph.split())]
        last_paragraph = paragraph_index == len(paragraphs) - 1
        for sentence_index, sentence in enumerate(sentences):
            parts = _fit_chunk(sentence)
            last_sentence = sentence_index == len(sentences) - 1
            for part_index, part in enumerate(parts):
                last_part = part_index == len(parts) - 1
                if not last_part:
                    pause = 0.0
                elif not last_sentence:
                    pause = SENTENCE_PAUSE_S
                elif not last_paragraph:
                    pause = PARAGRAPH_PAUSE_S
                else:
                    pause = 0.0
                pieces.append((part, pause))
    return pieces


def chunks_for_scene(text: str, trailing_paragraph_pause: bool) -> List[dict]:
    pieces = chunk_narration(text)
    chunks = [
        {"text": chunk_text, "pause_after_s": pause}
        for chunk_text, pause in pieces
    ]
    if chunks and trailing_paragraph_pause:
        chunks[-1]["pause_after_s"] = max(float(chunks[-1]["pause_after_s"]), PARAGRAPH_PAUSE_S)
    return chunks


def text_token(language: str, text: str) -> str:
    payload = f"{normalize_language(language)}\n{text.strip()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_request(
    language: str,
    ref_audio: str,
    ref_text: str,
    model_dir: Optional[str] = None,
) -> Path:
    """Fail before the voice process starts. Never substitute a demo clip."""
    normalize_language(language)
    if not str(ref_text or "").strip():
        raise RuntimeError(
            "Type the transcript of your reference clip. "
            "The clone speaks with your voice only when the words match the recording."
        )
    audio = str(ref_audio or "").strip()
    if not audio or not os.path.isfile(audio):
        raise RuntimeError(
            "Choose your reference clip first. "
            "Sleepy does not use a stand-in voice."
        )
    python = voice_python()
    if not python.is_file():
        raise RuntimeError(
            f"The voice environment is not installed at {python}. "
            "The Sleepy clone cannot speak until that environment is present."
        )
    script = worker_script()
    if not script.is_file():
        raise RuntimeError(f"Voice worker is missing: {script}")
    chosen = Path(model_dir).expanduser() if str(model_dir or "").strip() else default_model_dir()
    if not chosen.is_dir():
        if str(model_dir or "").strip():
            raise RuntimeError(f"Checkpoint folder not found: {chosen}")
        raise RuntimeError(f"Qwen3-TTS 1.7B-Base is not at {chosen}.")
    return chosen


def _read_yaml_dict(path: str) -> dict:
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data if isinstance(data, dict) else {}


def _media_duration(path: str) -> float:
    try:
        from mutagen.mp3 import MP3
        length = float(MP3(path).info.length)
        if length > 0:
            return length
    except Exception:
        pass
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", path,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        return float(result.stdout.strip())
    raise RuntimeError(f"Could not measure duration: {path}")


def _wav_to_mp3(wav_path: str, mp3_path: str) -> None:
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", wav_path, "-c:a", "libmp3lame", "-b:a", "192k", mp3_path],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not os.path.isfile(mp3_path) or os.path.getsize(mp3_path) == 0:
        tail = (result.stderr or "")[-1500:]
        raise RuntimeError(f"Could not convert voice audio to MP3:\n{tail}")


def synthesize_scenes(
    scenes: Sequence[dict],
    output_dir: str,
    timings_path: str,
    language: str,
    ref_audio: str,
    ref_text: str,
    model_dir: Optional[str] = None,
    seed: int = 42,
    replace_existing: bool = False,
    on_progress: Optional[Callable[[str], None]] = None,
    voice_run: Optional[VoiceRun] = None,
) -> Dict[int, float]:
    """Write scene_NNN.mp3 and timings.yaml. One model load for the pending scenes."""
    language = normalize_language(language)
    model = validate_request(language, ref_audio, ref_text, model_dir)
    if voice_run is not None and voice_run.cancelled():
        raise VoiceCancelled("Voice cancelled.")

    os.makedirs(output_dir, exist_ok=True)
    manifest_path = os.path.join(output_dir, "voice_sources.yaml")
    manifest = _read_yaml_dict(manifest_path)
    timings: Dict[int, float] = {}
    for key, value in _read_yaml_dict(timings_path).items():
        try:
            timings[int(key)] = float(value)
        except (TypeError, ValueError):
            continue

    pending = []
    tokens = {}
    for scene in scenes:
        scene_id = int(scene["id"])
        text = str(scene.get("text") or "").strip()
        if not text:
            raise RuntimeError(f"Scene {scene_id} has no narration text.")
        token = text_token(language, text)
        tokens[scene_id] = token
        mp3_path = os.path.join(output_dir, f"scene_{scene_id:03d}.mp3")
        stored = manifest.get(scene_id, manifest.get(str(scene_id)))
        if (
            not replace_existing
            and os.path.isfile(mp3_path)
            and stored == token
            and scene_id in timings
        ):
            continue
        pending.append({"id": scene_id, "text": text})

    def _report(message: str) -> None:
        if on_progress:
            on_progress(message)

    if not pending:
        _report("Narration already matches this text.")
        return timings

    job_scenes = []
    wav_for: Dict[int, str] = {}
    total = len(pending)
    for index, scene in enumerate(pending, start=1):
        scene_id = int(scene["id"])
        wav_path = os.path.join(output_dir, f"scene_{scene_id:03d}.wav")
        wav_for[scene_id] = wav_path
        job_scenes.append({
            "id": scene_id,
            "wav": wav_path,
            "chunks": chunks_for_scene(scene["text"], trailing_paragraph_pause=index < total),
        })

    job = {
        "model": str(model),
        "ref_audio": os.path.abspath(ref_audio),
        "ref_text": str(ref_text).strip(),
        "language": language,
        "seed": int(seed),
        "scenes": job_scenes,
    }
    descriptor, job_path = tempfile.mkstemp(suffix=".json", prefix="sleepy-voice-")
    os.close(descriptor)
    err_descriptor, err_path = tempfile.mkstemp(suffix=".log", prefix="sleepy-voice-")
    os.close(err_descriptor)
    try:
        with open(job_path, "w", encoding="utf-8") as handle:
            import json
            json.dump(job, handle, ensure_ascii=False)
        _speak_job(
            job_path,
            err_path,
            wav_for,
            tokens,
            output_dir,
            timings,
            timings_path,
            manifest,
            manifest_path,
            on_progress=_report,
            voice_run=voice_run,
        )
    finally:
        for path in (job_path, err_path):
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
    return timings


def _speak_job(
    job_path: str,
    err_path: str,
    wav_for: Dict[int, str],
    tokens: Dict[int, str],
    output_dir: str,
    timings: Dict[int, float],
    timings_path: str,
    manifest: dict,
    manifest_path: str,
    on_progress: Callable[[str], None],
    voice_run: Optional[VoiceRun],
) -> None:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    hf_home = vid_root() / "voice" / "hf-home"
    if hf_home.is_dir():
        env["HF_HOME"] = str(hf_home)
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NO_WINDOW

    error_line = ""
    with open(err_path, "w", encoding="utf-8") as err_handle:
        process = subprocess.Popen(
            [str(voice_python()), str(worker_script()), job_path],
            stdout=subprocess.PIPE,
            stderr=err_handle,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            creationflags=creationflags,
        )
        if voice_run is not None:
            voice_run.bind(process)
        assert process.stdout is not None
        try:
            for line in process.stdout:
                if voice_run is not None and voice_run.cancelled():
                    if process.poll() is None:
                        process.kill()
                    break
                text = line.strip()
                if not text:
                    continue
                if text.startswith("ERROR "):
                    error_line = text[6:].strip()
                    on_progress(error_line)
                    continue
                if not text.startswith("PROGRESS "):
                    continue
                parts = text.split()
                if len(parts) < 4:
                    continue
                try:
                    index = int(parts[1])
                    total = int(parts[2])
                    scene_id = int(parts[3])
                except ValueError:
                    continue
                _commit_scene(
                    scene_id, wav_for, tokens, output_dir, timings, timings_path, manifest, manifest_path,
                )
                on_progress(f"Spoke scene {scene_id} ({index}/{total})")
        except Exception:
            if process.poll() is None:
                process.kill()
            process.wait()
            raise
        return_code = process.wait()

    if voice_run is not None and voice_run.cancelled():
        raise VoiceCancelled("Voice cancelled.")
    if return_code != 0:
        tail = ""
        try:
            with open(err_path, "r", encoding="utf-8", errors="replace") as handle:
                tail = handle.read()[-2000:].strip()
        except OSError:
            tail = ""
        message = error_line or tail or f"Voice process failed ({return_code})."
        raise RuntimeError(message)


def _commit_scene(
    scene_id: int,
    wav_for: Dict[int, str],
    tokens: Dict[int, str],
    output_dir: str,
    timings: Dict[int, float],
    timings_path: str,
    manifest: dict,
    manifest_path: str,
) -> None:
    wav_path = wav_for[scene_id]
    mp3_path = os.path.join(output_dir, f"scene_{scene_id:03d}.mp3")
    if not os.path.isfile(wav_path) or os.path.getsize(wav_path) == 0:
        raise RuntimeError(f"Scene {scene_id} produced no audio.")
    _wav_to_mp3(wav_path, mp3_path)
    try:
        os.remove(wav_path)
    except OSError:
        pass
    timings[scene_id] = round(_media_duration(mp3_path), 3)
    manifest[scene_id] = tokens[scene_id]
    with open(timings_path, "w", encoding="utf-8") as handle:
        yaml.safe_dump(timings, handle, sort_keys=True)
    stored = {str(key): value for key, value in manifest.items()}
    with open(manifest_path, "w", encoding="utf-8") as handle:
        yaml.safe_dump(stored, handle, sort_keys=True)
