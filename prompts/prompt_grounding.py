"""Lexical checks that an image prompt still depicts the locked visual beat."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Sequence

from prompts.visual_beats import VisualBeat, content_tokens, normalize_text

_NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)?\b")
_PROPER_SPAN_RE = re.compile(r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)+)\b")

# Camera/style words Qwen (or style anchors) may add; they are not plot.
_STYLE_ALLOWLIST = {
    "atmosphere", "background", "bokeh", "camera", "cinematic", "closeup",
    "color", "colour", "composition", "contrast", "depth", "documentary",
    "dramatic", "editorial", "field", "foreground", "illustration", "lens",
    "light", "lighting", "medium", "natural", "optical", "photograph",
    "photographic", "photography", "shadow", "shot", "wide",
}


@dataclass
class GroundingResult:
    ok: bool
    missing: List[str] = field(default_factory=list)
    extras: List[str] = field(default_factory=list)

    def summary(self) -> str:
        parts = []
        if self.missing:
            parts.append("missing locked details: " + ", ".join(self.missing))
        if self.extras:
            parts.append("added unsupported details: " + ", ".join(self.extras))
        return "; ".join(parts)


def distinctive_tokens(text: str) -> List[str]:
    return content_tokens(text, min_length=4)


def required_beat_tokens(beat: VisualBeat) -> List[str]:
    """English content words the prompt should still mention."""
    return distinctive_tokens(beat.beat)


def _allowed_text(beat: VisualBeat, narration: str) -> str:
    parts = [
        narration,
        beat.beat,
        beat.source_quote,
        beat.subject,
        beat.action,
        beat.setting,
        " ".join(beat.objects),
    ]
    return " ".join(part for part in parts if part)


def extra_numbers(prompt: str, allowed: str) -> List[str]:
    allowed_norm = normalize_text(allowed)
    extras = []
    for match in _NUMBER_RE.findall(prompt or ""):
        if normalize_text(match) not in allowed_norm:
            extras.append(match)
    return extras


def extra_proper_names(prompt: str, allowed: str) -> List[str]:
    allowed_norm = normalize_text(allowed)
    extras = []
    for match in _PROPER_SPAN_RE.findall(prompt or ""):
        if normalize_text(match) in allowed_norm:
            continue
        extras.append(match)
    return extras


def check_prompt(prompt: str, beat: VisualBeat, narration: str) -> GroundingResult:
    text = str(prompt or "").strip()
    if not text:
        return GroundingResult(ok=False, missing=["(empty prompt)"])

    prompt_tokens = set(content_tokens(text, min_length=4))
    required = [
        token for token in required_beat_tokens(beat)
        if token not in _STYLE_ALLOWLIST
    ]
    missing = [token for token in required if token not in prompt_tokens]
    if required:
        hits = len(required) - len(missing)
        if hits >= max(1, (len(required) + 1) // 2):
            missing = []
    allowed = _allowed_text(beat, narration)
    extras = extra_numbers(text, allowed) + extra_proper_names(text, allowed)
    return GroundingResult(ok=not missing and not extras, missing=missing, extras=extras)


def retry_instruction(result: GroundingResult) -> str:
    return (
        "Your previous prompt drifted from the locked visual beat. "
        f"{result.summary()}. "
        "Rewrite using only the locked visual beat and the original narration. "
        "Do not add people, places, props, numbers, or names that are not there."
    )


def has_required_tokens(prompt: str, tokens: Sequence[str]) -> bool:
    prompt_tokens = set(content_tokens(prompt, min_length=4))
    return all(token in prompt_tokens for token in tokens)
