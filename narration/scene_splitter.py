import re
from typing import List, Dict


class SceneSplitter:
    """
    Splits narration text into scenes using different strategies.
    Default: sentence-based splitting.
    """

    def __init__(self, min_sentence_length: int = 20):
        """
        :param min_sentence_length: minimum number of characters for a sentence
        to be considered a scene (filters out noise like "Yes." or "Okay.")
        """
        self.min_sentence_length = min_sentence_length

    # ---------------------------------------------------------
    # PUBLIC API
    # ---------------------------------------------------------

    def split_into_scenes(self, text: str, method: str = "paragraph") -> List[Dict]:
        """
        Main entry point.
        :param text: narration text
        :param method: "sentence", "semantic", or "timed"
        :return: list of scene dicts
        """
        text = text.strip()

        if method == "paragraph":
            scenes = self._split_by_paragraph(text)
        elif method == "sentence":
            scenes = self._split_by_sentence(text)
        elif method == "semantic":
            scenes = self._split_by_semantic(text)
        elif method == "timed":
            scenes = self._split_by_timing(text)
        else:
            raise ValueError(f"Unknown scene splitting method: {method}")

        # Normalize scene objects
        return [
            {
                "id": i + 1,
                "text": scene.strip(),
            }
            for i, scene in enumerate(scenes)
            if len(scene.strip()) >= self.min_sentence_length
        ]

    # ---------------------------------------------------------
    # PARAGRAPH SPLITTING
    # ---------------------------------------------------------

    def _split_by_paragraph(self, text: str) -> List[str]:
        """
        Splits on blank lines. Adjacent short paragraphs (under
        min_sentence_length characters) are merged with the next one
        so each scene has enough context for image generation.
        """
        raw = re.split(r"\n{2,}", text)
        raw = [p.replace("\n", " ").strip() for p in raw if p.strip()]

        merged: List[str] = []
        buffer = ""
        for para in raw:
            if buffer:
                buffer = buffer + " " + para
            else:
                buffer = para
            if len(buffer) >= self.min_sentence_length:
                merged.append(buffer)
                buffer = ""
        if buffer:
            if merged:
                merged[-1] = merged[-1] + " " + buffer
            else:
                merged.append(buffer)
        return merged

    # ---------------------------------------------------------
    # SENTENCE SPLITTING
    # ---------------------------------------------------------

    def _split_by_sentence(self, text: str) -> List[str]:
        """
        Splits text into sentences using punctuation.
        """
        # Regex: split on . ! ? but keep punctuation
        raw_sentences = re.split(r'(?<=[.!?])\s+', text)

        # Clean up whitespace
        return [s.strip() for s in raw_sentences if s.strip()]

    # ---------------------------------------------------------
    # SEMANTIC SPLITTING (placeholder for future expansion)
    # ---------------------------------------------------------

    def _split_by_semantic(self, text: str) -> List[str]:
        """
        Placeholder for semantic scene detection.
        Later you can integrate:
        - sentence embeddings
        - clustering
        - topic segmentation
        """
        # For now, fallback to sentence-based
        return self._split_by_sentence(text)

    # ---------------------------------------------------------
    # TIMED SPLITTING (placeholder for future expansion)
    # ---------------------------------------------------------

    def _split_by_timing(self, text: str, seconds_per_scene: int = 5) -> List[str]:
        """
        Placeholder for time-based splitting.
        Later you can integrate:
        - narration duration
        - CPS (characters per second)
        - segment timing from your dubbing pipeline
        """
        # For now, fallback to sentence-based
        return self._split_by_sentence(text)
