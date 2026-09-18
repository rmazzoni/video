import os
import tempfile
import unittest

from ui.pipeline_controller import (
    copy_preview_to_lightbox,
    preview_v2_filename,
    recover_preview_still,
)


class PreviewLightboxCopyTests(unittest.TestCase):
    def test_filename_matches_pipeline_convention(self):
        self.assertEqual(
            preview_v2_filename(1, "schnell", 2),
            "scene_001_schnell_b02_v2.png",
        )

    def test_copy_overwrites_existing_lightbox_v2(self):
        with tempfile.TemporaryDirectory() as tmp:
            preview = os.path.join(tmp, "preview_images")
            lightbox = os.path.join(tmp, "lightbox")
            os.makedirs(preview)
            os.makedirs(lightbox)
            name = preview_v2_filename(3, "zimage", 1)
            src = os.path.join(preview, name)
            dest = os.path.join(lightbox, name)
            with open(src, "wb") as handle:
                handle.write(b"new-preview")
            with open(dest, "wb") as handle:
                handle.write(b"old-lightbox")
            self.assertTrue(copy_preview_to_lightbox(preview, lightbox, 3, "zimage", 1))
            with open(dest, "rb") as handle:
                self.assertEqual(handle.read(), b"new-preview")

    def test_copy_creates_missing_lightbox_slot(self):
        with tempfile.TemporaryDirectory() as tmp:
            preview = os.path.join(tmp, "preview_images")
            lightbox = os.path.join(tmp, "lightbox")
            os.makedirs(preview)
            name = preview_v2_filename(8, "schnell", 1)
            with open(os.path.join(preview, name), "wb") as handle:
                handle.write(b"preview")
            self.assertTrue(copy_preview_to_lightbox(preview, lightbox, 8, "schnell", 1))
            self.assertTrue(os.path.isfile(os.path.join(lightbox, name)))

    def test_copy_skips_when_preview_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            preview = os.path.join(tmp, "preview_images")
            lightbox = os.path.join(tmp, "lightbox")
            os.makedirs(preview)
            self.assertFalse(copy_preview_to_lightbox(preview, lightbox, 1, "schnell", 1))

    def test_recover_copies_lightbox_v2_into_preview_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            preview = os.path.join(tmp, "preview_images")
            lightbox = os.path.join(tmp, "lightbox")
            os.makedirs(preview)
            os.makedirs(lightbox)
            name = preview_v2_filename(4, "schnell", 1)
            with open(os.path.join(lightbox, name), "wb") as handle:
                handle.write(b"from-lightbox")
            self.assertTrue(recover_preview_still(preview, lightbox, 4, "schnell", 1))
            dest = os.path.join(preview, name)
            self.assertTrue(os.path.isfile(dest))
            with open(dest, "rb") as handle:
                self.assertEqual(handle.read(), b"from-lightbox")

    def test_recover_is_true_when_preview_already_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            preview = os.path.join(tmp, "preview_images")
            lightbox = os.path.join(tmp, "lightbox")
            os.makedirs(preview)
            os.makedirs(lightbox)
            name = preview_v2_filename(2, "zimage", 1)
            with open(os.path.join(preview, name), "wb") as handle:
                handle.write(b"already")
            self.assertTrue(recover_preview_still(preview, lightbox, 2, "zimage", 1))
