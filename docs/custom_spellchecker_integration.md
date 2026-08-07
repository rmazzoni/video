# Reusable Italian Spell Checker

This example adds an Italian spell checker to a PyQt6 `QPlainTextEdit`. It supports:

- A UTF-8 custom-word file with comments and blank lines.
- Case-insensitive Unicode matching.
- Automatic duplicate removal while preserving comments and the first spelling.
- Adding a selected or right-clicked word through the standard context menu.
- Italian elisions such as `sull'Iran`, `dell'Italia`, and `un'amica`.

## Dependencies

```powershell
pip install PyQt6 pyspellchecker
```

## Reusable implementation

```python
import os
import re
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import QMessageBox, QPlainTextEdit
from spellchecker import SpellChecker


class CustomSpellHighlighter(QSyntaxHighlighter):
    ITALIAN_ELISIONS = {
        "all", "bell", "c", "coll", "d", "dall", "dell", "gl", "l",
        "m", "n", "nell", "quest", "quell", "s", "senz", "sott", "sull",
        "t", "un",
    }
    WORD_PATTERN = re.compile(
        r"[A-Za-zÀ-ÖØ-öø-ÿ]+(?:['’][A-Za-zÀ-ÖØ-öø-ÿ]+)?"
    )

    def __init__(self, document, dictionary_path: str | Path, language: str = "it"):
        super().__init__(document)
        self.dictionary_path = Path(dictionary_path)
        self.custom_words: set[str] = set()
        self.checker = SpellChecker(language=language)

        self.error_format = QTextCharFormat()
        self.error_format.setUnderlineStyle(
            QTextCharFormat.UnderlineStyle.SpellCheckUnderline
        )
        self.error_format.setUnderlineColor(QColor("#FF5555"))
        self.reload_dictionary()

    def load_and_deduplicate(self) -> set[str]:
        """Load words and remove case-insensitive duplicate lines in place."""
        if not self.dictionary_path.exists():
            return set()

        lines = self.dictionary_path.read_text(encoding="utf-8-sig").splitlines()
        words: set[str] = set()
        cleaned_lines: list[str] = []

        for line in lines:
            # Text after # is treated as a comment.
            word = line.split("#", 1)[0].strip()
            normalized = word.casefold()
            if word and normalized in words:
                continue
            cleaned_lines.append(line)
            if word:
                words.add(normalized)

        if cleaned_lines != lines:
            cleaned_text = "\n".join(cleaned_lines).rstrip() + "\n"
            self.dictionary_path.write_text(cleaned_text, encoding="utf-8")

        return words

    def add_custom_word(self, word: str) -> bool:
        """Append a word at the end; return False when it already exists."""
        word = word.strip()
        normalized = word.casefold()
        self.custom_words = self.load_and_deduplicate()
        if not normalized or normalized in self.custom_words:
            return False

        self.dictionary_path.parent.mkdir(parents=True, exist_ok=True)
        needs_newline = (
            self.dictionary_path.exists()
            and self.dictionary_path.stat().st_size > 0
        )

        with self.dictionary_path.open("a", encoding="utf-8") as output:
            if needs_newline:
                with self.dictionary_path.open("rb") as source:
                    source.seek(-1, os.SEEK_END)
                    if source.read(1) not in (b"\n", b"\r"):
                        output.write("\n")
            output.write(word + "\n")

        self.custom_words.add(normalized)
        self.checker.word_frequency.load_words([normalized])
        self.rehighlight()
        return True

    def reload_dictionary(self) -> None:
        self.custom_words = self.load_and_deduplicate()
        if self.custom_words:
            self.checker.word_frequency.load_words(self.custom_words)
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:
        for match in self.WORD_PATTERN.finditer(text):
            token = match.group()
            parts = re.split(r"['’]", token, maxsplit=1)
            checked_word = token
            offset = 0

            if len(parts) == 2 and parts[0].casefold() in self.ITALIAN_ELISIONS:
                checked_word = parts[1]
                offset = len(parts[0]) + 1

            is_custom = checked_word.casefold() in self.custom_words
            if not is_custom and self.checker.unknown([checked_word]):
                self.setFormat(
                    match.start() + offset,
                    len(checked_word),
                    self.error_format,
                )


def attach_dictionary_menu(
    editor: QPlainTextEdit,
    highlighter: CustomSpellHighlighter,
    parent=None,
) -> None:
    """Extend the editor's standard menu with Add to Dictionary."""
    editor.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    def show_context_menu(position) -> None:
        cursor = editor.textCursor()
        if not cursor.hasSelection():
            cursor = editor.cursorForPosition(position)
            cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        word = cursor.selectedText().strip()

        menu = editor.createStandardContextMenu()
        menu.addSeparator()
        label = f'Add "{word}" to Dictionary' if word else "Add to Dictionary"
        add_action = menu.addAction(label)
        add_action.setEnabled(
            bool(re.fullmatch(r"[A-Za-zÀ-ÖØ-öø-ÿ]+", word))
            and word.casefold() not in highlighter.custom_words
        )

        if menu.exec(editor.viewport().mapToGlobal(position)) != add_action:
            return

        try:
            highlighter.add_custom_word(word)
        except OSError as error:
            QMessageBox.warning(
                parent or editor,
                "Dictionary",
                f"Could not update the dictionary:\n{error}",
            )

    editor.customContextMenuRequested.connect(show_context_menu)
```

## Integration

```python
from pathlib import Path

from PyQt6.QtWidgets import QPlainTextEdit

editor = QPlainTextEdit()
dictionary_path = Path(__file__).resolve().parent / "config" / "spell_custom_words.txt"

highlighter = CustomSpellHighlighter(editor.document(), dictionary_path)
attach_dictionary_menu(editor, highlighter)

# Keep a reference for as long as the editor exists.
editor.spell_highlighter = highlighter
```

The dictionary format is one word per line. Blank lines and lines beginning with `#` are retained. Duplicate words are compared with `casefold()`, so variants such as `Iran` and `IRAN` count as duplicates; the first occurrence is preserved.
