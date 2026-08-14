"""Parses ComfyUI websocket events and /history responses into simple results."""

from typing import Any, Dict, List, Optional, Tuple


class ResponseParser:
    """Stateless helpers for interpreting ComfyUI API payloads."""

    def parse_progress_event(self, event: Dict[str, Any], prompt_id: str) -> Optional[Tuple[int, str]]:
        """
        Returns (percent, message) for progress-style events, or None if the
        event isn't progress-related.
        """
        event_type = event.get("type")
        data = event.get("data", {})

        if event_type == "progress":
            value = data.get("value", 0)
            max_value = data.get("max", 1) or 1
            percent = int(100 * value / max_value)
            return percent, f"Sampling {value}/{max_value}"

        if event_type == "executing":
            node = data.get("node")
            if data.get("prompt_id") == prompt_id and node is not None:
                return None, f"Executing node {node}"
            return None

        if event_type == "status":
            return None

        return None

    def is_execution_finished(self, event: Dict[str, Any], prompt_id: str) -> bool:
        """ComfyUI signals completion with an 'executing' event where node is None."""
        if event.get("type") != "executing":
            return False
        data = event.get("data", {})
        return data.get("prompt_id") == prompt_id and data.get("node") is None

    def parse_history(self, history: Dict[str, Any], prompt_id: str) -> Dict[str, Any]:
        """
        Extracts generated output file references (images/videos) from a
        /history/{prompt_id} response.
        """
        entry = history.get(prompt_id, {})
        outputs = entry.get("outputs", {})

        images: List[Dict[str, str]] = []
        for node_output in outputs.values():
            for image in node_output.get("images", []):
                images.append(image)

        return {
            "prompt_id": prompt_id,
            "status": entry.get("status", {}),
            "images": images,
            "raw_outputs": outputs,
        }
