"""Dropdown widget for choosing a ComfyUI workflow file."""

from typing import Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QWidget

from comfy_bridge.workflow_loader import WorkflowLoader


class WorkflowSelector(QWidget):
    """Lists workflows from a directory and emits the selected filename."""

    workflow_selected = pyqtSignal(str)

    def __init__(self, workflows_dir: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.loader = WorkflowLoader(workflows_dir)

        self.combo = QComboBox(self)
        self.refresh_button = QPushButton("Refresh", self)

        layout = QHBoxLayout(self)
        layout.addWidget(QLabel("Workflow:", self))
        layout.addWidget(self.combo, 1)
        layout.addWidget(self.refresh_button)

        self.refresh_button.clicked.connect(self.refresh)
        self.combo.currentTextChanged.connect(self.workflow_selected.emit)

        self.refresh()

    def refresh(self) -> None:
        current = self.combo.currentText()
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.addItems(self.loader.list_workflows())
        if current:
            index = self.combo.findText(current)
            if index >= 0:
                self.combo.setCurrentIndex(index)
        self.combo.blockSignals(False)

    def selected_workflow(self) -> str:
        return self.combo.currentText()
