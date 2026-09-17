"""Turn named nationality and motion into camera-visible prompt clauses.

Distilled image models treat "officer from the United Arab Emirates" as a
caption and fill a European military figure walking into a room. Turbo
pipelines also ignore negative prompts, so appearance and blocking must be
stated in the positive prompt.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from prompts.prompt_builder import join_prompt_parts


# phrase in source text, demonym, visible features.
# Longer phrases first. Only non-Western identities that models whitewash.
_NATIONALITIES: Tuple[Tuple[str, str, str], ...] = (
    ("united arab emirates", "Emirati", "Gulf Arab features, olive-brown complexion"),
    ("south africa", "South African", "appearance matching the named South African identity"),
    ("saudi arabia", "Saudi", "Gulf Arab features, olive-brown complexion"),
    ("afghanistan", "Afghan", "Central Asian features"),
    ("philippines", "Filipino", "Southeast Asian features"),
    ("palestinian", "Palestinian", "Levantine Arab features"),
    ("palestine", "Palestinian", "Levantine Arab features"),
    ("indonesia", "Indonesian", "Southeast Asian features"),
    ("bangladesh", "Bangladeshi", "South Asian features"),
    ("vietnamese", "Vietnamese", "Southeast Asian features"),
    ("ethiopia", "Ethiopian", "East African features"),
    ("moroccan", "Moroccan", "North African features"),
    ("algerian", "Algerian", "North African features"),
    ("tunisian", "Tunisian", "North African features"),
    ("lebanese", "Lebanese", "Levantine Arab features"),
    ("bahraini", "Bahraini", "Gulf Arab features, olive-brown complexion"),
    ("kuwaiti", "Kuwaiti", "Gulf Arab features, olive-brown complexion"),
    ("qatari", "Qatari", "Gulf Arab features, olive-brown complexion"),
    ("emirati", "Emirati", "Gulf Arab features, olive-brown complexion"),
    ("pakistani", "Pakistani", "South Asian features"),
    ("nigerian", "Nigerian", "West African features"),
    ("egyptian", "Egyptian", "North African features"),
    ("iranian", "Iranian", "Persian features"),
    ("turkish", "Turkish", "Turkish features"),
    ("chinese", "Chinese", "East Asian features"),
    ("japanese", "Japanese", "East Asian features"),
    ("korean", "Korean", "East Asian features"),
    ("indian", "Indian", "South Asian features"),
    ("mexican", "Mexican", "appearance matching the named Mexican identity"),
    ("brazilian", "Brazilian", "appearance matching the named Brazilian identity"),
    ("sudanese", "Sudanese", "Sudanese features"),
    ("jordanian", "Jordanian", "Levantine Arab features"),
    ("syrian", "Syrian", "Levantine Arab features"),
    ("yemeni", "Yemeni", "Arab features"),
    ("omani", "Omani", "Gulf Arab features, olive-brown complexion"),
    ("saudi", "Saudi", "Gulf Arab features, olive-brown complexion"),
    ("iraq", "Iraqi", "Arab features"),
    ("iraqi", "Iraqi", "Arab features"),
    ("iran", "Iranian", "Persian features"),
    ("egypt", "Egyptian", "North African features"),
    ("qatar", "Qatari", "Gulf Arab features, olive-brown complexion"),
    ("kuwait", "Kuwaiti", "Gulf Arab features, olive-brown complexion"),
    ("bahrain", "Bahraini", "Gulf Arab features, olive-brown complexion"),
    ("oman", "Omani", "Gulf Arab features, olive-brown complexion"),
    ("uae", "Emirati", "Gulf Arab features, olive-brown complexion"),
    ("china", "Chinese", "East Asian features"),
    ("japan", "Japanese", "East Asian features"),
    ("korea", "Korean", "East Asian features"),
    ("india", "Indian", "South Asian features"),
    ("kenya", "Kenyan", "East African features"),
    ("nigeria", "Nigerian", "West African features"),
    ("morocco", "Moroccan", "North African features"),
    ("algeria", "Algerian", "North African features"),
    ("tunisia", "Tunisian", "North African features"),
    ("lebanon", "Lebanese", "Levantine Arab features"),
    ("jordan", "Jordanian", "Levantine Arab features"),
    ("yemen", "Yemeni", "Arab features"),
    ("syria", "Syrian", "Levantine Arab features"),
    ("sudan", "Sudanese", "Sudanese features"),
    ("turkey", "Turkish", "Turkish features"),
    ("brazil", "Brazilian", "appearance matching the named Brazilian identity"),
    ("mexico", "Mexican", "appearance matching the named Mexican identity"),
    ("vietnam", "Vietnamese", "Southeast Asian features"),
    ("pakistan", "Pakistani", "South Asian features"),
)

_NATIONALITIES = tuple(sorted(_NATIONALITIES, key=lambda item: len(item[0]), reverse=True))

_ROLE_RE = re.compile(
    r"\b(officer|official|diplomat|minister|president|soldier|commander|"
    r"leader|delegate|king|queen|sheikh|emir|man|woman|person|worker|"
    r"engineer|doctor|teacher|student|fisherman|farmer|guard|aide|"
    r"executive|employee|civilian|pilot|driver|police)\b",
    re.IGNORECASE,
)
_FROM_RE = re.compile(r"\bfrom\s+(?:the\s+)?$", re.IGNORECASE)
_TOWARD_EXIT_RE = re.compile(
    r"\b(?:toward|towards|to)\s+(?:the\s+)?(exit|door|doorway|entrance|gate)\b",
    re.IGNORECASE,
)
_BLOCKING_PRESENT_RE = re.compile(
    r"\b(body\s+fac|receding|leaving\s+through|walking\s+out|"
    r"toward\s+that\s+door|faces\s+the\s+(?:exit|door)|"
    r"oriented\s+toward)\b",
    re.IGNORECASE,
)
_WORD_RE = re.compile(r"[A-Za-z]+")

# Positive appearance already in the prompt (demonym or region features).
_APPEARANCE_RE = re.compile(
    r"\b(emirati|saudi|qatari|kuwaiti|bahraini|omani|gulf\s+arab|"
    r"levantine|north\s+african|west\s+african|east\s+african|"
    r"east\s+asian|south\s+asian|southeast\s+asian|central\s+asian|"
    r"persian|iranian|turkish|egyptian|chinese|japanese|korean|"
    r"indian|pakistani|nigerian|kenyan|ethiopian|moroccan|"
    r"mexican|brazilian|filipino|vietnamese|indonesian|afghan|"
    r"olive-brown|olive\s+complexion|brown\s+complexion|"
    r"visible\s+\w+\s+features)\b",
    re.IGNORECASE,
)

ZIMAGE_RENDER_CONSTRAINTS = (
    "Sharp focus, clear air, crisp detail. "
    "No extra people, no text, no watermark, no logos."
)


def _word_bound(text: str, start: int, end: int) -> bool:
    if start > 0 and (text[start - 1].isalnum() or text[start - 1] == "_"):
        return False
    if end < len(text) and (text[end].isalnum() or text[end] == "_"):
        return False
    return True


def _find_nationality(text: str) -> Optional[Tuple[int, int, str, str]]:
    lower = text.lower()
    found: List[Tuple[int, int, int, str, str]] = []
    for phrase, demonym, appearance in _NATIONALITIES:
        start = 0
        while True:
            idx = lower.find(phrase, start)
            if idx < 0:
                break
            end = idx + len(phrase)
            if _word_bound(lower, idx, end):
                prefix = text[:idx]
                from_hit = 2 if _FROM_RE.search(prefix[-24:]) else 0
                role_hit = 1 if _ROLE_RE.search(text[max(0, idx - 48):end + 24]) else 0
                found.append((from_hit + role_hit, idx, end, demonym, appearance))
            start = idx + 1
    if not found:
        return None
    found.sort(key=lambda item: (-item[0], item[1]))
    _score, start, end, demonym, appearance = found[0]
    return start, end, demonym, appearance


def _has_matching_appearance(prompt: str, demonym: str) -> bool:
    if re.search(rf"\b{re.escape(demonym)}\b", prompt, re.IGNORECASE):
        return True
    return bool(_APPEARANCE_RE.search(prompt))


def identity_clause(demonym: str, appearance: str) -> str:
    return f"an adult {demonym} with {appearance}"


def identity_allowed_text(source: str) -> str:
    """Words Python may add for a named nationality; not extras in grounding."""
    match = _find_nationality(source or "")
    if not match:
        return ""
    _start, _end, demonym, appearance = match
    return f"{demonym} {appearance} adult"


def blocking_clause() -> str:
    return (
        "Body faces a glass exit doorway at the far side of the room and walks "
        "toward that door, receding from the camera, leaving the table behind"
    )


def apply_visual_identity(prompt: str, beat_text: str = "") -> str:
    """Insert visible nationality and exit-blocking when the source names them."""
    text = str(prompt or "").strip()
    if not text:
        return ""
    source = f"{beat_text} {text}".strip() if beat_text else text
    match = _find_nationality(source)
    if match:
        _start, _end, demonym, appearance = match
        if not _has_matching_appearance(text, demonym):
            clause = identity_clause(demonym, appearance)
            # Prefer weaving after the nationality span inside the prompt.
            local = _find_nationality(text)
            if local:
                _ls, le, _d, _a = local
                rest = text[le:]
                insert = f", {clause}"
                if rest and rest[0].isalnum():
                    insert += ","
                elif rest.startswith(" "):
                    insert += ","
                text = text[:le] + insert + rest
            else:
                text = join_prompt_parts(clause, text)
    if _TOWARD_EXIT_RE.search(source) and not _BLOCKING_PRESENT_RE.search(text):
        text = join_prompt_parts(text, blocking_clause())
    return text
