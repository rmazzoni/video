import os
import re
from typing import Optional


class TranscriptLoader:
    """
    Loads narration text from various formats:
    - .txt (plain text)
    - .srt (subtitle format)
    - .vtt (web subtitle format)
    - raw text passed directly
    """

    def __init__(self, strip_timestamps: bool = True):
        """
        :param strip_timestamps: remove SRT/VTT timestamps if present
        """
        self.strip_timestamps = strip_timestamps

    # ---------------------------------------------------------
    # PUBLIC API
    # ---------------------------------------------------------

    def load(self, path_or_text: str) -> str:
        """
        Loads narration from a file path or raw text.
        Automatically detects file type.
        """

        if os.path.exists(path_or_text):
            ext = os.path.splitext(path_or_text)[1].lower()

            if ext == ".txt":
                return self._load_txt(path_or_text)

            if ext == ".srt":
                return self._load_srt(path_or_text)

            if ext == ".vtt":
                return self._load_vtt(path_or_text)

            raise ValueError(f"Unsupported transcript format: {ext}")

        # If it's not a file, treat it as raw text
        return self._clean_text(path_or_text)

    # ---------------------------------------------------------
    # LOADERS
    # ---------------------------------------------------------

    def _load_txt(self, path: str) -> str:
        with open(path, "r", encoding="utf-8") as f:
            return self._clean_text(f.read())

    def _load_srt(self, path: str) -> str:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        if self.strip_timestamps:
            content = self._remove_srt_timestamps(content)

        return self._clean_text(content)

    def _load_vtt(self, path: str) -> str:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        # Remove WEBVTT header
        content = re.sub(r"^WEBVTT.*\n", "", content, flags=re.IGNORECASE)

        if self.strip_timestamps:
            content = self._remove_vtt_timestamps(content)

        return self._clean_text(content)

    # ---------------------------------------------------------
    # CLEANING HELPERS
    # ---------------------------------------------------------

    def _remove_srt_timestamps(self, text: str) -> str:
        # Remove lines like: 00:00:01,000 --> 00:00:04,000
        return re.sub(r"\d{2}:\d{2}:\d{2},\d{3} --> .*", "", text)

    def _remove_vtt_timestamps(self, text: str) -> str:
        # Remove lines like: 00:00:01.000 --> 00:00:04.000
        return re.sub(r"\d{2}:\d{2}:\d{2}\.\d{3} --> .*", "", text)

    def _clean_text(self, text: str) -> str:
        # Remove numbering (SRT sequence numbers on their own line)
        text = re.sub(r"^\d+\s*$", "", text, flags=re.MULTILINE)

        # Collapse newlines: a newline that is NOT preceded by sentence-ending
        # punctuation (. ! ?) means the sentence continues — join with a space.
        # A newline after sentence-ending punctuation starts a new sentence.
        text = re.sub(r"([^.!?])\n+", r"\1 ", text)
        text = re.sub(r"([.!?])\n+", r"\1\n", text)

        # Collapse multiple spaces
        text = re.sub(r"[ \t]+", " ", text)

        # Remove blank lines left over
        text = re.sub(r"\n{2,}", "\n", text)

        return text.strip()
