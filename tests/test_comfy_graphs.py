import json
import os
import unittest

from comfy_bridge.client import ComfyClient
from comfy_bridge.graphs import (
    OTHER_WORKFLOWS,
    PRODUCT_STILLS,
    leftover_placeholders,
    missing_placeholders,
    params_for_spec,
    spec_for_model,
)


WORKFLOWS_DIR = os.path.join(os.path.dirname(__file__), "..", "workflows")


def _load_graph(filename: str):
    path = os.path.join(WORKFLOWS_DIR, filename)
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


class ProductStillContractTests(unittest.TestCase):
    def test_every_product_graph_matches_its_param_spec(self):
        for model_type, spec in PRODUCT_STILLS.items():
            with self.subTest(model=model_type):
                graph = _load_graph(spec.filename)
                declared = leftover_placeholders(graph)
                self.assertEqual(declared, spec.params, spec.filename)

    def test_spec_for_model_rejects_unknown(self):
        with self.assertRaises(ValueError):
            spec_for_model("sdxl")

    def test_params_for_spec_drops_keys_the_graph_ignores(self):
        spec = spec_for_model("flux-schnell")
        sent = params_for_spec(spec, {
            "prompt": "a drone",
            "seed": 1,
            "width": 1344,
            "height": 768,
            "steps": 4,
            "guidance": 0.0,
            "sampler": "res_multistep",
            "scheduler": "simple",
            "shift": 3.0,
            "filename_prefix": "vid/test",
        })
        self.assertNotIn("sampler", sent)
        self.assertNotIn("shift", sent)
        self.assertEqual(sent["prompt"], "a drone")
        self.assertEqual(leftover_placeholders(
            ComfyClient()._substitute_params(_load_graph(spec.filename), sent)
        ), frozenset())

    def test_missing_placeholders_are_detected(self):
        spec = spec_for_model("zimage-turbo")
        graph = _load_graph(spec.filename)
        missing = missing_placeholders(graph, {"prompt": "x"})
        self.assertIn("seed", missing)
        self.assertIn("sampler", missing)

    def test_compatibility_and_lab_graphs_are_not_product_stills(self):
        product_files = {spec.filename for spec in PRODUCT_STILLS.values()}
        for filename, spec in OTHER_WORKFLOWS.items():
            self.assertNotIn(filename, product_files)
            self.assertIn(spec.role, {"lab", "compatibility"})


if __name__ == "__main__":
    unittest.main()
