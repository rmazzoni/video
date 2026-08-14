"""Widget showing ComfyUI connection state, progress bar and log output."""

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QPlainTextEdit, QProgressBar, QVBoxLayout, QWidget


class PipelineStatus(QWidget):
    """Displays connection state, execution progress, and streamed log lines."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.connection_label = QLabel("ComfyUI: disconnected", self)
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.log_view = QPlainTextEdit(self)
        self.log_view.setReadOnly(True)

        layout = QVBoxLayout(self)
        layout.addWidget(self.connection_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.log_view, 1)

    def set_connected(self, connected: bool) -> None:
        self.connection_label.setText(f"ComfyUI: {'connected' if connected else 'disconnected'}")
        color = "green" if connected else "red"
        self.connection_label.setStyleSheet(f"color: {color};")

    def set_progress(self, percent: int, message: str = "") -> None:
        self.progress_bar.setValue(max(0, min(100, percent)))
        if message:
            self.append_log(message)

    def append_log(self, message: str) -> None:
        self.log_view.appendPlainText(message)

    def clear(self) -> None:
        self.progress_bar.setValue(0)
        self.log_view.clear()
