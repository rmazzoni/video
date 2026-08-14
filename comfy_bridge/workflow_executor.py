"""Injects parameters into a workflow graph and drives execution via ComfyClient."""

import copy
import threading
from typing import Any, Callable, Dict, Optional

from utilis.logger import Logger

from .client import ComfyClient
from .response_parser import ResponseParser


class WorkflowExecutor:
    """
    Takes a loaded workflow graph + a dict of parameter overrides (mapped by
    node title or node id), submits it to ComfyUI, and streams progress
    back through callbacks until completion.
    """

    def __init__(self, client: ComfyClient):
        self.client = client
        self.logger = Logger()
        self._cancel_requested = False

    def apply_params(self, graph: Dict[str, Any], params: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        params: {node_id_or_title: {input_name: value, ...}, ...}
        Matches nodes either by dict key (node id) or by `_meta.title`.
        Returns a new graph, the original is left untouched.
        """
        graph = copy.deepcopy(graph)
        title_to_id = {
            node.get("_meta", {}).get("title"): node_id
            for node_id, node in graph.items()
        }

        for target, overrides in params.items():
            node_id = target if target in graph else title_to_id.get(target)
            if node_id is None:
                self.logger.warning(f"No matching node for param target '{target}'")
                continue
            graph[node_id].setdefault("inputs", {}).update(overrides)

        return graph

    def cancel(self) -> None:
        self._cancel_requested = True
        self.client.interrupt()

    def run(
        self,
        graph: Dict[str, Any],
        on_progress: Optional[Callable[[int, str], None]] = None,
        on_complete: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ) -> None:
        """
        Synchronous, blocking execution. Intended to be called from a
        QThread/worker, not the Qt main thread.
        """
        self._cancel_requested = False
        parser = ResponseParser()

        try:
            queued = self.client.queue_prompt(graph)
            prompt_id = queued.get("prompt_id")
            if not prompt_id:
                raise RuntimeError(f"ComfyUI did not return a prompt_id: {queued}")

            self.client.connect()

            def stop_flag() -> bool:
                return self._cancel_requested

            def handle_event(event: Dict[str, Any]) -> None:
                progress = parser.parse_progress_event(event, prompt_id)
                if progress is not None and on_progress:
                    on_progress(progress[0], progress[1])
                if parser.is_execution_finished(event, prompt_id):
                    self._cancel_requested = True  # stop the stream loop

            self.client.stream_events(handle_event, stop_flag)
            self.client.close()

            history = self.client.get_history(prompt_id)
            result = parser.parse_history(history, prompt_id)

            if on_complete:
                on_complete(result)

        except Exception as exc:
            self.logger.error(f"Workflow execution failed: {exc}")
            if on_error:
                on_error(str(exc))

    def run_async(
        self,
        graph: Dict[str, Any],
        on_progress: Optional[Callable[[int, str], None]] = None,
        on_complete: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ) -> threading.Thread:
        """Convenience helper: runs `run` on a background thread and returns it."""
        thread = threading.Thread(
            target=self.run,
            kwargs=dict(graph=graph, on_progress=on_progress, on_complete=on_complete, on_error=on_error),
            daemon=True,
        )
        thread.start()
        return thread
