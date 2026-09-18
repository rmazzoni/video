"""Lexical checks that an image prompt still depicts the locked visual beat."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Sequence

from prompts.visual_beats import VisualBeat, content_tokens, normalize_text

_NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)?\b")
_PROPER_SPAN_RE = re.compile(r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)+)\b")
_CAMERA_NUMBER_RE = re.compile(
    r"\baspect(?:\s+ratio)?\s+\d+\s*[:/]\s*\d+\b"
    r"|\b\d+\s*[:/]\s*\d+\b"
    r"|\bf/\s*\d+(?:\.\d+)?"
    r"|\b\d+(?:\.\d+)?\s*mm\b"
    r"|\biso\s*\d+\b",
    re.IGNORECASE,
)
_PEOPLE_RE = re.compile(
    r"\b(man|woman|men|women|person|people|child|children|boy|girl|"
    r"official|officials|aide|aides|diplomat|diplomats|senator|senators|"
    r"worker|workers|executive|executives|crowd|crowds|audience|"
    r"soldier|soldiers|officer|officers|president|minister|king|queen|"
    r"leader|leaders|delegate|delegates|staff|crew|team|teams|"
    r"assistant|assistants|guard|guards|civilian|civilians)\b",
    re.IGNORECASE,
)
_GARMENT_RE = re.compile(
    r"\b(suit|suits|tie|ties|thobe|thobes|ghutra|shemagh|agal|abaya|"
    r"headscarf|hijab|uniform|uniforms|robe|robes|turban|blazer|"
    r"tuxedo|gown)\b",
    re.IGNORECASE,
)
_AFTERMATH_RE = re.compile(
    r"\b(shattered|wreckage|debris|scattered|race car|race cars|go-kart|go-karts)\b",
    re.IGNORECASE,
)
_ARCHITECTURE_RE = re.compile(
    r"\b(atrium|skyscraper|skyscrapers|boardroom|marble|limestone|"
    r"chrome|minaret|mosque|palace|colonnade|chandelier|hologram|"
    r"holograms|glass tower|glass facade|reflective glass|"
    r"neon|cyberpunk)\b",
    re.IGNORECASE,
)

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


def _allowed_text(beat: VisualBeat, profile_text: str = "") -> str:
    from prompts.visual_identity import identity_allowed_text

    parts = [
        beat.beat,
        beat.source_quote,
        beat.subject,
        beat.action,
        beat.setting,
        " ".join(beat.objects),
        profile_text,
        identity_allowed_text(" ".join(part for part in (beat.beat, beat.subject) if part)),
    ]
    return " ".join(part for part in parts if part)


def extra_numbers(prompt: str, allowed: str) -> List[str]:
    allowed_norm = normalize_text(allowed)
    cleaned = _CAMERA_NUMBER_RE.sub(" ", prompt or "")
    extras = []
    for match in _NUMBER_RE.findall(cleaned):
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


_NAMED_PERSON_GENDER = {"man", "woman", "person", "adult", "male", "female"}


def beat_names_person(beat: VisualBeat) -> bool:
    """True when the locked beat already has someone on camera."""
    for part in (beat.subject, beat.beat, beat.source_quote):
        if part and _PEOPLE_RE.search(part):
            return True
    return False


def extra_restricted_terms(prompt: str, allowed: str, pattern: re.Pattern) -> List[str]:
    allowed_norm = normalize_text(allowed)
    extras: List[str] = []
    seen = set()
    for match in pattern.finditer(prompt or ""):
        term = match.group(0)
        key = normalize_text(term)
        if not key or key in seen or key in allowed_norm:
            continue
        seen.add(key)
        extras.append(term.lower())
    return extras


def check_prompt(
    prompt: str,
    beat: VisualBeat,
    narration: str = "",
    profile_text: str = "",
) -> GroundingResult:
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
        needed = max(1, (len(required) * 2 + 2) // 3)
        if hits >= needed:
            missing = []
        else:
            missing = [token for token in required if token not in prompt_tokens]
    allowed = _allowed_text(beat, profile_text)
    people_extras = extra_restricted_terms(text, allowed, _PEOPLE_RE)
    if beat_names_person(beat):
        people_extras = [
            term for term in people_extras
            if normalize_text(term) not in _NAMED_PERSON_GENDER
        ]
        garment_extras: List[str] = []
    else:
        garment_extras = extra_restricted_terms(text, allowed, _GARMENT_RE)
    extras = (
        extra_numbers(text, allowed)
        + extra_proper_names(text, allowed)
        + people_extras
        + garment_extras
        + extra_restricted_terms(text, allowed, _ARCHITECTURE_RE)
        + extra_restricted_terms(text, allowed, _AFTERMATH_RE)
    )
    return GroundingResult(ok=not missing and not extras, missing=missing, extras=extras)


def retry_instruction(result: GroundingResult) -> str:
    return (
        "Your previous prompt drifted from the locked visual beat. "
        f"{result.summary()}. "
        "Rewrite using only the locked visual beat. "
        "Visible ethnicity and clothing of a person already named in the beat "
        "are required, not extras. "
        "Do not add people, places, architecture, props, numbers, "
        "or names that are not in the locked beat."
    )


def has_required_tokens(prompt: str, tokens: Sequence[str]) -> bool:
    prompt_tokens = set(content_tokens(prompt, min_length=4))
    return all(token in prompt_tokens for token in tokens)
