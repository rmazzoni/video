"""
narration/tts_engine.py

Edge TTS synthesis engine.

Generates per-scene MP3 audio files from script text using Microsoft Edge TTS.
Measures the duration of each clip and writes a timings manifest so that the
video clip generator can match each Ken Burns clip to its audio length.

Text fixup patterns are borrowed from dubbing_editor.py so that Italian and
English texts are pre-processed consistently.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

# ── Text fixups (ported from dubbing_editor._TTS_TEXT_FIXUPS) ─────────────────
# Each entry is (regex_pattern, replacement).  Applied in order before synthesis.
_TEXT_FIXUPS: List[Tuple[str, str]] = [
    # Italian elisions that confuse the tokeniser
    (r"c'è",              "cè"),
    (r"c'È",              "cÈ"),
    (r"C'è",              "Cè"),
    (r"C'È",              "CÈ"),
    (r"n['\u2019]è",      "nè"),
    (r"n['\u2019]È",      "nÈ"),
    (r"N['\u2019]è",      "Nè"),
    (r"N['\u2019]È",      "NÈ"),
    (r"d['\u2019]élite",  "délite"),
    (r"d['\u2019]Élite",  "dÉlite"),
    (r"D['\u2019]élite",  "Délite"),
    (r"D['\u2019]Élite",  "DÉlite"),
    # Decade shorthand: '60, '80 etc.
    (r"'(\d{2})\b",       r"\1"),
    # Elided articles before numbers: l'80%, dell'87% etc.
    (r"\b([Ll]|[Dd]ell|[Nn]ell|[Ss]ull|[Aa]ll|[Dd]all)['\u2019](\d)", r"\1\2"),
]


def _apply_fixups(text: str) -> str:
    for pattern, replacement in _TEXT_FIXUPS:
        text = re.sub(pattern, replacement, text)
    return text


# ── Edge TTS voice catalogue ──────────────────────────────────────────────────
# (display_label, voice_short_name, gender)
EDGE_TTS_VOICES: List[Tuple[str, str, str]] = [
    # ── Italian ───────────────────────────────────────────────────────────────
    ("🇮🇹 Diego     · it-IT · Neural ♂",            "it-IT-DiegoNeural",                   "Male"),
    ("🇮🇹 Giuseppe  · it-IT · Multilingual ♂",      "it-IT-GiuseppeMultilingualNeural",    "Male"),
    ("🇮🇹 Elsa      · it-IT · Neural ♀",            "it-IT-ElsaNeural",                    "Female"),
    ("🇮🇹 Isabella  · it-IT · Neural ♀",            "it-IT-IsabellaNeural",                "Female"),
    # ── English (US) ──────────────────────────────────────────────────────────
    ("🇺🇸 Andrew    · en-US · Neural ♂",            "en-US-AndrewNeural",                  "Male"),
    ("🇺🇸 Brian     · en-US · Neural ♂",            "en-US-BrianNeural",                   "Male"),
    ("🇺🇸 Christopher· en-US · Neural ♂",           "en-US-ChristopherNeural",             "Male"),
    ("🇺🇸 Eric      · en-US · Neural ♂",            "en-US-EricNeural",                    "Male"),
    ("🇺🇸 Guy       · en-US · Neural ♂",            "en-US-GuyNeural",                     "Male"),
    ("🇺🇸 Roger     · en-US · Neural ♂",            "en-US-RogerNeural",                   "Male"),
    ("🇺🇸 Ava       · en-US · Neural ♀",            "en-US-AvaNeural",                     "Female"),
    ("🇺🇸 Aria      · en-US · Neural ♀",            "en-US-AriaNeural",                    "Female"),
    ("🇺🇸 Emma      · en-US · Neural ♀",            "en-US-EmmaNeural",                    "Female"),
    ("🇺🇸 Jenny     · en-US · Neural ♀",            "en-US-JennyNeural",                   "Female"),
    ("🇺🇸 Michelle  · en-US · Neural ♀",            "en-US-MichelleNeural",                "Female"),
    # ── English (UK) ──────────────────────────────────────────────────────────
    ("🇬🇧 Ryan      · en-GB · Neural ♂",            "en-GB-RyanNeural",                    "Male"),
    ("🇬🇧 Thomas    · en-GB · Neural ♂",            "en-GB-ThomasNeural",                  "Male"),
    ("🇬🇧 Libby     · en-GB · Neural ♀",            "en-GB-LibbyNeural",                   "Female"),
    ("🇬🇧 Maisie    · en-GB · Neural ♀",            "en-GB-MaisieNeural",                  "Female"),
    ("🇬🇧 Sonia     · en-GB · Neural ♀",            "en-GB-SoniaNeural",                   "Female"),
]


# ── TTS Engine ────────────────────────────────────────────────────────────────

class TTSEngine:
    """
    Synthesises speech for a list of scenes using Edge TTS.

    Saves one MP3 per scene to *output_dir* and writes a timings YAML
    file mapping scene_id → duration_seconds.
    """

    def __init__(
        self,
        output_dir: str,
        voice: str = "it-IT-DiegoNeural",
        rate: str = "+0%",
        pitch: str = "+0Hz",
        volume: str = "+0%",
    ):
        """
        :param output_dir: directory to save audio files
        :param voice: Edge TTS short voice name
        :param rate: speaking rate offset, e.g. "+10%", "-5%"
        :param pitch: pitch offset, e.g. "+2Hz", "-10Hz"
        :param volume: volume offset, e.g. "+0%", "+10%"
        """
        self.output_dir = output_dir
        self.voice = voice
        self.rate = rate
        self.pitch = pitch
        self.volume = volume
        os.makedirs(output_dir, exist_ok=True)

    # ---------------------------------------------------------
    # PUBLIC API
    # ---------------------------------------------------------

    def synthesise_scenes(
        self,
        scenes: List[dict],
        timings_path: str,
        on_progress: Optional[callable] = None,
        skip_existing: bool = True,
    ) -> Dict[int, float]:
        """
        Synthesise audio for all scenes. Returns {scene_id: duration_seconds}.

        :param scenes: list of scene dicts with 'id' and 'text'
        :param timings_path: path to write/update timings.yaml
        :param on_progress: optional callback(scene_id, index, total)
        :param skip_existing: skip scenes that already have an audio file
        """
        # Load existing timings
        timings: Dict[int, float] = {}
        if os.path.exists(timings_path):
            with open(timings_path, "r", encoding="utf-8") as fh:
                timings = yaml.safe_load(fh) or {}

        total = len(scenes)
        for index, scene in enumerate(scenes, start=1):
            scene_id = int(scene["id"])
            audio_path = os.path.join(self.output_dir, f"scene_{scene_id:03d}.mp3")

            if skip_existing and os.path.exists(audio_path) and scene_id in timings:
                if on_progress:
                    on_progress(scene_id, index, total, skipped=True)
                continue

            text = _apply_fixups(scene["text"])
            self._synthesise_subprocess(text, audio_path)

            duration = self._measure_duration(audio_path)
            timings[scene_id] = duration

            # Persist timings after each scene so a crash doesn't lose progress
            with open(timings_path, "w", encoding="utf-8") as fh:
                yaml.safe_dump(timings, fh, sort_keys=True)

            if on_progress:
                on_progress(scene_id, index, total, skipped=False)

        return timings

    # ---------------------------------------------------------
    # INTERNAL
    # ---------------------------------------------------------

    def _synthesise_subprocess(self, text: str, output_path: str) -> None:
        """Synthesise via a temp script file — avoids encoding issues on Windows."""
        import sys, subprocess, tempfile, os
        kwargs: dict = {}
        def _is_zero(v: str) -> bool:
            return v.lstrip('+').rstrip('%Hz') == '0'
        if not _is_zero(self.rate):   kwargs["rate"]   = self.rate
        if not _is_zero(self.pitch):  kwargs["pitch"]  = self.pitch
        if not _is_zero(self.volume): kwargs["volume"] = self.volume

        kw_lines = "".join(
            f"    kwargs[{k!r}] = {v!r}\n" for k, v in kwargs.items()
        )
        script = (
            "# -*- coding: utf-8 -*-\n"
            "import asyncio, edge_tts\n"
            "async def _go():\n"
            "    kwargs = {}\n"
            + kw_lines +
            f"    c = edge_tts.Communicate({text!r}, {self.voice!r}, **kwargs)\n"
            f"    await c.save({output_path!r})\n"
            "asyncio.run(_go())\n"
        )
        sf = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8')
        sf.write(script)
        sf.close()
        try:
            result = subprocess.run(
                [sys.executable, sf.name],
                capture_output=True, text=True, timeout=60,
            )
        finally:
            os.unlink(sf.name)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "TTS synthesis failed")

    @staticmethod
    def _measure_duration(audio_path: str) -> float:
        """Return the duration of an MP3/audio file in seconds."""
        try:
            from mutagen.mp3 import MP3
            return MP3(audio_path).info.length
        except Exception:
            pass
        try:
            # Fallback: use moviepy
            from moviepy import AudioFileClip
            clip = AudioFileClip(audio_path)
            dur = clip.duration
            clip.close()
            return dur
        except Exception:
            return 4.0  # safe default if measurement fails
