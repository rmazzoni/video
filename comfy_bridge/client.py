"""HTTP/WebSocket client for talking to a running ComfyUI server."""

import copy
import json
import os
import time
import uuid
from typing import Any, Callable, Dict, Optional

import requests
import websocket

from utilis.logger import Logger

from .response_parser import ResponseParser


class ComfyClient:
    """
    Thin transport layer around ComfyUI's REST + WebSocket API.

    Does not know anything about workflow structure; callers pass fully
    built prompt graphs and receive raw responses/events back.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8188, client_id: Optional[str] = None):
        self.host = host
        self.port = port
        self.client_id = client_id or str(uuid.uuid4())
        self.logger = Logger()
        self._ws: Optional[websocket.WebSocket] = None

    # ------------------------------------------------------------------
    # URL helpers
    # ------------------------------------------------------------------

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def ws_url(self) -> str:
        return f"ws://{self.host}:{self.port}/ws?clientId={self.client_id}"

    # ------------------------------------------------------------------
    # REST API
    # ------------------------------------------------------------------

    def is_alive(self, timeout: float = 2.0) -> bool:
        try:
            resp = requests.get(f"{self.base_url}/system_stats", timeout=timeout)
            return resp.status_code == 200
        except requests.RequestException:
            return False

    def queue_prompt(self, prompt: Dict[str, Any]) -> Dict[str, Any]:
        """Submit a prompt graph to ComfyUI and return the queue response (prompt_id, etc.)."""
        payload = {"prompt": prompt, "client_id": self.client_id}
        resp = requests.post(f"{self.base_url}/prompt", json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_history(self, prompt_id: str) -> Dict[str, Any]:
        resp = requests.get(f"{self.base_url}/history/{prompt_id}", timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_queue(self) -> Dict[str, Any]:
        """Returns the current running/pending queue (GET /queue)."""
        resp = requests.get(f"{self.base_url}/queue", timeout=10)
        resp.raise_for_status()
        return resp.json()

    def get_image(self, filename: str, subfolder: str = "", folder_type: str = "output") -> bytes:
        params = {"filename": filename, "subfolder": subfolder, "type": folder_type}
        resp = requests.get(f"{self.base_url}/view", params=params, timeout=60)
        resp.raise_for_status()
        return resp.content

    def interrupt(self) -> None:
        requests.post(f"{self.base_url}/interrupt", timeout=10)

    # ------------------------------------------------------------------
    # High-level workflow API
    # ------------------------------------------------------------------

    def load_workflow(self, path: str) -> Dict[str, Any]:
        """Loads a ComfyUI API-format workflow graph from a .json file."""
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Workflow not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _substitute_params(self, node: Any, params: Dict[str, Any]) -> Any:
        """Recursively replaces "@key" placeholder strings with params[key]."""
        if isinstance(node, str) and node.startswith("@"):
            key = node[1:]
            if key in params:
                return params[key]
            return node
        if isinstance(node, dict):
            return {k: self._substitute_params(v, params) for k, v in node.items()}
        if isinstance(node, list):
            return [self._substitute_params(v, params) for v in node]
        return node

    def execute_workflow(self, workflow: Dict[str, Any], params: Dict[str, Any]) -> str:
        """
        Injects `params` (e.g. {"prompt": "...", "seed": 123}) into any
        "@prompt" / "@seed" placeholder found in the workflow's node inputs,
        submits the resulting graph, and returns the ComfyUI prompt_id.
        """
        graph = self._substitute_params(copy.deepcopy(workflow), params)
        queued = self.queue_prompt(graph)
        prompt_id = queued.get("prompt_id")
        if not prompt_id:
            raise RuntimeError(f"ComfyUI did not return a prompt_id: {queued}")
        return prompt_id

    def get_result(self, prompt_id: str, timeout: float = 300.0, poll_interval: float = 1.0) -> Dict[str, Any]:
        """
        Blocks until `prompt_id` finishes (or `timeout` seconds elapse),
        polling /history/{id}, then returns the parsed result
        (see ResponseParser.parse_history).
        """
        parser = ResponseParser()
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            history = self.get_history(prompt_id)
            if prompt_id in history:
                return parser.parse_history(history, prompt_id)
            time.sleep(poll_interval)

        raise TimeoutError(f"Timed out waiting for ComfyUI prompt {prompt_id}")

    # ------------------------------------------------------------------
    # WebSocket streaming
    # ------------------------------------------------------------------

    def connect(self) -> None:
        self._ws = websocket.WebSocket()
        self._ws.connect(self.ws_url)

    def close(self) -> None:
        if self._ws is not None:
            try:
                self._ws.close()
            finally:
                self._ws = None

    def stream_events(self, on_event: Callable[[Dict[str, Any]], None], stop_flag: Callable[[], bool]) -> None:
        """
        Blocking loop that reads JSON messages from the ComfyUI websocket
        and forwards them to `on_event` until `stop_flag()` returns True.
        Binary frames (preview images) are ignored.
        """
        if self._ws is None:
            self.connect()

        while not stop_flag():
            try:
                message = self._ws.recv()
            except Exception as exc:  # connection closed/broken
                self.logger.warning(f"WebSocket recv failed: {exc}")
                break

            if isinstance(message, (bytes, bytearray)):
                continue  # binary preview data, not needed here

            try:
                event = json.loads(message)
            except json.JSONDecodeError:
                continue

            on_event(event)
