import unittest

from narration.tts_engine import (
    EDGE_TTS_VOICES,
    preview_text_for_voice,
    voice_locale,
)


class EdgeTtsVoiceCatalogueTests(unittest.TestCase):
    def test_catalogue_includes_us_and_uk_voices(self):
        short_names = [name for _label, name, _gender in EDGE_TTS_VOICES]
        self.assertIn("it-IT-DiegoNeural", short_names)
        self.assertIn("en-US-AndrewNeural", short_names)
        self.assertIn("en-US-JennyNeural", short_names)
        self.assertIn("en-GB-RyanNeural", short_names)
        self.assertIn("en-GB-LibbyNeural", short_names)

    def test_voice_locale_from_short_name(self):
        self.assertEqual(voice_locale("en-US-AndrewNeural"), "en-US")
        self.assertEqual(voice_locale("en-GB-RyanNeural"), "en-GB")
        self.assertEqual(voice_locale("it-IT-DiegoNeural"), "it-IT")
        self.assertEqual(voice_locale(""), "it-IT")

    def test_preview_text_matches_voice_language(self):
        italian = preview_text_for_voice("it-IT-DiegoNeural")
        us = preview_text_for_voice("en-US-AvaNeural")
        uk = preview_text_for_voice("en-GB-SoniaNeural")
        self.assertIn("Ciao", italian)
        self.assertTrue(us.startswith("Hello"))
        self.assertEqual(us, uk)


if __name__ == "__main__":
    unittest.main()
