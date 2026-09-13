"""Grounded visual-beat extraction for local Qwen.

A beat is a camera-ready moment already present in the narration. Extraction
asks Qwen for a verbatim source quote plus structured slots, then Python
rejects anything that is not entailed by that quote.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

logger = logging.getLogger(__name__)

BEAT_RESPONSE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "visual_beats": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source_quote": {"type": "string"},
                    "subject": {"type": "string"},
                    "action": {"type": "string"},
                    "setting": {"type": "string"},
                    "objects": {"type": "array", "items": {"type": "string"}},
                    "beat": {"type": "string"},
                },
                "required": [
                    "source_quote",
                    "subject",
                    "action",
                    "setting",
                    "objects",
                    "beat",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["visual_beats"],
    "additionalProperties": False,
}

EXTRACT_SYSTEM_PROMPT = (
    "Identify camera-ready visual beats in narration. A beat is something a "
    "camera can see: a subject, an action, a place, or an object. Commentary, "
    "statistics, motives, and 'this shows that' claims are not beats.\n\n"
    "Return only as many beats as there are distinct visual moments, at most "
    "the requested maximum. Returning fewer than the maximum is required when "
    "the narration has fewer visual moments. Never invent extra shots to fill "
    "the quota. Never pad.\n\n"
    "source_quote must be copied verbatim from the narration. subject, action, "
    "setting, and objects must use only facts inside that quote, in the source "
    "language. If a fact is not in the quote, leave the field empty.\n\n"
    "beat is one English sentence that restates only those facts. If the "
    "paragraph is abstract, pick the single most concrete stated fact. Do not "
    "invent a person, prop, place, or action to symbolize an idea.\n\n"
    "Do not write image-model prompts, camera language, lighting, style, or "
    "wardrobe unless the quote itself names them."
)

_TOKEN_RE = re.compile(r"[0-9]+|[^\W\d_]+", re.UNICODE)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_APOS_RE = str.maketrans({
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
})

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "into",
    "is", "it", "of", "on", "or", "that", "the", "this", "to", "was", "were",
    "with", "al", "alla", "che", "con", "da", "dal", "dei", "del", "della",
    "delle", "di", "e", "gli", "i", "il", "la", "le", "lo", "nel", "nella",
    "nei", "nelle", "per", "su", "tra", "fra", "un", "una", "uno",
}


@dataclass
class VisualBeat:
    beat: str
    source_quote: str = ""
    subject: str = ""
    action: str = ""
    setting: str = ""
    objects: List[str] = field(default_factory=list)
    source: str = "generated"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "beat": self.beat,
            "source_quote": self.source_quote,
            "subject": self.subject,
            "action": self.action,
            "setting": self.setting,
            "objects": list(self.objects),
            "source": self.source,
        }

    @classmethod
    def from_stored(cls, value: Any) -> Optional["VisualBeat"]:
        if isinstance(value, VisualBeat):
            return value
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            return cls(beat=text, source_quote=text)
        if isinstance(value, dict):
            beat = str(value.get("beat") or value.get("visual_beat") or "").strip()
            quote = str(value.get("source_quote") or "").strip()
            if not beat and not quote:
                return None
            raw_objects = value.get("objects") or []
            if not isinstance(raw_objects, list):
                raw_objects = [raw_objects] if raw_objects else []
            source = str(value.get("source") or "generated").strip() or "generated"
            return cls(
                beat=beat or quote,
                source_quote=quote,
                subject=str(value.get("subject") or "").strip(),
                action=str(value.get("action") or "").strip(),
                setting=str(value.get("setting") or "").strip(),
                objects=[str(item).strip() for item in raw_objects if str(item).strip()],
                source=source,
            )
        return None


def normalize_text(text: str) -> str:
    return " ".join(str(text or "").translate(_APOS_RE).casefold().split())


def quote_in_narration(quote: str, narration: str) -> bool:
    normalized_quote = normalize_text(quote)
    normalized_narration = normalize_text(narration)
    return bool(normalized_quote) and normalized_quote in normalized_narration


def content_tokens(text: str, min_length: int = 3) -> List[str]:
    tokens = []
    for match in _TOKEN_RE.findall(str(text or "")):
        token = match.casefold()
        if len(token) < min_length or token in _STOPWORDS:
            continue
        tokens.append(token)
    return tokens


def slot_is_grounded(slot: str, quote: str) -> bool:
    tokens = content_tokens(slot)
    if not tokens:
        return True
    quote_tokens = set(content_tokens(quote))
    hits = sum(1 for token in tokens if token in quote_tokens)
    return hits >= max(1, (len(tokens) + 1) // 2)


def split_sentences(text: str) -> List[str]:
    stripped = str(text or "").strip()
    if not stripped:
        return []
    return [part.strip() for part in _SENTENCE_SPLIT_RE.split(stripped) if part.strip()]


def fallback_beat(narration: str) -> VisualBeat:
    sentences = split_sentences(narration)
    quote = (sentences[0] if sentences else str(narration or "").strip())
    return VisualBeat(beat=quote, source_quote=quote)


def normalize_stored_beats(raw: Any) -> List[VisualBeat]:
    if raw is None:
        return []
    if isinstance(raw, (str, dict, VisualBeat)):
        items: Iterable[Any] = [raw]
    elif isinstance(raw, Sequence):
        items = raw
    else:
        return []
    beats: List[VisualBeat] = []
    for item in items:
        beat = VisualBeat.from_stored(item)
        if beat is not None:
            beats.append(beat)
    return beats


def beats_as_dicts(beats: Sequence[VisualBeat]) -> List[Dict[str, Any]]:
    return [beat.to_dict() for beat in beats]


def align_prompt_rows_to_beats(
    existing_rows: Sequence[Any],
    beats: Sequence[VisualBeat],
    scene_id: int,
    model_key: str,
) -> List[Dict[str, Any]]:
    """Keep existing prompt rows that still match a beat index; drop extras.

    Missing beats are left ungenerated so Build Prompts / Regenerate Prompt
    can fill them after the user reviews the new shot list.
    """
    rows = [row for row in existing_rows if isinstance(row, dict)]
    aligned: List[Dict[str, Any]] = []
    for index, beat in enumerate(beats, 1):
        previous = next(
            (row for row in rows if int(row.get("beat", 0) or 0) == index),
            None,
        )
        if previous is None:
            continue
        updated = dict(previous)
        updated["beat"] = index
        updated["visual_beat"] = beat.beat
        updated["id"] = (
            str(updated.get("id") or "").strip()
            or f"scene_{int(scene_id):03d}_beat_{index:02d}_{model_key}"
        )
        aligned.append(updated)
    return aligned


def parse_raw_beat(item: Any) -> Optional[VisualBeat]:
    return VisualBeat.from_stored(item)


def _clean_slots(beat: VisualBeat) -> VisualBeat:
    quote = beat.source_quote
    subject = beat.subject if slot_is_grounded(beat.subject, quote) else ""
    action = beat.action if slot_is_grounded(beat.action, quote) else ""
    setting = beat.setting if slot_is_grounded(beat.setting, quote) else ""
    objects = [item for item in beat.objects if slot_is_grounded(item, quote)]
    english = str(beat.beat or "").strip()
    if not any((subject, action, setting, objects)):
        english = quote
    return VisualBeat(
        beat=english or quote,
        source_quote=quote,
        subject=subject,
        action=action,
        setting=setting,
        objects=objects,
        source=beat.source or "generated",
    )


def validate_beat(item: Any, narration: str) -> Optional[VisualBeat]:
    beat = parse_raw_beat(item)
    if beat is None:
        return None
    quote = beat.source_quote.strip() or beat.beat.strip()
    if not quote_in_narration(quote, narration):
        return None
    beat.source_quote = quote
    if not beat.beat.strip():
        beat.beat = quote
    return _clean_slots(beat)


def dedupe_beats(beats: Sequence[VisualBeat]) -> List[VisualBeat]:
    kept: List[VisualBeat] = []
    for beat in beats:
        quote = normalize_text(beat.source_quote or beat.beat)
        if not quote:
            continue
        replaced = False
        for index, existing in enumerate(kept):
            existing_quote = normalize_text(existing.source_quote or existing.beat)
            if quote == existing_quote or quote in existing_quote or existing_quote in quote:
                if len(quote) > len(existing_quote):
                    kept[index] = beat
                replaced = True
                break
        if not replaced:
            kept.append(beat)
    return kept


def validate_extracted_beats(
    raw_items: Sequence[Any],
    narration: str,
    limit: int,
) -> List[VisualBeat]:
    limit = max(1, int(limit))
    accepted: List[VisualBeat] = []
    for item in list(raw_items)[:limit]:
        beat = validate_beat(item, narration)
        if beat is not None:
            accepted.append(beat)
    accepted = dedupe_beats(accepted)
    if len(split_sentences(narration)) <= 1 and len(accepted) > 1:
        accepted = accepted[:1]
    if not accepted:
        fallback = fallback_beat(narration)
        if fallback.source_quote:
            accepted = [fallback]
    return accepted[:limit]


def build_extraction_messages(
    scene: Dict[str, Any],
    limit: int,
    extra_system: str = "",
) -> List[Dict[str, str]]:
    system = EXTRACT_SYSTEM_PROMPT
    extra = str(extra_system or "").strip()
    if extra:
        system = f"{system}\n\n{extra}"
    user = json.dumps({
        "scene_id": int(scene.get("id") or 0),
        "narration": str(scene.get("text") or "").strip(),
        "maximum_visual_beats": int(limit),
        "instructions": (
            "Copy source_quote verbatim. Do not pad to the maximum. "
            "Omit any fact not present in the quote."
        ),
    }, ensure_ascii=False)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def extract_structured_beats(
    scene: Dict[str, Any],
    *,
    ollama_model: str,
    ollama_host: str,
    max_visual_beats: Optional[int] = None,
    extra_system: str = "",
) -> List[VisualBeat]:
    narration = str(scene.get("text") or "").strip()
    limit = max(1, int(max_visual_beats or 3))
    if not narration:
        return []

    raw_items: List[Any] = []
    try:
        import ollama

        client = ollama.Client(host=ollama_host)
        response = client.chat(
            model=ollama_model,
            format=BEAT_RESPONSE_SCHEMA,
            options={"temperature": 0.1, "top_p": 0.8},
            messages=build_extraction_messages(scene, limit, extra_system),
        )
        message = getattr(response, "message", None)
        content = (
            getattr(message, "content", "")
            if message is not None
            else response["message"]["content"]
        )
        payload = json.loads(content)
        raw_items = payload.get("visual_beats") or []
        if not isinstance(raw_items, list):
            raw_items = []
    except Exception:
        logger.exception("Visual beat extraction failed; using fallback beat")
        return [fallback_beat(narration)]

    beats = validate_extracted_beats(raw_items, narration, limit)
    if not beats:
        logger.warning("No grounded visual beats survived validation; using fallback")
        return [fallback_beat(narration)]
    return beats
