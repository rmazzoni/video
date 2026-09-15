import os
import unittest

from prompts.ollama_runtime import (
    is_loopback_host,
    model_is_available,
    normalize_ollama_host,
    parse_model_json,
)
from prompts.beat_feedback import (
    beats_differ,
    extract_guidance_text,
    format_correction_examples,
    record_correction,
)
from prompts.model_prompt_service import (
    PROMPT_ONLY_SCHEMA,
    build_prompt_user_payload,
    wrap_project_profile,
)
from prompts.project_profiles import load_project_profiles
from prompts.prompt_grounding import check_prompt
from prompts.visual_beats import (
    VisualBeat,
    align_prompt_rows_to_beats,
    beats_as_dicts,
    build_extraction_messages,
    dedupe_beats,
    compact_visual_quote,
    ensure_prompt_rows_for_beats,
    fallback_beat,
    fallback_beats,
    is_visual_moment,
    normalize_stored_beats,
    quote_in_narration,
    recover_source_quote,
    slot_is_grounded,
    stub_prompt_row,
    sync_model_prompts_to_beats,
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
        self.assertEqual(len(beats), 2)
        self.assertTrue(quote_in_narration(beats[0].source_quote, NARRATION))
        self.assertTrue(quote_in_narration(beats[1].source_quote, NARRATION))
        self.assertEqual(beats[0].beat, fallback_beat(NARRATION).beat)

    def test_long_scene_keeps_distinct_quotes(self):
        narration = (
            "The drone strike hit the convoy at four in the morning local time. "
            "Eight vehicles. UAE funded Sudanese RSF militia fighters moving through "
            "a contested corridor in southwestern Sudan."
        )
        raw = [
            {
                "source_quote": "The drone strike hit the convoy at four in the morning local time.",
                "subject": "drone strike",
                "action": "hit the convoy",
                "setting": "four in the morning",
                "objects": ["convoy"],
                "beat": "A drone strike hits a convoy at four in the morning.",
            },
            {
                "source_quote": "UAE funded Sudanese RSF militia fighters moving through a contested corridor in southwestern Sudan.",
                "subject": "RSF militia fighters",
                "action": "moving through a contested corridor",
                "setting": "southwestern Sudan",
                "objects": [],
                "beat": "RSF militia fighters move through a contested corridor in southwestern Sudan.",
            },
        ]
        beats = validate_extracted_beats(raw, narration, limit=3)
        self.assertEqual(len(beats), 2)

    def test_whole_narration_is_not_kept_as_the_beat(self):
        narration = (
            "The Saudi-UAE secret war that nobody is talking about just became kinetic, "
            "and the specific implications of that kinetic escalation for the Gulf "
            "Cooperation Council, for the Islamic Military Coalition, and for the "
            "broader regional security architecture that MBS has been building."
        )
        raw = [{
            "source_quote": narration,
            "subject": "Saudi-UAE war",
            "action": "became kinetic",
            "setting": "",
            "objects": [],
            "beat": narration,
        }]
        beats = validate_extracted_beats(raw, narration, limit=3)
        self.assertTrue(all(b.source_quote != narration for b in beats))
        self.assertTrue(all(len(b.source_quote) < len(narration) for b in beats))

    def test_commentary_runon_can_yield_no_beats(self):
        narration = (
            "Let us now examine the broader pattern of Saudi UAE competition and why "
            "the kinetic escalation in Sudan represents a qualitative threshold "
            "crossing rather than just a quantitative increase in the existing "
            "financial and political rivalry between the two states."
        )
        beats = validate_extracted_beats([], narration, limit=3)
        self.assertEqual(beats, [])

    def test_whole_paragraph_quote_is_dropped_as_too_broad(self):
        narration = (
            "The drone strike hit the convoy at four in the morning local time. "
            "Eight vehicles. UAE funded Sudanese RSF militia fighters moving through "
            "a contested corridor in southwestern Sudan."
        )
        raw = [{
            "source_quote": narration,
            "subject": "drone strike",
            "action": "hit the convoy",
            "setting": "Sudan",
            "objects": ["vehicles"],
            "beat": "A drone strike hits a convoy in Sudan.",
        }]
        beats = validate_extracted_beats(raw, narration, limit=3)
        self.assertGreaterEqual(len(beats), 2)
        self.assertTrue(all(len(beat.source_quote) < len(narration) for beat in beats))

    def test_recovers_near_verbatim_quote_to_a_sentence(self):
        recovered = recover_source_quote(
            "The drone strike hit the convoy at 4 in the morning",
            "The drone strike hit the convoy at four in the morning local time. Eight vehicles.",
        )
        self.assertEqual(
            recovered,
            "The drone strike hit the convoy at four in the morning local time.",
        )

    def test_fallback_beats_uses_multiple_sentences(self):
        beats = fallback_beats(NARRATION, limit=3)
        self.assertEqual(len(beats), 2)

    def test_rejects_negation_and_abstract_commentary(self):
        narration = (
            "The drone strike hit the convoy at four in the morning local time. "
            "It was not an Iranian drone. It was not a Russian supplied weapon. "
            "The UAE does not have a formal army in Sudan. "
            "The UAE's RSF relationship in Sudan has been providing Abu Dhabi "
            "with specific strategic assets that the broader MBS master plan "
            "directly competes with."
        )
        raw = [
            {
                "source_quote": "It was not an Iranian drone.",
                "subject": "drone",
                "action": "was not",
                "setting": "",
                "objects": ["drone"],
                "beat": "It was not an Iranian drone.",
            },
            {
                "source_quote": "The UAE does not have a formal army in Sudan.",
                "subject": "UAE",
                "action": "does not have",
                "setting": "Sudan",
                "objects": ["army"],
                "beat": "The UAE does not have a formal army in Sudan.",
            },
            {
                "source_quote": (
                    "The UAE's RSF relationship in Sudan has been providing Abu Dhabi "
                    "with specific strategic assets that the broader MBS master plan "
                    "directly competes with."
                ),
                "subject": "UAE",
                "action": "providing assets",
                "setting": "Sudan",
                "objects": [],
                "beat": "The UAE RSF relationship provides strategic assets.",
            },
            {
                "source_quote": "The drone strike hit the convoy at four in the morning local time.",
                "subject": "drone strike",
                "action": "hit the convoy",
                "setting": "four in the morning",
                "objects": ["convoy"],
                "beat": "A drone strike hits a convoy at four in the morning.",
            },
        ]
        beats = validate_extracted_beats(raw, narration, limit=4)
        self.assertEqual(len(beats), 1)
        self.assertIn("convoy", beats[0].source_quote.lower())
        self.assertFalse(is_visual_moment("It was not a Russian supplied weapon."))
        self.assertFalse(is_visual_moment(
            "The first choice is more sustainable but more costly for UAE political "
            "identity and for MBC's domestic standing as the leader who built UAE "
            "strategic independence."
        ))
        self.assertFalse(is_visual_moment(
            "The Gulf's internal political dynamics are entering a period of stress."
        ))
        self.assertTrue(is_visual_moment(
            "UAE funded Sudanese RSF militia fighters moving through a contested corridor."
        ))
        self.assertTrue(is_visual_moment(
            "The drone strike hit the convoy at four in the morning local time."
        ))

    def test_compacts_visual_kernel_out_of_analysis_sentence(self):
        narration = (
            "The convoy that was struck was moving toward a position that would have "
            "consolidated RSF control over a logistics corridor that Saudi Arabia's "
            "New Silk Road design routes through Saudi territory."
        )
        beats = validate_extracted_beats([], narration, limit=3)
        self.assertGreaterEqual(len(beats), 1)
        self.assertIn("convoy", beats[0].source_quote.lower())
        self.assertNotIn("consolidated", beats[0].source_quote.lower())
        self.assertLess(len(beats[0].source_quote), len(narration))
        kernel = compact_visual_quote(
            "The convoy strike moved the competition into a fourth category "
            "that gulf state internal competition has historically avoided.",
            "The convoy strike moved the competition into a fourth category "
            "that gulf state internal competition has historically avoided.",
        )
        self.assertTrue(kernel)
        self.assertIn("convoy", kernel.lower())
        self.assertNotIn("historically avoided", kernel.lower())


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
        self.assertEqual(dumped[1]["source"], "generated")

    def test_align_prompt_rows_keeps_matching_indexes_and_drops_extras(self):
        beats = [
            VisualBeat(beat="A fisherman walks on the pier.", source_quote="Il pescatore cammina sul molo all'alba."),
        ]
        rows = [
            {"beat": 1, "text": "old prompt one", "visual_beat": "old one"},
            {"beat": 2, "text": "old prompt two", "visual_beat": "old two"},
        ]
        aligned = align_prompt_rows_to_beats(rows, beats, scene_id=1, model_key="zimage")
        self.assertEqual(len(aligned), 1)
        self.assertEqual(aligned[0]["text"], "old prompt one")
        self.assertEqual(aligned[0]["visual_beat"], "A fisherman walks on the pier.")

    def test_ensure_prompt_rows_adds_stubs_for_missing_beats(self):
        beats = [
            VisualBeat(beat="A fisherman walks on the pier.", source_quote="Il pescatore cammina sul molo all'alba."),
            VisualBeat(beat="Nets dry on the pier.", source_quote="Le reti sono stese a asciugare.", source="user_added"),
        ]
        rows = [
            {"beat": 1, "text": "cinematic fisherman prompt", "visual_beat": "old one", "source": "generated"},
        ]
        aligned = ensure_prompt_rows_for_beats(rows, beats, scene_id=1, model_key="schnell")
        self.assertEqual(len(aligned), 2)
        self.assertEqual(aligned[0]["text"], "cinematic fisherman prompt")
        self.assertEqual(aligned[0]["visual_beat"], "A fisherman walks on the pier.")
        self.assertEqual(aligned[1]["text"], "Nets dry on the pier.")
        self.assertEqual(aligned[1]["source"], "pending")
        self.assertEqual(aligned[1]["id"], "scene_001_beat_02_schnell")

    def test_ensure_prompt_rows_updates_pending_text_when_beat_changes(self):
        beats = [VisualBeat(beat="Nets dry on the pier.", source="user_added")]
        rows = [stub_prompt_row(1, "dev", VisualBeat(beat="New visual beat", source="user_added"), 1)]
        aligned = ensure_prompt_rows_for_beats(rows, beats, scene_id=1, model_key="dev")
        self.assertEqual(aligned[0]["text"], "Nets dry on the pier.")
        self.assertEqual(aligned[0]["visual_beat"], "Nets dry on the pier.")
        self.assertEqual(aligned[0]["source"], "pending")

    def test_ensure_prompt_rows_keeps_manual_prompt_text(self):
        beats = [VisualBeat(beat="Nets dry on the pier.", source="manually_edited")]
        rows = [{
            "beat": 1,
            "text": "hand-tuned prompt",
            "visual_beat": "New visual beat",
            "source": "manually_edited",
        }]
        aligned = ensure_prompt_rows_for_beats(rows, beats, scene_id=1, model_key="flux2")
        self.assertEqual(aligned[0]["text"], "hand-tuned prompt")
        self.assertEqual(aligned[0]["visual_beat"], "Nets dry on the pier.")
        self.assertEqual(aligned[0]["source"], "manually_edited")

    def test_sync_model_prompts_copies_beats_onto_every_model(self):
        beats = [
            VisualBeat(beat="A fisherman walks on the pier."),
            VisualBeat(beat="Nets dry on the pier.", source="user_added"),
        ]
        models = {
            "schnell": {
                "profile": "schnell.yaml",
                "prompts": [{"beat": 1, "text": "old schnell", "visual_beat": "old", "source": "generated"}],
                "max_prompts_per_scene": 3,
            }
        }
        synced = sync_model_prompts_to_beats(
            models, beats, scene_id=4, model_keys=("schnell", "zimage", "dev")
        )
        self.assertEqual(set(synced), {"schnell", "zimage", "dev"})
        self.assertEqual(len(synced["schnell"]["prompts"]), 2)
        self.assertEqual(synced["schnell"]["prompts"][0]["text"], "old schnell")
        self.assertEqual(synced["schnell"]["prompts"][1]["text"], "Nets dry on the pier.")
        self.assertEqual(len(synced["zimage"]["prompts"]), 2)
        self.assertEqual(synced["zimage"]["prompts"][0]["text"], "A fisherman walks on the pier.")
        self.assertEqual(synced["dev"]["prompts"][1]["source"], "pending")
        self.assertGreaterEqual(synced["zimage"]["max_prompts_per_scene"], 2)

    def test_extraction_messages_include_guidance(self):
        messages = build_extraction_messages(
            {"id": 1, "text": NARRATION},
            limit=3,
            extra_system="Prefer one beat per action.",
        )
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("Prefer one beat per action.", messages[0]["content"])
        self.assertIn("Il pescatore", messages[1]["content"])


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


class OllamaRuntimeTests(unittest.TestCase):
    def test_parse_model_json_strips_think_and_fences(self):
        payload = parse_model_json(
            "<think>planning</think>\n```json\n{\"visual_beats\": []}\n```"
        )
        self.assertEqual(payload, {"visual_beats": []})

    def test_parse_model_json_extracts_object_from_prose(self):
        payload = parse_model_json(
            'Here you go:\n{"visual_beats": [{"beat": "A fisherman walks."}]}\nDone.'
        )
        self.assertEqual(payload["visual_beats"][0]["beat"], "A fisherman walks.")

    def test_localhost_is_forced_onto_loopback(self):
        self.assertEqual(normalize_ollama_host("http://localhost:11434"), "http://127.0.0.1:11434")
        self.assertEqual(normalize_ollama_host("localhost"), "http://127.0.0.1:11434")
        self.assertTrue(is_loopback_host("http://localhost:11434"))
        self.assertFalse(is_loopback_host("http://192.168.1.10:11434"))

    def test_model_name_matches_tags(self):
        self.assertTrue(model_is_available(["qwen3:8b", "llama3"], "qwen3:8b"))
        self.assertTrue(model_is_available(["qwen3:8b"], "qwen3"))
        self.assertFalse(model_is_available(["llama3"], "qwen3:8b"))


class BeatFeedbackTests(unittest.TestCase):
    def test_record_correction_skips_identical_beats(self):
        beat = VisualBeat(
            beat="A fisherman walks on the pier.",
            source_quote="Il pescatore cammina sul molo all'alba.",
        )
        feedback = {"examples": []}
        self.assertFalse(record_correction(
            feedback, scene_id=1, narration=NARRATION, original=beat, corrected=beat
        ))
        self.assertEqual(feedback["examples"], [])

    def test_record_correction_stores_before_and_after(self):
        original = VisualBeat(
            beat="A diplomat shakes hands.",
            source_quote="A diplomat shakes hands.",
        )
        corrected = VisualBeat(
            beat="A fisherman walks along the pier at dawn.",
            source_quote="Il pescatore cammina sul molo all'alba.",
            subject="il pescatore",
        )
        feedback = {"examples": []}
        self.assertTrue(record_correction(
            feedback, scene_id=1, narration=NARRATION, original=original, corrected=corrected
        ))
        self.assertEqual(len(feedback["examples"]), 1)
        self.assertEqual(feedback["examples"][0]["corrected"]["beat"], corrected.beat)
        self.assertTrue(beats_differ(original, corrected))

    def test_guidance_includes_notes_and_examples(self):
        text = extract_guidance_text(
            "One beat per visual action.",
            [{
                "narration": NARRATION,
                "original": {"beat": "A diplomat.", "source_quote": "A diplomat."},
                "corrected": {
                    "beat": "A fisherman walks on the pier.",
                    "source_quote": "Il pescatore cammina sul molo all'alba.",
                },
            }],
        )
        self.assertIn("PROJECT BEAT NOTES", text)
        self.assertIn("One beat per visual action.", text)
        self.assertIn("LEARN FROM THESE USER CORRECTIONS", text)
        self.assertIn("Il pescatore", text)
        self.assertEqual(extract_guidance_text("  ", [], include_examples=False), "")
        self.assertIn("User correction", format_correction_examples([{
            "corrected": {"beat": "Nets dry.", "source_quote": "Le reti sono stese a asciugare."},
        }]))


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
