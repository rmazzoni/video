"""Persist manual beat corrections so later Qwen extractions can learn from them."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

import yaml

from prompts.visual_beats import VisualBeat

FEEDBACK_FILENAME = "beat_corrections.yaml"
MAX_EXAMPLES = 4


def feedback_path(output_dir: str) -> str:
    return os.path.join(output_dir, FEEDBACK_FILENAME)


def empty_feedback() -> Dict[str, Any]:
    return {
        "extraction_notes": "",
        "include_examples": True,
        "examples": [],
    }


def load_beat_feedback(output_dir: str) -> Dict[str, Any]:
    path = feedback_path(output_dir)
    data = empty_feedback()
    if not os.path.exists(path):
        return data
    try:
        with open(path, encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
    except Exception:
        return data
    if not isinstance(loaded, dict):
        return data
    data["extraction_notes"] = str(loaded.get("extraction_notes") or "").strip()
    data["include_examples"] = bool(loaded.get("include_examples", True))
    examples = loaded.get("examples") or []
    if isinstance(examples, list):
        data["examples"] = [item for item in examples if isinstance(item, dict)]
    return data


def save_beat_feedback(output_dir: str, feedback: Dict[str, Any]) -> str:
    os.makedirs(output_dir, exist_ok=True)
    payload = {
        "extraction_notes": str(feedback.get("extraction_notes") or "").strip(),
        "include_examples": bool(feedback.get("include_examples", True)),
        "examples": list(feedback.get("examples") or []),
    }
    path = feedback_path(output_dir)
    with open(path, "w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, allow_unicode=True, sort_keys=False)
    return path


def _beat_signature(beat: Any) -> tuple:
    parsed = VisualBeat.from_stored(beat)
    if parsed is None:
        return ("", "", "", "", "")
    objects = tuple(sorted(item.casefold() for item in parsed.objects))
    return (
        parsed.beat.strip(),
        parsed.source_quote.strip(),
        parsed.subject.strip(),
        parsed.action.strip(),
        parsed.setting.strip(),
        objects,
    )


def beats_differ(original: Any, corrected: Any) -> bool:
    return _beat_signature(original) != _beat_signature(corrected)


def record_correction(
    feedback: Dict[str, Any],
    *,
    scene_id: int,
    narration: str,
    original: Any,
    corrected: Any,
) -> bool:
    """Prepend a correction example. Returns True if a new example was stored."""
    if not beats_differ(original, corrected):
        return False
    original_beat = VisualBeat.from_stored(original)
    corrected_beat = VisualBeat.from_stored(corrected)
    if corrected_beat is None:
        return False
    example = {
        "scene_id": int(scene_id),
        "narration": str(narration or "").strip(),
        "original": original_beat.to_dict() if original_beat is not None else {},
        "corrected": corrected_beat.to_dict(),
        "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    examples: List[Dict[str, Any]] = [
        item for item in list(feedback.get("examples") or [])
        if isinstance(item, dict)
    ]
    signature = (
        example["scene_id"],
        example["narration"],
        _beat_signature(example["original"]),
        _beat_signature(example["corrected"]),
    )
    examples = [
        item for item in examples
        if (
            int(item.get("scene_id") or 0),
            str(item.get("narration") or "").strip(),
            _beat_signature(item.get("original")),
            _beat_signature(item.get("corrected")),
        ) != signature
    ]
    examples.insert(0, example)
    feedback["examples"] = examples[:MAX_EXAMPLES]
    return True


def format_correction_examples(examples: Optional[Sequence[Dict[str, Any]]]) -> str:
    if not examples:
        return ""
    blocks = []
    for index, item in enumerate(list(examples)[:MAX_EXAMPLES], 1):
        if not isinstance(item, dict):
            continue
        original = item.get("original") or {}
        corrected = item.get("corrected") or {}
        narration = str(item.get("narration") or "").strip()
        lines = [f"Example {index}:"]
        if narration:
            lines.append(f"Narration: {narration}")
        if original:
            lines.append(
                "Rejected extraction: "
                f"quote={original.get('source_quote', '')!r}; "
                f"beat={original.get('beat', '')!r}; "
                f"subject={original.get('subject', '')!r}; "
                f"action={original.get('action', '')!r}; "
                f"setting={original.get('setting', '')!r}; "
                f"objects={original.get('objects', [])!r}"
            )
        lines.append(
            "User correction (prefer this style of quote and English restatement): "
            f"quote={corrected.get('source_quote', '')!r}; "
            f"beat={corrected.get('beat', '')!r}; "
            f"subject={corrected.get('subject', '')!r}; "
            f"action={corrected.get('action', '')!r}; "
            f"setting={corrected.get('setting', '')!r}; "
            f"objects={corrected.get('objects', [])!r}"
        )
        blocks.append("\n".join(lines))
    if not blocks:
        return ""
    return (
        "LEARN FROM THESE USER CORRECTIONS. Copy their quote-selection and "
        "English restatement style. Do not copy their content into other scenes.\n\n"
        + "\n\n".join(blocks)
    )


def extract_guidance_text(
    notes: str = "",
    examples: Optional[Sequence[Dict[str, Any]]] = None,
    include_examples: bool = True,
) -> str:
    parts: List[str] = []
    notes_text = str(notes or "").strip()
    if notes_text:
        parts.append("PROJECT BEAT NOTES (follow these preferences):\n" + notes_text)
    if include_examples:
        formatted = format_correction_examples(examples)
        if formatted:
            parts.append(formatted)
    return "\n\n".join(parts)
