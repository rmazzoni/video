import os
import tempfile
import unittest

import yaml

from utilis.project_paths import (
    DIR_DRAFT,
    DIR_FINAL,
    DIR_FINAL_CLIPS,
    DIR_PREVIEW,
    ProjectLayout,
    migrate_legacy_output_dirs,
    prefixed_media_name,
    project_slug,
    sanitize_project_slug,
)


class SlugTests(unittest.TestCase):
    def test_spaces_become_underscores(self):
        self.assertEqual(sanitize_project_slug("Gulf Film"), "Gulf_Film")

    def test_illegal_filename_chars_are_stripped(self):
        self.assertEqual(sanitize_project_slug('A<>:"/\\|?*B'), "AB")

    def test_empty_falls_back(self):
        self.assertEqual(sanitize_project_slug("   "), "project")

    def test_prefix_is_idempotent(self):
        self.assertEqual(
            prefixed_media_name("Gulf", "Gulf_preview_video.mp4"),
            "Gulf_preview_video.mp4",
        )
        self.assertEqual(
            prefixed_media_name("Gulf", "preview_video.mp4"),
            "Gulf_preview_video.mp4",
        )

    def test_slug_that_matches_a_media_stem_still_prefixes(self):
        self.assertEqual(
            prefixed_media_name("preview", "preview_video.mp4"),
            "preview_preview_video.mp4",
        )
        self.assertEqual(
            prefixed_media_name("final", "final_with_audio.mp4"),
            "final_final_with_audio.mp4",
        )
        self.assertEqual(
            prefixed_media_name("preview", "preview_preview_video.mp4"),
            "preview_preview_video.mp4",
        )


class LayoutTests(unittest.TestCase):
    def test_paths_use_new_folder_names_and_project_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "Gulf Story")
            os.makedirs(root)
            layout = ProjectLayout(root)
            self.assertEqual(layout.slug, "Gulf_Story")
            self.assertTrue(layout.draft.endswith(os.path.join("output", DIR_DRAFT)))
            self.assertTrue(layout.preview.endswith(os.path.join("output", DIR_PREVIEW)))
            self.assertTrue(layout.final_clips.endswith(os.path.join("output", DIR_FINAL_CLIPS)))
            self.assertTrue(layout.final.endswith(os.path.join("output", DIR_FINAL)))
            self.assertEqual(
                os.path.basename(layout.preview_video),
                "Gulf_Story_preview_video.mp4",
            )
            self.assertEqual(
                os.path.basename(layout.preview_with_audio),
                "Gulf_Story_preview_with_audio.mp4",
            )
            self.assertEqual(
                os.path.basename(layout.final_video),
                "Gulf_Story_final_video.mp4",
            )
            self.assertEqual(
                os.path.basename(layout.final_with_audio),
                "Gulf_Story_final_with_audio.mp4",
            )
            self.assertEqual(
                os.path.basename(layout.preview_audio),
                "Gulf_Story_narration_combined.mp3",
            )
            self.assertEqual(
                os.path.basename(layout.final_audio),
                "Gulf_Story_final_audio.mp3",
            )

    def test_manifest_name_wins_over_folder_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "folder")
            os.makedirs(root)
            with open(os.path.join(root, "vid_project.yaml"), "w", encoding="utf-8") as handle:
                yaml.safe_dump({"name": "Official Title"}, handle)
            self.assertEqual(project_slug(root), "Official_Title")

    def test_migrate_renames_legacy_dirs_and_media(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "Alpha")
            output = os.path.join(root, "output")
            old_preview = os.path.join(output, "preview")
            old_clips = os.path.join(output, "clips")
            old_draft = os.path.join(output, "draft")
            old_final = os.path.join(output, "final")
            for path in (old_preview, old_clips, old_draft, old_final):
                os.makedirs(path)
            open(os.path.join(old_preview, "preview_video.mp4"), "w").close()
            open(os.path.join(old_preview, "preview_with_audio.mp4"), "w").close()
            open(os.path.join(old_final, "final_video.mp4"), "w").close()
            open(os.path.join(old_final, "final_with_audio.mp4"), "w").close()
            open(os.path.join(old_final, "final_audio.mp3"), "w").close()

            notes = migrate_legacy_output_dirs(root)
            self.assertTrue(any("draft" in line and DIR_DRAFT in line for line in notes))
            self.assertTrue(os.path.isdir(os.path.join(output, DIR_DRAFT)))
            self.assertTrue(os.path.isdir(os.path.join(output, DIR_PREVIEW)))
            self.assertTrue(os.path.isdir(os.path.join(output, DIR_FINAL_CLIPS)))
            self.assertTrue(os.path.isdir(os.path.join(output, DIR_FINAL)))
            self.assertFalse(os.path.exists(old_preview))
            self.assertFalse(os.path.exists(old_clips))
            self.assertTrue(
                os.path.isfile(os.path.join(output, DIR_PREVIEW, "Alpha_preview_video.mp4"))
            )
            self.assertTrue(
                os.path.isfile(os.path.join(output, DIR_FINAL, "Alpha_final_with_audio.mp4"))
            )
            self.assertTrue(
                os.path.isfile(os.path.join(output, DIR_FINAL, "Alpha_final_audio.mp3"))
            )

    def test_migrate_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "Beta")
            os.makedirs(os.path.join(root, "output", "clips"))
            migrate_legacy_output_dirs(root)
            second = migrate_legacy_output_dirs(root)
            self.assertEqual(second, [])
            self.assertTrue(os.path.isdir(os.path.join(root, "output", DIR_FINAL_CLIPS)))
