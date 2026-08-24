"""Sanitization helpers for text returned by local prompt-generation models."""

import re


_LEAK_MARKERS = (
    "Script Segment",
    "Narration:",
    "User:",
)


def sanitize_generated_prompt(raw_text: str) -> str:
    """Return only generated visual prose, without wrappers or echoed input blocks."""
    prompt = str(raw_text or "").strip()

    if "PROMPT_START:" in prompt:
        prompt = prompt.rsplit("PROMPT_START:", 1)[-1].strip()

    prompt = prompt.strip().strip('"\'').strip()

    marker_positions = [
        match.start()
        for marker in _LEAK_MARKERS
        if (match := re.search(rf"(?:^|\n)\s*{re.escape(marker)}", prompt, re.IGNORECASE))
    ]
    if marker_positions:
        prompt = prompt[:min(marker_positions)].strip()

    return prompt.strip().strip('"\'').strip()
