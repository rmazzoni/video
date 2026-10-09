"""Sleepy episode contract: one HiDream seed, storybook prompts, clone voice guard."""

import ast
import os
import sys
import tempfile
import unittest
from pathlib import Path

from audio_loudness import configured_loudness
from narration import qwen_voice
from narration.qwen_voice import (
    chunks_for_scene,
    chunk_narration,
    validate_request,
    voice_python,
    default_model_dir,
    worker_script,
)
from sleepy.chapter import (
    align_stills,
    build_model_prompts,
    create_episode,
    ensure_rome_softly_prompt,
    filenames_for_offsets,
    is_sleepy_project,
    prompts_missing,
    publish_scenes,
    selections_for_stills,
    sleepy_pipeline_config,
)


class SeedContractTests(unittest.TestCase):
    def test_main_keeps_three_seed_neighbours(self):
        names = filenames_for_offsets(4, 2, None)
        self.assertEqual(names, [
            "scene_004_hidream_b02_v1.png",
            "scene_004_hidream_b02_v2.png",
            "scene_004_hidream_b02_v3.png",
        ])

    def test_sleepy_uses_one_seed_named_v1(self):
        names = filenames_for_offsets(4, 2, [0])
        self.assertEqual(names, ["scene_004_hidream_b02_v1.png"])

    def test_pipeline_asks_for_offsets_instead_of_a_fixed_triple(self):
        source = Path("ui/pipeline_controller.py").read_text(encoding="utf-8")
        self.assertIn("resolve_seed_offsets", source)
        self.assertIn("variant_filename", source)
        self.assertNotIn("seed_offsets = [-1, 0, 1]", source)

    def test_main_loudness_default_stays_and_sleepy_uses_the_series_target(self):
        self.assertEqual(configured_loudness({}), (-17.0, -1.0))
        config = sleepy_pipeline_config(7, "rome_softly_ch01")
        self.assertEqual(configured_loudness(config), (-20.0, -3.0))
        self.assertEqual(config["seed_offsets"], [0])
        self.assertEqual(config["enabled_image_models"], ["hidream"])
        self.assertEqual(config["visual_style"], "rome_softly")
        self.assertEqual((config["image_width"], config["image_height"]), (1344, 768))
        self.assertEqual(config["lightbox_model_key"], "")
        self.assertNotIn("schnell", config["enabled_image_models"])


class ChapterTests(unittest.TestCase):
    def test_storybook_sentence_is_kept_and_not_turned_into_a_photograph(self):
        prompt = ensure_rome_softly_prompt(
            "Wide shot of the Tiber at dawn in 509 BC, distant figures on the bank."
        )
        self.assertIn("painterly storybook illustration", prompt.lower())
        self.assertIn("509 BC", prompt)
        self.assertNotIn("sharp photograph", prompt.lower())
        self.assertNotIn("sharp focus, clear air", prompt.lower())
        again = ensure_rome_softly_prompt(prompt)
        self.assertEqual(again, prompt)

    def test_episode_roundtrip_keeps_one_prompt_per_still(self):
        with tempfile.TemporaryDirectory() as folder:
            project = create_episode(folder, "Roma capitolo 1")
            self.assertTrue(is_sleepy_project(project))
            text = "Prima scena sul Tevere all'alba.\n\nSeconda scena dentro la capanna."
            scenes = publish_scenes(project, "Italian", text)
            self.assertEqual([scene["id"] for scene in scenes], [1, 2])
            stills = align_stills(scenes, [{
                "scene_id": 1,
                "beat": 1,
                "prompt": "Dawn on the river.",
            }, {
                "scene_id": 1,
                "beat": 2,
                "prompt": "The hut interior.",
            }])
            self.assertEqual([(row["scene_id"], row["beat"]) for row in stills], [
                (1, 1), (1, 2), (2, 1),
            ])
            self.assertEqual(prompts_missing(stills), ["Scene 002 still 1"])
            stills[2]["prompt"] = "A timber hut."
            prompts = build_model_prompts(scenes, stills)
            self.assertEqual(set(prompts), {1, 2})
            row = prompts[1]["models"]["hidream"]["prompts"][0]
            self.assertEqual(row["source"], "manually_edited")
            self.assertIn("painterly storybook illustration", row["text"].lower())
            self.assertNotIn("dev", prompts[1]["models"])
            selections, missing = selections_for_stills(
                stills, os.path.join(project, "output", "lightbox"),
            )
            self.assertEqual(selections, {})
            self.assertIn("scene_001_hidream_b01_v1.png", missing)
            self.assertIn("scene_001_hidream_b02_v1.png", missing)

    def test_a_main_project_is_not_a_sleepy_episode(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertFalse(is_sleepy_project(folder))


class VoiceChunkTests(unittest.TestCase):
    def test_sentence_and_paragraph_pauses(self):
        pieces = chunk_narration("Hello. There.\n\nNext paragraph.")
        self.assertEqual(pieces, [
            ("Hello.", 0.8),
            ("There.", 2.5),
            ("Next paragraph.", 0.0),
        ])

    def test_long_sentence_splits_without_a_pause_inside_it(self):
        sentence = "word " * 80
        pieces = chunk_narration(sentence.strip() + ".")
        self.assertGreater(len(pieces), 1)
        self.assertTrue(all(len(text) <= 300 for text, _pause in pieces))
        self.assertTrue(all(pause == 0.0 for _text, pause in pieces[:-1]))

    def test_between_scenes_adds_a_paragraph_pause(self):
        chunks = chunks_for_scene("Hello. There.", trailing_paragraph_pause=True)
        self.assertEqual(chunks[0]["pause_after_s"], 0.8)
        self.assertEqual(chunks[-1]["pause_after_s"], 2.5)

    def test_short_abbreviation_is_not_a_sentence(self):
        pieces = chunk_narration("Rome in c. 509 BC was small.")
        self.assertEqual(len(pieces), 1)
        self.assertIn("c. 509", pieces[0][0])

    def test_missing_reference_fails_before_the_model(self):
        with self.assertRaises(RuntimeError) as raised:
            validate_request("Italian", r"F:\no\such\clip.wav", "Ciao, questa è la mia voce.")
        self.assertIn("reference", str(raised.exception).lower())

    def test_empty_transcript_fails_before_the_model(self):
        with self.assertRaises(RuntimeError) as raised:
            validate_request("English", r"F:\no\such\clip.wav", "  ")
        self.assertIn("transcript", str(raised.exception).lower())

    def test_worker_stays_out_of_the_app_process(self):
        sys.modules.pop("qwen_tts", None)
        import narration.qwen_voice_worker  # noqa: F401
        self.assertNotIn("qwen_tts", sys.modules)
        tree = ast.parse(Path(worker_script()).read_text(encoding="utf-8"))
        imported = []
        for node in tree.body:
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            if isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
        self.assertFalse(any("qwen" in name for name in imported))
        source = Path(worker_script()).read_text(encoding="utf-8")
        self.assertIn("non_streaming_mode=True", source)
        self.assertNotIn("qianwen-res.oss", source)
        app_tree = ast.parse(Path(qwen_voice.__file__).read_text(encoding="utf-8"))
        app_imports = []
        for node in ast.walk(app_tree):
            if isinstance(node, ast.Import):
                app_imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                app_imports.append(node.module or "")
        self.assertFalse(any(name.startswith("qwen") for name in app_imports))

    def test_voice_environment_is_the_sibling_venv(self):
        parts = voice_python().parts
        self.assertEqual(parts[-4:], ("voice", "venv", "Scripts", "python.exe"))
        self.assertTrue(voice_python().is_file())
        self.assertTrue(default_model_dir().is_dir())


class SleepyPanelTests(unittest.TestCase):
    def test_panel_has_only_the_chapter_tabs(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication
        from ui.pipeline_controller import PipelineController
        from ui.sleepy_panel import SleepyPanel

        app = QApplication.instance() or QApplication([])
        panel = SleepyPanel(PipelineController())
        titles = [panel.inner_tabs.tabText(index) for index in range(panel.inner_tabs.count())]
        self.assertEqual(titles, ["Episode", "Script", "Stills", "Voice", "Final"])
        window_source = Path("ui/main_window.py").read_text(encoding="utf-8")
        self.assertIn('self.mode_tabs.addTab(self.tabs, "Main")', window_source)
        self.assertIn('self.mode_tabs.addTab(self.sleepy_panel, "Sleepy")', window_source)
        panel.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    unittest.main()
