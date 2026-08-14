"""Placeholder widget reserved for a future embedded ComfyUI node graph editor."""

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget


class NodeEditorStub(QWidget):
    """
    Minimal stand-in panel. Replace with a real node-graph editor (or an
    embedded web view pointing at ComfyUI's own UI) once available.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        label = QLabel("Node editor coming soon.\nUse workflow JSON files for now.", self)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
