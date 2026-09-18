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
    "Identify camera-ready visual beats in narration. A beat is one frame a "
    "camera can point at: who or what is visible, what they are doing, and "
    "where. Commentary, statistics, motives, strategies, relationships, and "
    "'this shows that' claims are not beats.\n\n"
    "Never use a negative or absence sentence as a beat. 'It was not an "
    "Iranian drone', 'It was not a Russian weapon', and 'The UAE does not "
    "have a formal army' are explanations, not shots. Do not illustrate the "
    "thing being denied.\n\n"
    "Return one beat per distinct visual moment, at most the requested maximum. "
    "Any photographable subject counts: a person, animal, object, room, landscape, "
    "vehicle, or weather event. Do not limit beats to military or news imagery. "
    "A scene that names several visible things must return several beats. "
    "Returning fewer than the maximum is required when there are fewer visual "
    "moments. Never invent extra shots to fill the quota. Never pad with commentary.\n\n"
    "source_quote must be copied verbatim from the narration. Use one sentence "
    "or a short clause, never the whole paragraph, when the paragraph contains "
    "more than one visual moment. subject, action, setting, and objects must "
    "use only facts inside that quote, in the source language. If a fact is "
    "not in the quote, leave the field empty. These slots describe the locked "
    "image: subject = who/what is on camera, action = what is happening, "
    "setting = place or time of day, objects = visible props.\n\n"
    "beat is one English sentence that restates only those visible facts. "
    "Do not invent a person, prop, place, or action to symbolize an idea.\n\n"
    "Do not write image-model prompts, camera language, lighting, style, or "
    "wardrobe unless the quote itself names them. Never copy the entire "
    "narration into source_quote or beat. If the scene is only commentary, "
    "return an empty visual_beats list. If a sentence cannot be photographed "
    "as a still image, omit it. Political identity, costs, choices, standing, "
    "and strategy are not beats."
)

MAX_QUOTE_CHARS = 220
_CLAUSE_SPLIT_RE = re.compile(r"\s*;\s*|\s*:\s+|\s*,\s+and\s+", re.IGNORECASE)
_META_LEAD_RE = re.compile(
    r"^\s*(by the end of this video|let us (now )?(examine|start)|"
    r"you are going to understand)\b",
    re.IGNORECASE,
)

_NEGATION_CLAIM_RE = re.compile(
    r"\b(it\s+)?(was|were|is|are)\s+not\b"
    r"|\b(does|do|did|has|have)\s+not\b"
    r"|\b(has|have)\s+no\b"
    r"|\bnot\s+an?\b"
    r"|\bno\s+formal\b"
    r"|\bwithout\s+any\b",
    re.IGNORECASE,
)
_ABSTRACT_RE = re.compile(
    r"\b(relationship|implications?|strategy|strategic\s+assets?|master\s+plan|"
    r"options?|architecture|competition|competes?|political\s+cover|"
    r"goodwill|investments?|context\s+of\s+what|by\s+the\s+end\s+of\s+this\s+video|"
    r"understand\s+exactly|nobody\s+is\s+talking|let\s+us\s+start|"
    r"specific\s+context|represents\s+the|political identity|domestic standing|"
    r"strategic independence|first choice|second choice|higher costs?|"
    r"neutrality|diplomatic|institutional|qualitative|quantitative|"
    r"consolidation|observer|public information|financial competition|"
    r"dynamics|rivalry|threshold|broader pattern|period of stress|"
    r"political dynamics|internal competition)\b",
    re.IGNORECASE,
)
_EVALUATIVE_RE = re.compile(
    r"\b(more|less)\s+(sustainable|costly|expensive|difficult|valuable)\b"
    r"|\bpolitical identity\b"
    r"|\bdomestic standing\b"
    r"|\bstrategic independence\b"
    r"|\bthe first choice\b"
    r"|\bthe second choice\b"
    r"|\bas the leader who\b"
    r"|\bworth using\b"
    r"|\bread it as the specific message\b",
    re.IGNORECASE,
)
_VISIBLE_NOUNS = (
    # people and roles
    "man", "woman", "men", "women", "person", "people", "child", "children",
    "boy", "girl", "worker", "workers", "executive", "executives", "official",
    "officials", "officer", "officers", "president", "minister", "king", "queen",
    "soldier", "soldiers", "fighter", "fighters", "police", "doctor", "nurse",
    "teacher", "student", "engineer", "technician", "driver", "pilot", "farmer",
    "fisherman", "pescatore", "crowd", "audience", "crew", "staff", "leader",
    "leaders", "employee", "customer", "patient", "civilian", "troops",
    "commander", "commanders", "militia", "delegate", "delegates",
    # body
    "face", "faces", "hand", "hands", "head",
    # places
    "room", "office", "hall", "building", "buildings", "street", "road", "bridge",
    "city", "town", "village", "port", "pier", "molo", "harbor", "airport",
    "station", "factory", "plant", "farm", "farmland", "field", "desert",
    "forest", "river", "sea", "ocean", "beach", "mountain", "base", "bases",
    "camp", "hospital", "school", "church", "mosque", "temple", "market",
    "kitchen", "studio", "lab", "laboratory", "cleanroom", "warehouse", "dock",
    "corridor", "parliament", "court", "embassy", "palace", "stadium", "park",
    "garden", "boardroom", "classroom", "bedroom", "shop",
    # objects and vehicles
    "table", "desk", "chair", "computer", "laptop", "monitor", "screen", "phone",
    "car", "truck", "trucks", "vehicle", "vehicles", "bus", "train", "plane",
    "aircraft", "drone", "ship", "ships", "boat", "convoy", "tank", "gun",
    "weapon", "weapons", "missile", "missiles", "camera", "microphone", "podium",
    "book", "machine", "robot", "server", "chip", "wafer", "tool", "net", "reti",
    "uniform", "helmet", "rifle", "flag",
    # nature and time of day
    "tree", "trees", "animal", "bird", "fish", "horse", "water", "fire", "smoke",
    "cloud", "rain", "snow", "sun", "moon", "dawn", "sunrise", "alba", "night",
    "sky",
)
_VISIBLE_NOUN_RE = re.compile(
    r"\b(" + "|".join(_VISIBLE_NOUNS) + r")\b",
    re.IGNORECASE,
)
_ANALYSIS_TAIL_RE = re.compile(
    r"\s*,?\s*(that would have|that gulf state|which (?:means|represents|involves)|"
    r"because the|in ways that|rather than just|as (?:directly|part of) |"
    r"that saudi arabia's|that the broader|that no external)\b.*$",
    re.IGNORECASE,
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
    needed = len(tokens) if len(tokens) <= 2 else (len(tokens) * 2 + 2) // 3
    return hits >= needed


def split_sentences(text: str) -> List[str]:
    stripped = str(text or "").strip()
    if not stripped:
        return []
    return [part.strip() for part in _SENTENCE_SPLIT_RE.split(stripped) if part.strip()]


def split_clauses(text: str) -> List[str]:
    """Break a run-on paragraph into clauses a camera could isolate."""
    pieces: List[str] = []
    for sentence in split_sentences(text) or [str(text or "").strip()]:
        if not sentence:
            continue
        if len(sentence) < MAX_QUOTE_CHARS:
            pieces.append(sentence)
            continue
        parts = [part.strip(" ,;:") for part in _CLAUSE_SPLIT_RE.split(sentence) if part.strip()]
        if len(parts) >= 2:
            pieces.extend(part for part in parts if part)
        else:
            pieces.append(sentence)
    return pieces


def fallback_beat(narration: str) -> VisualBeat:
    sentences = split_sentences(narration)
    quote = (sentences[0] if sentences else str(narration or "").strip())
    return VisualBeat(beat=quote, source_quote=quote, source="fallback")


def compact_visual_quote(text: str, narration: str) -> str:
    """Keep the photographable clause and drop the analysis tail."""
    raw = str(text or "").strip()
    if not raw:
        return ""
    candidates = [raw]
    trimmed = _ANALYSIS_TAIL_RE.sub("", raw).strip(" ,;")
    if trimmed and trimmed != raw:
        candidates.append(trimmed)
    candidates.extend(split_clauses(raw))
    if len(raw) > MAX_QUOTE_CHARS:
        cut = raw[:MAX_QUOTE_CHARS].rsplit(" ", 1)[0].strip(" ,;")
        if cut:
            candidates.append(cut)
    seen = set()
    for candidate in candidates:
        candidate = candidate.strip()
        key = normalize_text(candidate)
        if not candidate or key in seen:
            continue
        seen.add(key)
        if not quote_in_narration(candidate, narration):
            continue
        if quote_is_too_broad(candidate, narration):
            continue
        if is_visual_moment(candidate):
            return candidate
    return ""


def fallback_beats(narration: str, limit: int = 3) -> List[VisualBeat]:
    """Use distinct visual clauses when Qwen returns nothing grounded.

    Long analysis sentences are compacted to the visible kernel. Scenes with
    no photographable noun still return [].
    """
    limit = max(1, int(limit))
    chosen: List[VisualBeat] = []
    seen = set()
    pieces = split_sentences(narration) + split_clauses(narration)
    for piece in pieces:
        kernel = compact_visual_quote(piece, narration)
        if not kernel:
            continue
        key = normalize_text(kernel)
        if key in seen:
            continue
        seen.add(key)
        chosen.append(VisualBeat(
            beat=kernel,
            source_quote=kernel,
            source="fallback",
        ))
        if len(chosen) >= limit:
            break
    return chosen


def is_visual_moment(text: str) -> bool:
    """True when a still photograph could depict the text without inventing a scene."""
    blob = str(text or "").strip()
    if not blob:
        return False
    if _META_LEAD_RE.search(blob):
        return False
    if _NEGATION_CLAIM_RE.search(blob):
        return False
    if _EVALUATIVE_RE.search(blob):
        return False
    visible_nouns = len(_VISIBLE_NOUN_RE.findall(blob))
    if visible_nouns == 0:
        return False
    abstract = len(_ABSTRACT_RE.findall(blob))
    if abstract > visible_nouns:
        return False
    return True


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


PENDING_PROMPT_SOURCES = {"pending", "user_added", "ungrounded"}
PROTECTED_PROMPT_SOURCES = {"manually_edited"}


def coerce_beat_index(value: Any, default: int = 0) -> int:
    """Parse a 1-based beat number; invalid values become default."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


def prompt_row_is_ready(row: Any) -> bool:
    """True when a prompt row is a finished Build Prompts result.

    Ungrounded/pending rows still have beat text and can be rendered; they
    are not 'ready' in the Prompts tab sense.
    """
    if not isinstance(row, dict):
        return False
    if not prompt_row_render_text(row):
        return False
    source = str(row.get("source") or "").strip()
    return source not in PENDING_PROMPT_SOURCES


def prompt_row_render_text(row: Any) -> str:
    """Text Comfy should paint: stored prompt, else generated_prompt."""
    if not isinstance(row, dict):
        return ""
    text = str(row.get("text") or "").strip()
    if text:
        return text
    return str(row.get("generated_prompt") or "").strip()


def prompt_row_can_render(row: Any) -> bool:
    """True when image stages should use this row instead of re-running Qwen."""
    return bool(prompt_row_render_text(row))


def prompt_rows_for_render(rows: Sequence[Any]) -> List[Dict[str, Any]]:
    """Copy prompt rows that have paint-able text, with ``text`` filled in."""
    rendered: List[Dict[str, Any]] = []
    for row in rows or []:
        text = prompt_row_render_text(row)
        if not text:
            continue
        item = dict(row)
        item["text"] = text
        rendered.append(item)
    return rendered


def find_prompt_row(rows: Sequence[Any], beat_index: int) -> Optional[Dict[str, Any]]:
    """Return the prompt dict for a 1-based beat without assuming list length.

    Prefer an explicit ``beat`` field. Fall back to list position only when that
    slot has no beat number of its own. Never raise IndexError.
    """
    target = coerce_beat_index(beat_index)
    if target <= 0:
        return None
    items = [row for row in (rows or []) if isinstance(row, dict)]
    for row in items:
        if coerce_beat_index(row.get("beat")) == target:
            return row
    if 1 <= target <= len(items):
        positional = items[target - 1]
        if coerce_beat_index(positional.get("beat")) == 0:
            return positional
    return None


def upsert_prompt_row(
    rows: Sequence[Any],
    row: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Replace or append a prompt row keyed by its beat number."""
    items = [item for item in (rows or []) if isinstance(item, dict)]
    beat_index = coerce_beat_index(row.get("beat"))
    if beat_index <= 0:
        items.append(dict(row))
        return items
    for index, item in enumerate(items):
        if coerce_beat_index(item.get("beat")) == beat_index:
            items[index] = dict(row)
            return items
    items.append(dict(row))
    items.sort(key=lambda item: coerce_beat_index(item.get("beat")))
    return items


def stub_prompt_row(
    scene_id: int,
    model_key: str,
    beat: VisualBeat,
    index: int,
) -> Dict[str, Any]:
    """Placeholder prompt so a beat appears on every model tab before Qwen runs."""
    text = str(beat.beat or beat.source_quote or "").strip()
    return {
        "id": f"scene_{int(scene_id):03d}_beat_{index:02d}_{model_key}",
        "beat": int(index),
        "visual_beat": beat.beat,
        "text": text,
        "source": "pending",
    }


def _row_for_beat(
    rows: Sequence[Dict[str, Any]],
    beat_index: int,
    used: set,
) -> Optional[Dict[str, Any]]:
    for row in rows:
        if id(row) in used:
            continue
        if coerce_beat_index(row.get("beat")) == beat_index:
            used.add(id(row))
            return row
    if 1 <= beat_index <= len(rows):
        positional = rows[beat_index - 1]
        if id(positional) not in used and coerce_beat_index(positional.get("beat")) == 0:
            used.add(id(positional))
            return positional
    return None


def _refresh_prompt_row(
    previous: Dict[str, Any],
    beat: VisualBeat,
    scene_id: int,
    model_key: str,
    index: int,
    *,
    update_pending_text: bool,
) -> Dict[str, Any]:
    updated = dict(previous)
    source = str(updated.get("source") or "").strip()
    old_lock = normalize_text(str(previous.get("visual_beat") or ""))
    new_lock = normalize_text(beat.beat)
    lock_changed = bool(old_lock) and old_lock != new_lock
    updated["beat"] = index
    updated["visual_beat"] = beat.beat
    updated["id"] = (
        str(updated.get("id") or "").strip()
        or f"scene_{int(scene_id):03d}_beat_{index:02d}_{model_key}"
    )
    if source in PROTECTED_PROMPT_SOURCES:
        return updated
    if lock_changed:
        updated["text"] = beat.beat
        updated["source"] = "pending"
        updated.pop("generated_prompt", None)
        updated.pop("grounding_error", None)
        return updated
    if update_pending_text and (source in PENDING_PROMPT_SOURCES or not source):
        updated["text"] = beat.beat
        updated["source"] = "pending"
    return updated


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
    used: set = set()
    for index, beat in enumerate(beats, 1):
        previous = _row_for_beat(rows, index, used)
        if previous is None:
            continue
        aligned.append(
            _refresh_prompt_row(
                previous, beat, scene_id, model_key, index, update_pending_text=False
            )
        )
    return aligned


def ensure_prompt_rows_for_beats(
    existing_rows: Sequence[Any],
    beats: Sequence[VisualBeat],
    scene_id: int,
    model_key: str,
) -> List[Dict[str, Any]]:
    """Keep matching prompt rows and insert stubs for beats the model is missing."""
    rows = [row for row in existing_rows if isinstance(row, dict)]
    aligned: List[Dict[str, Any]] = []
    used: set = set()
    for index, beat in enumerate(beats, 1):
        previous = _row_for_beat(rows, index, used)
        if previous is None:
            aligned.append(stub_prompt_row(scene_id, model_key, beat, index))
            continue
        aligned.append(
            _refresh_prompt_row(
                previous, beat, scene_id, model_key, index, update_pending_text=True
            )
        )
    return aligned


def sync_model_prompts_to_beats(
    models: Any,
    beats: Sequence[VisualBeat],
    scene_id: int,
    model_keys: Sequence[str],
) -> Dict[str, Any]:
    """Copy the shared beat list onto every model so Prompts tabs stay in sync."""
    existing = models if isinstance(models, dict) else {}
    updated: Dict[str, Any] = {}
    for model_key, value in existing.items():
        if model_key not in model_keys:
            updated[model_key] = value
    for model_key in model_keys:
        entry = existing.get(model_key)
        if not isinstance(entry, dict):
            entry = {}
        existing_rows = entry.get("prompts", [])
        if not isinstance(existing_rows, list):
            existing_rows = []
        updated[model_key] = {
            "profile": entry.get("profile") or f"{model_key}.yaml",
            "prompts": ensure_prompt_rows_for_beats(
                existing_rows,
                beats,
                scene_id,
                model_key,
            ),
            "max_prompts_per_scene": max(
                int(entry.get("max_prompts_per_scene") or len(beats) or 3),
                len(beats),
            ),
        }
    return updated


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


def recover_source_quote(quote: str, narration: str) -> str:
    """Return a verbatim narration span for a quote, or empty if ungrounded."""
    raw = str(quote or "").strip()
    if quote_in_narration(raw, narration):
        return raw
    quote_tokens = set(content_tokens(raw))
    if not quote_tokens:
        return ""
    best = ""
    best_score = 0
    for sentence in split_sentences(narration):
        sentence_tokens = set(content_tokens(sentence))
        if not sentence_tokens:
            continue
        overlap = len(quote_tokens & sentence_tokens)
        needed = max(1, (len(quote_tokens) + 1) // 2)
        if overlap >= needed and overlap > best_score:
            best = sentence
            best_score = overlap
    if best and quote_in_narration(best, narration):
        return best
    return ""


def quote_is_too_broad(quote: str, narration: str) -> bool:
    """A beat quote must be one short clause, not the whole scene."""
    normalized_quote = normalize_text(quote)
    normalized_narration = normalize_text(narration)
    if not normalized_quote:
        return False
    if len(split_sentences(quote)) > 1:
        return True
    if len(quote.strip()) > MAX_QUOTE_CHARS:
        return True
    if not normalized_narration:
        return False
    if normalized_quote == normalized_narration and len(normalized_narration) > 120:
        return True
    if len(normalized_narration) > 160 and len(normalized_quote) >= int(0.55 * len(normalized_narration)):
        return True
    return False


def split_raw_beat_item(item: Any, narration: str) -> List[Dict[str, Any]]:
    """Turn a whole-paragraph Qwen quote into one candidate per clause."""
    beat = parse_raw_beat(item)
    if beat is None:
        return []
    text = beat.source_quote.strip() or beat.beat.strip()
    pieces = split_sentences(text)
    if len(pieces) <= 1:
        pieces = split_clauses(text)
    if len(pieces) <= 1:
        return [beat.to_dict()]
    rows: List[Dict[str, Any]] = []
    for piece in pieces:
        if not quote_in_narration(piece, narration):
            continue
        rows.append({
            "beat": piece,
            "source_quote": piece,
            "subject": "",
            "action": "",
            "setting": "",
            "objects": [],
            "source": beat.source,
        })
    return rows or [beat.to_dict()]


def validate_beat(item: Any, narration: str) -> Optional[VisualBeat]:
    beat = parse_raw_beat(item)
    if beat is None:
        return None
    quote = recover_source_quote(
        beat.source_quote.strip() or beat.beat.strip(),
        narration,
    )
    if not quote:
        return None
    compacted = compact_visual_quote(quote, narration) or compact_visual_quote(beat.beat, narration)
    if not compacted:
        return None
    beat.source_quote = compacted
    if not beat.beat.strip() or quote_is_too_broad(beat.beat, narration) or not is_visual_moment(beat.beat):
        beat.beat = compacted
    return _clean_slots(beat)


def quotes_are_same_moment(left: str, right: str) -> bool:
    """True when one quote is only a small extension of the other."""
    a = normalize_text(left)
    b = normalize_text(right)
    if not a or not b:
        return False
    if a == b:
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if shorter not in longer:
        return False
    return len(shorter) >= int(0.6 * len(longer))


def dedupe_beats(beats: Sequence[VisualBeat]) -> List[VisualBeat]:
    kept: List[VisualBeat] = []
    for beat in beats:
        quote = normalize_text(beat.source_quote or beat.beat)
        if not quote:
            continue
        replaced = False
        for index, existing in enumerate(kept):
            existing_quote = existing.source_quote or existing.beat
            if quotes_are_same_moment(quote, existing_quote):
                if len(quote) > len(normalize_text(existing_quote)):
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
    expanded: List[Any] = []
    for item in list(raw_items):
        expanded.extend(split_raw_beat_item(item, narration))
    for item in expanded[: max(limit * 3, limit)]:
        beat = validate_beat(item, narration)
        if beat is not None:
            accepted.append(beat)
    accepted = dedupe_beats(accepted)
    sentences = split_sentences(narration)
    short_single_sentence = (
        len(sentences) <= 1
        and len(str(narration or "").strip()) < 180
        and len(accepted) > 1
    )
    if short_single_sentence:
        accepted = accepted[:1]
    if not accepted:
        accepted = fallback_beats(narration, limit)
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
            "Omit any fact not present in the quote. Reply with JSON only: "
            '{"visual_beats":[{"source_quote":"","subject":"","action":"",'
            '"setting":"","objects":[],"beat":""}]}'
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

    from prompts.ollama_runtime import chat_json_object

    raw_items: List[Any] = []
    try:
        payload = chat_json_object(
            host=ollama_host,
            model=ollama_model,
            messages=build_extraction_messages(scene, limit, extra_system),
            options={"temperature": 0.0, "top_p": 0.8},
        )
        raw_items = payload.get("visual_beats") or []
        if not isinstance(raw_items, list):
            raw_items = []
    except Exception as exc:
        logger.exception("Visual beat extraction failed for scene %s", scene.get("id"))
        raise RuntimeError(
            f"Qwen beat extraction failed for scene {scene.get('id')}: {exc}"
        ) from exc

    beats = validate_extracted_beats(raw_items, narration, limit)
    if not beats:
        logger.warning("No grounded visual beats survived validation; using fallback sentences")
        return fallback_beats(narration, limit)
    return beats
