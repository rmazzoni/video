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
    LOCKED_BEAT_INSTRUCTION,
    ModelPromptService,
    PROMPT_ONLY_SCHEMA,
    beat_needs_profile_defaults,
    build_prompt_user_payload,
    wrap_project_profile,
)
from prompts.prompt_builder import (
    PromptBuilder,
    join_prompt_parts,
    structure_prompt_for_model,
)
from prompts.visual_identity import apply_visual_identity
from prompts.project_profiles import load_project_profiles
from prompts.prompt_grounding import check_prompt
from prompts.visual_beats import (
    VisualBeat,
    align_prompt_rows_to_beats,
    beats_as_dicts,
    build_extraction_messages,
    coerce_beat_index,
    dedupe_beats,
    compact_visual_quote,
    ensure_prompt_rows_for_beats,
    fallback_beat,
    fallback_beats,
    find_prompt_row,
    is_visual_moment,
    normalize_stored_beats,
    prompt_row_is_ready,
    quote_in_narration,
    recover_source_quote,
    slot_is_grounded,
    stub_prompt_row,
    sync_model_prompts_to_beats,
    upsert_prompt_row,
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
        self.assertTrue(is_visual_moment("Executives sat around a conference table."))
        self.assertTrue(is_visual_moment(
            "A technician inspected a wafer in the cleanroom."
        ))
        self.assertTrue(is_visual_moment("The president spoke from a podium."))

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

    def test_find_prompt_row_does_not_index_past_short_lists(self):
        rows = [
            {"beat": 1, "text": "first"},
            {"beat": 2, "text": "second"},
        ]
        self.assertIsNone(find_prompt_row(rows, 3))
        self.assertIsNone(find_prompt_row([], 1))
        self.assertIsNone(find_prompt_row(None, 1))
        self.assertEqual(find_prompt_row(rows, 2)["text"], "second")

    def test_find_prompt_row_uses_position_only_when_beat_field_is_missing(self):
        rows = [{"text": "unnumbered one"}, {"text": "unnumbered two"}]
        self.assertEqual(find_prompt_row(rows, 1)["text"], "unnumbered one")
        self.assertEqual(find_prompt_row(rows, 2)["text"], "unnumbered two")
        numbered = [{"beat": 1, "text": "keep"}, {"beat": 4, "text": "four"}]
        self.assertIsNone(find_prompt_row(numbered, 2))

    def test_coerce_beat_index_rejects_invalid_values(self):
        self.assertEqual(coerce_beat_index(None), 0)
        self.assertEqual(coerce_beat_index(""), 0)
        self.assertEqual(coerce_beat_index("03"), 3)
        self.assertEqual(coerce_beat_index("beat"), 0)
        self.assertEqual(coerce_beat_index(0, 1), 1)

    def test_upsert_prompt_row_replaces_matching_beat(self):
        rows = [{"beat": 1, "text": "old"}, {"beat": 3, "text": "three"}]
        updated = upsert_prompt_row(rows, {"beat": 3, "text": "new three"})
        self.assertEqual([row["text"] for row in updated], ["old", "new three"])
        appended = upsert_prompt_row(rows, {"beat": 2, "text": "two"})
        self.assertEqual([row["beat"] for row in appended], [1, 2, 3])

    def test_pending_prompt_rows_are_not_ready_for_images(self):
        self.assertFalse(prompt_row_is_ready({"beat": 3, "text": "shot", "source": "pending"}))
        self.assertFalse(prompt_row_is_ready({"beat": 3, "text": "shot", "source": "ungrounded"}))
        self.assertTrue(prompt_row_is_ready({"beat": 3, "text": "shot", "source": "generated"}))

    def test_ensure_prompt_rows_maps_unnumbered_rows_by_position(self):
        beats = [
            VisualBeat(beat="A fisherman walks on the pier."),
            VisualBeat(beat="Nets dry on the pier."),
        ]
        rows = [{"text": "old prompt one", "source": "generated"}]
        aligned = ensure_prompt_rows_for_beats(rows, beats, scene_id=5, model_key="schnell")
        self.assertEqual(len(aligned), 2)
        self.assertEqual(aligned[0]["text"], "old prompt one")
        self.assertEqual(aligned[0]["beat"], 1)
        self.assertEqual(aligned[1]["source"], "pending")
        self.assertEqual(aligned[1]["beat"], 2)

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
        self.assertEqual(aligned[0]["text"], "A fisherman walks on the pier.")
        self.assertEqual(aligned[0]["source"], "pending")
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
        self.assertEqual(aligned[0]["text"], "A fisherman walks on the pier.")
        self.assertEqual(aligned[0]["source"], "pending")
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

    def test_ensure_prompt_rows_keeps_generated_when_beat_unchanged(self):
        beats = [VisualBeat(beat="A fisherman walks on the pier.")]
        rows = [{
            "beat": 1,
            "text": "cinematic fisherman prompt",
            "visual_beat": "A fisherman walks on the pier.",
            "source": "generated",
        }]
        aligned = ensure_prompt_rows_for_beats(rows, beats, scene_id=1, model_key="schnell")
        self.assertEqual(aligned[0]["text"], "cinematic fisherman prompt")
        self.assertEqual(aligned[0]["source"], "generated")

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
        self.assertEqual(synced["schnell"]["prompts"][0]["text"], "A fisherman walks on the pier.")
        self.assertEqual(synced["schnell"]["prompts"][0]["source"], "pending")
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
        self.assertTrue(bad.missing or bad.extras)

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

    def test_allows_camera_and_aspect_ratio_numbers(self):
        beat = VisualBeat(
            beat="A fisherman walks along the pier.",
            source_quote="Il pescatore cammina sul molo all'alba.",
        )
        result = check_prompt(
            "A fisherman walks along the pier, 35mm lens, aspect ratio 16:9.",
            beat,
            NARRATION,
        )
        self.assertTrue(result.ok, result.summary())

    def test_rejects_extra_people_garments_and_architecture(self):
        beat = VisualBeat(
            beat="A drone strike hits a convoy at four in the morning.",
            source_quote="The drone strike hit the convoy at four in the morning local time.",
        )
        drifted = check_prompt(
            "A senior official in a thobe stands in a marble atrium near a convoy.",
            beat,
        )
        self.assertFalse(drifted.ok)
        self.assertTrue(drifted.extras)
        self.assertTrue(
            any(term in drifted.extras for term in ("official", "thobe", "marble", "atrium")),
            drifted.extras,
        )
        grounded = check_prompt(
            "A drone strike hits a convoy at four in the morning under hard night light.",
            beat,
        )
        self.assertTrue(grounded.ok, grounded.summary())

    def test_allows_appearance_and_uniform_of_named_officer(self):
        beat = VisualBeat(
            beat=(
                "A high-ranking officer from the United Arab Emirates strides "
                "toward the exit of a modern glass-walled meeting room."
            ),
            subject="a high-ranking officer from the United Arab Emirates",
            action="strides toward the exit",
            setting="a modern glass-walled meeting room",
        )
        result = check_prompt(
            "A high-ranking officer from the United Arab Emirates, an adult "
            "Emirati man with Gulf Arab features and olive-brown complexion, "
            "wears a UAE military dress uniform and strides toward the exit of "
            "a modern glass-walled meeting room.",
            beat,
        )
        self.assertTrue(result.ok, result.summary())
        drifted = check_prompt(
            "An Emirati officer and an aide stand in a marble atrium.",
            beat,
        )
        self.assertFalse(drifted.ok)
        self.assertTrue(
            any(term in drifted.extras for term in ("aide", "atrium", "marble")),
            drifted.extras,
        )


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
        self.assertNotIn("narration", payload)
        self.assertNotIn("visual_beats", payload)

    def test_project_profile_is_wrapped_as_defaults_only(self):
        wrapped = wrap_project_profile("Wear thobes in every scene.")
        self.assertIn("UNSPECIFIED WARDROBE AND ARCHITECTURE ONLY", wrapped)
        self.assertIn("Wear thobes in every scene.", wrapped)
        self.assertEqual(wrap_project_profile("  "), "")
        complete = VisualBeat(
            beat="A fisherman walks on the pier.",
            subject="il pescatore",
            setting="molo",
        )
        self.assertFalse(beat_needs_profile_defaults(complete))
        self.assertTrue(beat_needs_profile_defaults(VisualBeat(beat="A fisherman walks.")))

    def test_locked_instruction_asks_for_a_staged_scene(self):
        self.assertIn("Do not copy the beat sentence verbatim", LOCKED_BEAT_INSTRUCTION)
        self.assertIn("Do not mention aspect ratio", LOCKED_BEAT_INSTRUCTION)
        self.assertIn("visible face and complexion", LOCKED_BEAT_INSTRUCTION.lower())
        self.assertIn("direction of travel", LOCKED_BEAT_INSTRUCTION.lower())
        self.assertIn("haze", LOCKED_BEAT_INSTRUCTION.lower())

    def test_user_payload_forbids_aspect_ratio(self):
        beat = VisualBeat(beat="A fisherman walks along the pier.")
        payload = build_prompt_user_payload({"id": 1, "text": NARRATION}, beat)
        self.assertIn("aspect ratio", payload["writing_rules"].lower())


class PromptAssemblyTests(unittest.TestCase):
    def test_join_prompt_parts_avoids_double_periods(self):
        joined = join_prompt_parts(
            "Cinematic photograph, natural materials.",
            "A meeting of Arab leaders in a conference room of the Gulf Cooperation Council.",
        )
        self.assertEqual(
            joined,
            "Cinematic photograph, natural materials. "
            "A meeting of Arab leaders in a conference room of the Gulf Cooperation Council.",
        )
        self.assertNotIn("..", joined)

    def test_prompt_builder_omits_aspect_ratio(self):
        prompt = PromptBuilder(style_preset="cinematic", default_aspect_ratio="16:9").build_prompt(
            {"id": 1, "text": "A meeting of Arab leaders in a conference room."}
        )
        self.assertNotIn("Aspect ratio", prompt)
        self.assertNotIn("16:9", prompt)

    def test_template_prompt_is_style_prefix_plus_beat(self):
        profiles_dir = os.path.join(
            os.path.dirname(__file__), "..", "config", "prompt_profiles"
        )
        service = ModelPromptService(profiles_dir, "qwen3:8b", "http://127.0.0.1:11434")
        beat = VisualBeat(
            beat="A meeting of Arab leaders in a conference room of the Gulf Cooperation Council.",
            source="user_added",
        )
        prompt = service._template_prompt(
            {"id": 1, "text": NARRATION},
            {"model_key": "schnell", "style_preset": "cinematic"},
            beat,
        )
        self.assertIn("Cinematic photograph", prompt)
        self.assertIn("Arab leaders", prompt)
        self.assertLess(
            prompt.lower().index("arab leaders"),
            prompt.lower().index("cinematic photograph"),
        )
        self.assertNotIn("Aspect ratio", prompt)
        self.assertNotIn("volumetric light", prompt)
        self.assertNotIn("characters facing the camera", prompt)
        self.assertNotIn("..", prompt)

    def test_zimage_template_uses_sharp_not_hazy_style(self):
        profiles_dir = os.path.join(
            os.path.dirname(__file__), "..", "config", "prompt_profiles"
        )
        service = ModelPromptService(profiles_dir, "qwen3:8b", "http://127.0.0.1:11434")
        beat = VisualBeat(
            beat="A meeting of Arab leaders in a conference room of the Gulf Cooperation Council.",
            source="user_added",
        )
        prompt = service._template_prompt(
            {"id": 1, "text": NARRATION},
            {"model_key": "zimage", "style_preset": "cinematic"},
            beat,
        )
        self.assertIn("Sharp photograph", prompt)
        self.assertIn("clear air", prompt)
        self.assertNotIn("photographic depth", prompt.lower())
        self.assertNotIn("motivated light", prompt.lower())
        self.assertNotIn("volumetric", prompt.lower())

    def test_system_instruction_skips_style_essay_and_complete_beats(self):
        profiles_dir = os.path.join(
            os.path.dirname(__file__), "..", "config", "prompt_profiles"
        )
        service = ModelPromptService(
            profiles_dir,
            "qwen3:8b",
            "http://127.0.0.1:11434",
            project_profile_text="Wear thobes in every scene.",
        )
        profile = service.load_profile("schnell")
        complete = VisualBeat(
            beat="A fisherman walks on the pier.",
            subject="il pescatore",
            action="cammina",
            setting="molo",
        )
        system = service._system_instruction_for_beat(profile, complete)
        self.assertNotIn("Wear thobes", system)
        self.assertNotIn("GLOBAL VISUAL STYLE", system)
        self.assertIn("LOCKED VISUAL BEAT", system)
        incomplete = VisualBeat(beat="A fisherman walks on the pier.")
        system2 = service._system_instruction_for_beat(profile, incomplete)
        self.assertIn("Wear thobes", system2)
        self.assertNotIn("GLOBAL VISUAL STYLE", system2)

    def test_hidream_template_avoids_volumetric_keyword_pile(self):
        profiles_dir = os.path.join(
            os.path.dirname(__file__), "..", "config", "prompt_profiles"
        )
        service = ModelPromptService(profiles_dir, "qwen3:8b", "http://127.0.0.1:11434")
        beat = VisualBeat(beat="A meeting of Arab leaders in a conference room.")
        prompt = service._template_prompt(
            {"id": 1, "text": NARRATION},
            {"model_key": "hidream"},
            beat,
        )
        self.assertIn("Clear photograph", prompt)
        self.assertIn("Arab leaders", prompt)
        self.assertNotIn("volumetric", prompt.lower())
        self.assertNotIn("Aspect ratio", prompt)


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
        self.assertIn("Fill only unspecified clothing or place", middle_east)
        self.assertIn("Never add people", middle_east)
        self.assertNotIn("Prefer one principal person", middle_east)
        software = profiles["software_delevopment"]
        self.assertNotIn("middle_east_modern", software)
        self.assertIn("PROJECT PROFILE: CORPORATE GLOBAL", profiles["corporate_global"])
        self.assertNotIn("charcoal gray suits", profiles["corporate_global"])
        self.assertIn("PROJECT PROFILE: NATURE DOCUMENTARY", profiles["nature_documentary"])
        self.assertIn("organic wilderness", profiles["nature_documentary"])
        self.assertIn("Gulf or Arab nationality", middle_east)


class VisualIdentityTests(unittest.TestCase):
    UAE_PROMPT = (
        "Cinematic photograph, natural materials, photographic depth, motivated light. "
        "A high-ranking officer from the United Arab Emirates strides toward the exit "
        "of a modern, glass-walled meeting room within the Gulf Cooperation Council. "
        "The space is illuminated by natural light, reflecting off sleek surfaces and "
        "contemporary architecture."
    )

    def test_weaves_emirati_appearance_into_uae_officer_prompt(self):
        scene = (
            "A high-ranking officer from the United Arab Emirates strides toward "
            "the exit of a modern, glass-walled meeting room."
        )
        result = apply_visual_identity(scene)
        self.assertIn("Emirati", result)
        self.assertIn("Gulf Arab", result)
        self.assertIn("olive-brown complexion", result)
        self.assertIn("United Arab Emirates, an adult Emirati", result)
        self.assertIn("strides toward the exit", result)
        self.assertIn("receding from the camera", result)

    def test_does_not_duplicate_identity_or_blocking(self):
        once = apply_visual_identity(
            "A high-ranking officer from the United Arab Emirates strides toward the exit."
        )
        twice = apply_visual_identity(once)
        self.assertEqual(once.lower().count("emirati"), twice.lower().count("emirati"))
        self.assertEqual(once.lower().count("receding"), twice.lower().count("receding"))

    def test_skips_western_default_scenes(self):
        scene = "A fisherman walks along the pier at dawn."
        self.assertEqual(apply_visual_identity(scene), scene)


class RenderPromptTests(unittest.TestCase):
    def test_zimage_moves_style_to_end_and_states_identity(self):
        prompt = VisualIdentityTests.UAE_PROMPT
        rendered = structure_prompt_for_model(prompt, "zimage-turbo")
        lower = rendered.lower()
        self.assertLess(lower.index("emirati"), lower.index("sharp photograph"))
        self.assertLess(lower.index("officer"), lower.index("sharp photograph"))
        self.assertIn("receding from the camera", lower)
        self.assertIn("no extra people", lower)
        self.assertIn("no watermark", lower)
        self.assertIn("sharp focus", lower)
        self.assertIn("clear air", lower)
        self.assertNotIn("photographic depth", lower)
        self.assertNotIn("motivated light", lower)
        again = structure_prompt_for_model(rendered, "zimage-turbo")
        self.assertEqual(again.lower().count("emirati"), rendered.lower().count("emirati"))
        self.assertEqual(again.lower().count("no extra people"), 1)
        self.assertEqual(again.lower().count("sharp photograph"), 1)

    def test_schnell_gets_identity_without_turbo_constraints(self):
        prompt = VisualIdentityTests.UAE_PROMPT
        rendered = structure_prompt_for_model(prompt, "flux-schnell")
        self.assertIn("Emirati", rendered)
        self.assertNotIn("No extra people, no text, no watermark, no logos.", rendered)
        self.assertNotIn("Sharp focus, clear air, crisp detail.", rendered)


if __name__ == "__main__":
    unittest.main()
