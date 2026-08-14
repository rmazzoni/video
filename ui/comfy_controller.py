"""Connects the Qt6 UI to the comfy_bridge backend (client/loader/executor)."""

from typing import Any, Dict, Optional

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot

from comfy_bridge.client import ComfyClient
from comfy_bridge.workflow_executor import WorkflowExecutor
from comfy_bridge.workflow_loader import WorkflowLoader
from utilis.logger import Logger


class ComfyWorker(QObject):
    """Runs a single workflow execution on a background QThread."""

    progress = pyqtSignal(int, str)
    finished = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, executor: WorkflowExecutor, graph: Dict[str, Any]):
        super().__init__()
        self.executor = executor
        self.graph = graph

    @pyqtSlot()
    def run(self) -> None:
        self.executor.run(
            self.graph,
            on_progress=lambda pct, msg: self.progress.emit(pct, msg),
            on_complete=lambda result: self.finished.emit(result),
            on_error=lambda err: self.failed.emit(err),
        )

    @pyqtSlot()
    def cancel(self) -> None:
        self.executor.cancel()


class ComfyController(QObject):
    """
    High-level facade the UI talks to: manages the ComfyUI connection,
    loads workflows, applies UI parameters, and runs executions on a
    background thread while surfacing Qt signals for progress/results.
    """

    connection_changed = pyqtSignal(bool)
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(
        self,
        workflows_dir: str,
        host: str = "127.0.0.1",
        port: int = 8188,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.logger = Logger()
        self.client = ComfyClient(host=host, port=port)
        self.loader = WorkflowLoader(workflows_dir)
        self.executor = WorkflowExecutor(self.client)

        self._thread: Optional[QThread] = None
        self._worker: Optional[ComfyWorker] = None

    def check_connection(self) -> bool:
        alive = self.client.is_alive()
        self.connection_changed.emit(alive)
        return alive

    def load_workflow(self, name: str) -> Dict[str, Any]:
        return self.loader.load(name)

    def run_workflow(self, workflow_name: str, params: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
        if self._thread is not None:
            self.logger.warning("A workflow is already running.")
            return

        graph = self.loader.load(workflow_name)
        if params:
            graph = self.executor.apply_params(graph, params)

        self._thread = QThread(self)
        self._worker = ComfyWorker(self.executor, graph)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self.progress.emit)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)

        self._thread.start()

    def cancel(self) -> None:
        if self._worker is not None:
            self._worker.cancel()

    def _cleanup_thread(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
            self._thread = None
            self._worker = None

    def _on_finished(self, result: Dict[str, Any]) -> None:
        self.finished.emit(result)
        self._cleanup_thread()

    def _on_failed(self, error: str) -> None:
        self.failed.emit(error)
        self._cleanup_thread()
