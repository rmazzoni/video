"""Connects the Qt6 UI to the comfy_bridge backend (client/loader)."""

import copy
import os
import shutil
import time
from typing import Any, Dict, Optional

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot

from comfy_bridge.client import ComfyClient
from comfy_bridge.workflow_loader import WorkflowLoader
from utilis.logger import Logger


class WorkflowWorker(QObject):
    """
    Submits a workflow + params to ComfyUI on a background QThread and
    polls `ComfyClient.get_result` until it reports completion.
    """

    progress = pyqtSignal(int)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, comfy_client: ComfyClient, workflow: Dict[str, Any], params: Dict[str, Any]):
        super().__init__()
        self.client = comfy_client
        self.workflow = workflow
        self.params = params
        self._cancel_requested = False

    @pyqtSlot()
    def cancel(self) -> None:
        self._cancel_requested = True
        self.client.interrupt()

    @pyqtSlot()
    def run(self) -> None:
        try:
            prompt_id = self.client.execute_workflow(self.workflow, self.params)
            self.progress.emit(10)

            # Poll until finished
            while not self._cancel_requested:
                status = self.client.get_result(prompt_id)
                if status.get("completed"):
                    self.progress.emit(100)
                    self.finished.emit(status)
                    return
                self.progress.emit(status.get("progress") or 50)
                time.sleep(0.5)

        except Exception as e:
            self.error.emit(str(e))


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

        self._thread: Optional[QThread] = None
        self._worker: Optional[WorkflowWorker] = None

    def check_connection(self) -> bool:
        alive = self.client.is_alive()
        self.connection_changed.emit(alive)
        return alive

    def load_workflow(self, name: str) -> Dict[str, Any]:
        return self.loader.load(name)

    def prepare_workflow(self, name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        graph = self.loader.load(name)
        graph = {key: value for key, value in graph.items() if isinstance(value, dict)}
        return self.client._substitute_params(copy.deepcopy(graph), params)

    def save_canvas_workflow(self, name: str, exported_graph: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
        template = self.loader.load(name)
        graph = copy.deepcopy(exported_graph)
        missing = []
        parameter_values: Dict[str, Any] = {}

        def restore_placeholders(source: Any, target: Any, path: str = "") -> None:
            if isinstance(source, str) and source.startswith("@"):
                missing.append((path, source))
                return
            if isinstance(source, dict) and isinstance(target, dict):
                for key, value in source.items():
                    child_path = f"{path}.{key}" if path else str(key)
                    if isinstance(value, str) and value.startswith("@"):
                        if key in target:
                            parameter_values[value[1:]] = target[key]
                            target[key] = value
                        else:
                            missing.append((child_path, value))
                    elif key in target:
                        restore_placeholders(value, target[key], child_path)
            elif isinstance(source, list) and isinstance(target, list):
                for index, value in enumerate(source):
                    if index < len(target):
                        if isinstance(value, str) and value.startswith("@"):
                            parameter_values[value[1:]] = target[index]
                            target[index] = value
                        else:
                            restore_placeholders(value, target[index], f"{path}[{index}]")

        for node_id, node in template.items():
            if not isinstance(node, dict) or not node.get("class_type"):
                continue
            exported_node = graph.get(node_id)
            if not isinstance(exported_node, dict):
                missing.append((node_id, "parameterized node"))
                continue
            restore_placeholders(node, exported_node, node_id)

        if missing:
            details = ", ".join(f"{path} ({value})" for path, value in missing)
            raise ValueError(
                "The canvas no longer contains required Qt parameter locations: " + details
            )

        for key, value in template.items():
            if not isinstance(value, dict):
                graph[key] = value

        workflow_path = os.path.join(self.loader.workflows_dir, name)
        backup_path = workflow_path + ".bak"
        shutil.copy2(workflow_path, backup_path)
        self.loader.save(name, graph)
        return backup_path, parameter_values

    def run_workflow(self, workflow_name: str, params: Optional[Dict[str, Any]] = None) -> None:
        """
        `params` maps placeholder names used in the workflow JSON (e.g.
        "prompt", "seed") to their values, matching `@prompt`/`@seed`
        tokens in the graph.
        """
        if self._thread is not None:
            self.logger.warning("A workflow is already running.")
            return

        graph = self.loader.load(workflow_name)

        self._thread = QThread(self)
        self._worker = WorkflowWorker(self.client, graph, params or {})
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(lambda pct: self.progress.emit(pct, ""))
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_failed)

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

