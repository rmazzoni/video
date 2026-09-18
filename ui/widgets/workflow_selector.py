"""Dropdown widget for choosing a ComfyUI workflow file."""

from typing import List, Optional, Sequence, Tuple

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QWidget

from comfy_bridge.workflow_loader import WorkflowLoader


class WorkflowSelector(QWidget):
    """Lists workflows from a directory and emits the selected filename."""

    workflow_selected = pyqtSignal(str)

    def __init__(
        self,
        workflows_dir: str,
        default_workflow: str = "",
        parent: Optional[QWidget] = None,
        choices: Optional[Sequence[Tuple[str, str]]] = None,
    ):
        super().__init__(parent)
        self.loader = WorkflowLoader(workflows_dir)
        self.default_workflow = default_workflow
        self.choices = list(choices) if choices else None

        self.combo = QComboBox(self)
        self.refresh_button = QPushButton("Refresh", self)

        layout = QHBoxLayout(self)
        layout.addWidget(QLabel("Graph:", self))
        layout.addWidget(self.combo, 1)
        layout.addWidget(self.refresh_button)

        self.refresh_button.clicked.connect(self.refresh)
        self.combo.currentIndexChanged.connect(self._emit_selected)

        self.refresh()

    def _emit_selected(self) -> None:
        name = self.selected_workflow()
        if name:
            self.workflow_selected.emit(name)

    def refresh(self) -> None:
        current = self.selected_workflow()
        self.combo.blockSignals(True)
        self.combo.clear()
        if self.choices:
            available = set(self.loader.list_workflows())
            for filename, label in self.choices:
                if filename in available:
                    self.combo.addItem(label, filename)
        else:
            for filename in self.loader.list_workflows():
                self.combo.addItem(filename, filename)
        selected = current or self.default_workflow
        if selected:
            index = self.combo.findData(selected)
            if index < 0:
                index = self.combo.findText(selected)
            if index >= 0:
                self.combo.setCurrentIndex(index)
        self.combo.blockSignals(False)
        self._emit_selected()

    def selected_workflow(self) -> str:
        data = self.combo.currentData()
        if data:
            return str(data)
        return self.combo.currentText()
