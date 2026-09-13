import os
import unittest

from prompts.model_prompt_service import (
    PROMPT_ONLY_SCHEMA,
    build_prompt_user_payload,
    wrap_project_profile,
)
from prompts.project_profiles import load_project_profiles
from prompts.prompt_grounding import check_prompt
from prompts.visual_beats import (
    VisualBeat,
    beats_as_dicts,
    dedupe_beats,
    fallback_beat,
    normalize_stored_beats,
    quote_in_narration,
    slot_is_grounded,
    validate_extracted_beats,
)


NARRATION = (
    "Il pescatore cammina sul molo all'alba. "
    "Le reti sono stese a asciugare."
)


class QuoteLockTests(unittest.TestCase):
    def test_quote_must_be_verbatim_substring(self):
        self.assertTrue(quote_in_narration("Il pescatore cammina sul molo all'alba.", NARRATION))
        self.assertTrue(quote_in_narration("  IL  PESCATORE  cammina sul molo all'alba. ", NARRATION))
        self.assertFalse(quote_in_narration("A fisherman walks on a pier at dawn.", NARRATION))

    def test_slot_grounding_uses_source_language(self):
        quote = "Il pescatore cammina sul molo all'alba."
        self.assertTrue(slot_is_grounded("pescatore", quote))
        self.assertTrue(slot_is_grounded("cammina sul molo", quote))
        self.assertFalse(slot_is_grounded("un diplomatico con smartphone", quote))


class ValidationTests(unittest.TestCase):
    def test_drops_ungrounded_quote_and_invented_slots(self):
        raw = [
            {
                "source_quote": "A diplomat shakes hands in a marble hall",
                "subject": "a diplomat",
                "action": "shakes hands",
                "setting": "marble hall",
                "objects": ["smartphone"],
                "beat": "A diplomat shakes hands in a marble hall.",
            },
            {
                "source_quote": "Il pescatore cammina sul molo all'alba.",
                "subject": "il pescatore",
                "action": "cammina sul molo",
                "setting": "all'alba",
                "objects": ["molo"],
                "beat": "A fisherman walks along the pier at dawn.",
            },
        ]
        beats = validate_extracted_beats(raw, NARRATION, limit=3)
        self.assertEqual(len(beats), 1)
        self.assertEqual(beats[0].source_quote, "Il pescatore cammina sul molo all'alba.")
        self.assertIn("fisherman", beats[0].beat.lower())

    def test_clears_invented_slots_but_keeps_grounded_quote(self):
        raw = [{
            "source_quote": "Il pescatore cammina sul molo all'alba.",
            "subject": "a senator",
            "action": "holds a tablet",
            "setting": "glass boardroom",
            "objects": ["hologram"],
            "beat": "A senator holds a glowing hologram in a glass boardroom.",
        }]
        beats = validate_extracted_beats(raw, NARRATION, limit=3)
        self.assertEqual(len(beats), 1)
        self.assertEqual(beats[0].subject, "")
        self.assertEqual(beats[0].action, "")
        self.assertEqual(beats[0].objects, [])
        self.assertEqual(beats[0].beat, "Il pescatore cammina sul molo all'alba.")

    def test_does_not_pad_to_maximum(self):
        raw = [{
            "source_quote": "Il pescatore cammina sul molo all'alba.",
            "subject": "il pescatore",
            "action": "cammina",
            "setting": "molo",
            "objects": [],
            "beat": "A fisherman walks on the pier.",
        }]
        beats = validate_extracted_beats(raw, NARRATION, limit=3)
        self.assertEqual(len(beats), 1)

    def test_dedupes_overlapping_quotes(self):
        first = VisualBeat(
            beat="A fisherman walks on the pier.",
            source_quote="Il pescatore cammina sul molo all'alba.",
        )
        second = VisualBeat(
            beat="A fisherman at dawn.",
            source_quote="Il pescatore cammina sul molo all'alba",
        )
        kept = dedupe_beats([first, second])
        self.assertEqual(len(kept), 1)

    def test_one_sentence_scene_caps_at_one_beat(self):
        narration = "Il pescatore cammina sul molo all'alba."
        raw = [
            {
                "source_quote": "Il pescatore cammina sul molo all'alba.",
                "subject": "il pescatore",
                "action": "cammina",
                "setting": "molo",
                "objects": [],
                "beat": "A fisherman walks on the pier.",
            },
            {
                "source_quote": "Il pescatore cammina sul molo all'alba.",
                "subject": "il pescatore",
                "action": "cammina",
                "setting": "alba",
                "objects": [],
                "beat": "Dawn light on the pier.",
            },
        ]
        beats = validate_extracted_beats(raw, narration, limit=3)
        self.assertEqual(len(beats), 1)

    def test_fallback_when_nothing_is_grounded(self):
        beats = validate_extracted_beats([], NARRATION, limit=3)
        self.assertEqual(len(beats), 1)
        self.assertTrue(quote_in_narration(beats[0].source_quote, NARRATION))
        self.assertEqual(beats[0].beat, fallback_beat(NARRATION).beat)


class PersistenceTests(unittest.TestCase):
    def test_loader_accepts_legacy_strings_and_mappings(self):
        beats = normalize_stored_beats([
            "A fisherman walks on the pier.",
            {
                "beat": "Nets dry on the pier.",
                "source_quote": "Le reti sono stese a asciugare.",
                "subject": "reti",
            },
        ])
        self.assertEqual(len(beats), 2)
        self.assertEqual(beats[0].source_quote, "A fisherman walks on the pier.")
        self.assertEqual(beats[1].subject, "reti")
        dumped = beats_as_dicts(beats)
        self.assertEqual(dumped[1]["source_quote"], "Le reti sono stese a asciugare.")


class PromptGroundingTests(unittest.TestCase):
    def test_prompt_must_keep_beat_content(self):
        beat = VisualBeat(
            beat="A fisherman walks along the wooden pier at sunrise.",
            source_quote="Il pescatore cammina sul molo all'alba.",
            subject="il pescatore",
            action="cammina",
        )
        good = check_prompt(
            "A fisherman walks along a wooden pier at sunrise, cinematic light.",
            beat,
            NARRATION,
        )
        self.assertTrue(good.ok, good.summary())
        bad = check_prompt(
            "A diplomat shakes hands in a marble hall.",
            beat,
            NARRATION,
        )
        self.assertFalse(bad.ok)
        self.assertTrue(bad.missing)

    def test_flags_invented_proper_names_and_numbers(self):
        beat = VisualBeat(
            beat="A fisherman walks along the pier.",
            source_quote="Il pescatore cammina sul molo all'alba.",
        )
        result = check_prompt(
            "A fisherman walks along the pier beside John Smith holding 47 drones.",
            beat,
            NARRATION,
        )
        self.assertFalse(result.ok)
        self.assertIn("John Smith", result.extras)
        self.assertIn("47", result.extras)


class PromptPayloadTests(unittest.TestCase):
    def test_prompt_schema_does_not_ask_for_visual_beat(self):
        self.assertEqual(list(PROMPT_ONLY_SCHEMA["properties"]), ["prompt"])
        self.assertNotIn("visual_beat", PROMPT_ONLY_SCHEMA["properties"])

    def test_user_payload_locks_the_beat(self):
        beat = VisualBeat(
            beat="A fisherman walks along the pier.",
            source_quote="Il pescatore cammina sul molo all'alba.",
            subject="il pescatore",
        )
        payload = build_prompt_user_payload({"id": 1, "text": NARRATION}, beat)
        self.assertEqual(payload["locked_visual_beat"]["beat"], beat.beat)
        self.assertIn("narration", payload)
        self.assertNotIn("visual_beats", payload)

    def test_project_profile_is_wrapped_as_defaults_only(self):
        wrapped = wrap_project_profile("Wear thobes in every scene.")
        self.assertIn("UNSPECIFIED DEFAULTS ONLY", wrapped)
        self.assertIn("Wear thobes in every scene.", wrapped)
        self.assertEqual(wrap_project_profile("  "), "")


class ProjectProfileYamlTests(unittest.TestCase):
    def test_long_profiles_are_not_overwritten_by_short_duplicates(self):
        config_dir = os.path.join(os.path.dirname(__file__), "..", "config")
        profiles = load_project_profiles(os.path.abspath(config_dir))
        middle_east = profiles["middle_east_modern"]
        self.assertIn("Preserve every explicit identity", middle_east)
        self.assertNotIn("Never depict Western business suits", middle_east)
        software = profiles["software_delevopment"]
        self.assertNotIn("middle_east_modern", software)
        self.assertIn("PROJECT PROFILE: CORPORATE GLOBAL", profiles["corporate_global"])
        self.assertNotIn("charcoal gray suits", profiles["corporate_global"])
        self.assertIn("PROJECT PROFILE: NATURE DOCUMENTARY", profiles["nature_documentary"])
        self.assertIn("organic wilderness", profiles["nature_documentary"])


if __name__ == "__main__":
    unittest.main()
