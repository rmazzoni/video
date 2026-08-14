"""Loads ComfyUI workflow graphs (API-format .json exports) from disk."""

import json
import os
from typing import Any, Dict, List

from utilis.logger import Logger


class WorkflowLoader:
    """Discovers and loads workflow JSON files from the `workflows/` directory."""

    def __init__(self, workflows_dir: str):
        self.workflows_dir = workflows_dir
        self.logger = Logger()

    def list_workflows(self) -> List[str]:
        if not os.path.isdir(self.workflows_dir):
            return []
        return sorted(
            f for f in os.listdir(self.workflows_dir)
            if f.lower().endswith(".json")
        )

    def load(self, name: str) -> Dict[str, Any]:
        """
        Load a workflow by filename (e.g. "flux2_image.json") or absolute path.
        Returns the parsed prompt graph dict.
        """
        path = name if os.path.isabs(name) else os.path.join(self.workflows_dir, name)
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Workflow not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            graph = json.load(f)

        self.logger.info(f"Loaded workflow: {path}")
        return graph

    def save(self, name: str, graph: Dict[str, Any]) -> str:
        os.makedirs(self.workflows_dir, exist_ok=True)
        path = os.path.join(self.workflows_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(graph, f, indent=2)
        return path
