"""Keep named military vehicles looking like military vehicles.

FLUX Schnell maps leftover words like 'Rapid' plus generic 'shattered
vehicles' onto toy or race cars. A locked military convoy must stay
armored military trucks, and invented wreckage is stripped unless the
beat already names it.
"""

from __future__ import annotations

import re

from prompts.prompt_builder import join_prompt_parts

_CONVOY_RE = re.compile(
    r"\b(military convoy|army convoy|convoy|rapid response force|\brsf\b)\b",
    re.IGNORECASE,
)
_MILITARY_TRUCK_RE = re.compile(
    r"\b(military trucks?|army trucks?|armored military|"
    r"armoured military|armored? (?:personnel )?carriers?|"
    r"armoured? (?:personnel )?carriers?|\bapcs?\b|tanks?|"
    r"camouflage(?:d)? (?:military )?(?:trucks?|vehicles?))\b",
    re.IGNORECASE,
)
_AFTERMATH_RE = re.compile(
    r"\b(shattered|wreckage|debris|scattered)\b",
    re.IGNORECASE,
)
_REVEALING_WRECKAGE_RE = re.compile(
    r",?\s*revealing shattered vehicles(?: and scattered equipment)?",
    re.IGNORECASE,
)
_SHATTERED_VEHICLES_RE = re.compile(r"\bshattered vehicles?\b", re.IGNORECASE)
_SCATTERED_EQUIPMENT_RE = re.compile(r"\bscattered equipment\b", re.IGNORECASE)
_STRIKE_RE = re.compile(
    r"\b(drone strike|airstrike|air strike|missile strike|hits?|hit by)\b",
    re.IGNORECASE,
)


def _cleanup(text: str) -> str:
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\s+([,.;])", r"\1", text)
    return text.strip(" ,")


def _beat_names_aftermath(beat_text: str) -> bool:
    return bool(_AFTERMATH_RE.search(beat_text or ""))


def apply_kit_lock(prompt: str, beat_text: str = "") -> str:
    """Force military convoys to military trucks; drop invented wreckage."""
    text = str(prompt or "").strip()
    if not text:
        return ""
    source = f"{beat_text} {text}".strip()
    convoy = bool(_CONVOY_RE.search(source))
    strike = bool(_STRIKE_RE.search(source))
    if convoy and strike and not _beat_names_aftermath(beat_text):
        text = _REVEALING_WRECKAGE_RE.sub("", text)
        text = _SCATTERED_EQUIPMENT_RE.sub("", text)
        text = _SHATTERED_VEHICLES_RE.sub("armored military trucks", text)
        text = _cleanup(text)
    if convoy and not _MILITARY_TRUCK_RE.search(text):
        if re.search(r"\bmilitary convoy\b", text, re.IGNORECASE):
            text = re.sub(
                r"\bmilitary convoy\b",
                "military convoy of armored military trucks",
                text,
                count=1,
                flags=re.IGNORECASE,
            )
        elif re.search(r"\bconvoy\b", text, re.IGNORECASE):
            text = re.sub(
                r"\bconvoy\b",
                "convoy of armored military trucks",
                text,
                count=1,
                flags=re.IGNORECASE,
            )
        else:
            text = join_prompt_parts(text, "armored military trucks")
        text = _cleanup(text)
    return text
