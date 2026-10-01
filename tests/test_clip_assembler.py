import os
import tempfile
import unittest

from ui.pipeline_controller import PipelineWorker
from video.clip_assembler import (
    ClipAssembler,
    clip_file_is_usable,
    clip_sort_key,
    concat_list_line,
    scene_id_from_name,
    _clips_grouped_by_scene,
)


class ClipNameTests(unittest.TestCase):
    def test_sort_orders_scene_then_beat_then_schnell_before_zimage(self):
        names = [
            "scene_002_zimage_b01_v2.mp4",
            "scene_001_zimage_b02_v2.mp4",
            "scene_001_schnell_b02_v2.mp4",
            "scene_001_schnell_b01_v2.mp4",
            "scene_001_zimage_b01_v2.mp4",
        ]
        ordered = sorted(names, key=clip_sort_key)
        self.assertEqual(ordered, [
            "scene_001_schnell_b01_v2.mp4",
            "scene_001_zimage_b01_v2.mp4",
            "scene_001_schnell_b02_v2.mp4",
            "scene_001_zimage_b02_v2.mp4",
            "scene_002_zimage_b01_v2.mp4",
        ])

    def test_legacy_and_final_clip_names_still_sort(self):
        names = ["scene_002.mp4", "scene_001_v01.mp4", "scene_001_v00.mp4"]
        ordered = sorted(names, key=clip_sort_key)
        self.assertEqual(ordered, [
            "scene_001_v00.mp4",
            "scene_001_v01.mp4",
            "scene_002.mp4",
        ])

    def test_group_consecutive_clips_by_scene(self):
        files = [
            "scene_001_schnell_b01_v2.mp4",
            "scene_001_zimage_b01_v2.mp4",
            "scene_002_schnell_b01_v2.mp4",
        ]
        groups = _clips_grouped_by_scene(files)
        self.assertEqual([sid for sid, _paths in groups], [1, 2])
        self.assertEqual(len(groups[0][1]), 2)
        self.assertEqual(len(groups[1][1]), 1)

    def test_scene_id_from_preview_clip_name(self):
        self.assertEqual(scene_id_from_name("scene_014_zimage_b03_v2.mp4"), 14)

    def test_empty_mp4_is_not_usable(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = os.path.join(tmp, "scene_001_v00.mp4")
            open(empty, "wb").close()
            self.assertFalse(clip_file_is_usable(empty))
            self.assertFalse(clip_file_is_usable(os.path.join(tmp, "missing.mp4")))
            real = os.path.join(tmp, "scene_001_v01.mp4")
            with open(real, "wb") as fh:
                fh.write(b"\x00" * 64)
            self.assertTrue(clip_file_is_usable(real))

    def test_assemble_rejects_empty_clips(self):
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "scene_001_v00.mp4"), "wb").close()
            assembler = ClipAssembler(os.path.join(tmp, "out.mp4"))
            with self.assertRaises(ValueError) as ctx:
                assembler.assemble(tmp)
            message = str(ctx.exception)
            self.assertIn("empty or unreadable", message)
            self.assertIn("scene_001_v00.mp4", message)

    def test_concat_list_line_uses_forward_slashes(self):
        line = concat_list_line(r"F:\proj\output\final_clips\scene_001_v00.mp4")
        self.assertTrue(line.startswith("file '"))
        self.assertNotIn("\\", line)

    def test_padded_temp_clips_are_not_assembled(self):
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "scene_001_v00_padded.mp4"), "wb").close()
            assembler = ClipAssembler(os.path.join(tmp, "out.mp4"))
            self.assertEqual(assembler._get_sorted_clips(tmp), [])

    def test_clip_output_is_current_rejects_empty_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "still.png")
            clip = os.path.join(tmp, "scene_001_v00.mp4")
            with open(src, "wb") as fh:
                fh.write(b"png")
            open(clip, "wb").close()
            os.utime(clip, (os.path.getmtime(src) + 10, os.path.getmtime(src) + 10))
            self.assertFalse(PipelineWorker._clip_output_is_current(clip, src))
            with open(clip, "wb") as fh:
                fh.write(b"\x00" * 64)
            os.utime(clip, (os.path.getmtime(src) + 10, os.path.getmtime(src) + 10))
            self.assertTrue(PipelineWorker._clip_output_is_current(clip, src))


class PreviewStillCandidateTests(unittest.TestCase):
    def test_lists_each_schnell_and_zimage_beat(self):
        with tempfile.TemporaryDirectory() as tmp:
            names = [
                "scene_001_schnell_b01_v2.png",
                "scene_001_schnell_b02_v2.png",
                "scene_001_zimage_b01_v2.png",
                "scene_001_zimage_b02_v2.png",
                "scene_001.png",
            ]
            for name in names:
                open(os.path.join(tmp, name), "w").close()
            found = [
                os.path.basename(path)
                for path in PipelineWorker._preview_still_candidates(tmp)
            ]
            self.assertEqual(found, [
                "scene_001_schnell_b01_v2.png",
                "scene_001_zimage_b01_v2.png",
                "scene_001_schnell_b02_v2.png",
                "scene_001_zimage_b02_v2.png",
            ])

    def test_clip_suffix_matches_still_stem(self):
        suffix = PipelineWorker._clip_suffix_from_still(
            "output/preview_images/scene_003_zimage_b02_v2.png"
        )
        self.assertEqual(suffix, "_zimage_b02_v2")
