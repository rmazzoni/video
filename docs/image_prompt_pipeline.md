# Visual beats, prompts, and image models

How the whole app fits together is in `docs/how_it_works.md`. This file is
the working contract for the beats-to-image path. It exists so later
changes do not recreate the failure modes that made output unpredictable:
profile-written scenes, European default faces, cinematic haze, invented
people on equipment, and Schnell turning a military convoy into a race car.

Re-run images after a render-path change. Rebuild prompts after a Qwen
instruction or grounding change if you want the saved YAML to match.

## Pipeline

```
scene narration
  → Qwen structured beat extraction (shared across models)
  → Python validation (quote must be in the narration)
  → per-model prompt generation (Qwen, temperature 0)
  → lexical grounding (one retry, then fail closed)
  → Python identity / kit lock + style suffix
  → structure_prompt_for_model() at ComfyUI render
  → native ComfyUI graph (Schnell / Z-Image Turbo / Dev / HiDream / FLUX.2)

ComfyUI only receives the already-shaped positive prompt and sampling
params. It does not see the beat, profile, or Qwen. See `docs/comfy_role.md`.
```

Beats live in `output/model_prompts.yaml` and are shared. Each model has its
own prompt rows. ComfyUI renders the row text after `structure_prompt_for_model`.

## Shared rules

These apply to every model.

1. **The locked beat is the only image content.** Empty slots are absent, not
   filled from the project profile, the visual-style essay, or the rest of the
   scene narration. Qwen does not receive the full narration at prompt time.
2. **Do not invent a person.** A nationality on a drone, vehicle, army, desert,
   or force name is not a face. "A drone used by the Saudi military" is a drone.
   "An officer from the UAE" is a person and must look Emirati.
3. **Do not invent wreckage.** A strike hitting a convoy is the strike, not a
   junkyard. "Shattered vehicles" is banned unless the beat names wreckage.
4. **A named military convoy is armored military trucks**, not civilian cars,
   toy cars, or race cars. Schnell reads "Rapid" + "vehicles" as a race car.
5. **No cinematic haze language** unless the beat names weather: photographic
   depth, motivated light, volumetric light, bokeh, bloom, soft focus, spatial
   depth slogans.
6. **Style slogans go last**, never first. Distilled models overweight the
   start of the prompt.
7. **Fail closed.** If a generated prompt fails grounding after one retry, keep
   the locked beat text (`source: ungrounded`) instead of swapping in a template
   and calling it generated. Preview Images and Final Images **paint that stored
   text**. They do not re-run Qwen unless the row has no text at all.
8. **Project profiles are fill-in only** for unnamed clothing or place. They
   are skipped when the beat already names subject and setting. They must never
   add people or replace the beat.
9. **Keep the beat verb.** Hide is not retrieve. A safe in the wall is built
   flush into the wall; the person does not hold the safe. Do not turn that
   action into a portrait of someone holding a small box (hands fuse to metal
   on distilled models). Skip face-hero framing when the shot is a fixture
   interaction (`prompts/visual_kit.py` `apply_prop_lock`).

## Per model

| Model | Prompt length | Person framing | Style suffix | Sampler notes |
| --- | --- | --- | --- | --- |
| FLUX Schnell | 12–30 words, one subject | Medium shot, facing the camera | Sharp photograph, clear air, simple staging | 4 steps, FluxGuidance 0, euler/simple (graph) |
| Z-Image Turbo | 80–160 words, structured | Medium-full, three-quarter, face large and sharp | Sharp photograph, clear air, directional daylight | 9 steps, CFG 1, **res_multistep**/simple, shift 3 |
| FLUX Dev | 40–80 words, one moment | Medium-full, three-quarter, face readable | Sharp photograph, clear air, directional daylight | 20 steps, FluxGuidance **3.5**, euler/simple (graph) |
| FLUX.2 Klein 4B | 40–80 words, one moment | Medium-full, three-quarter, face readable | Sharp photograph, clear air, directional daylight | 4 steps, FluxGuidance **1.0**, euler/simple (graph), Qwen 3 4B encoder |
| HiDream-I1 Dev | 40–80 words, one moment | Medium-full, three-quarter, face readable | Sharp photograph, clear air, one lighting direction | 28 steps, CFG **1.5**, euler/normal, shift 6; no volumetric haze, no repeated color adjectives |

Schnell cannot carry a long essay. Dev, FLUX.2, HiDream, and Z-Image can take
more concrete detail, but not haze or extra people.

Z-Image Turbo ignores negative prompts (KSampler CFG 1). Schnell, Dev, FLUX.2,
and HiDream also zero the negative branch; put exclusions in the **positive**
prompt.

Canvas: **1280×720 or 1344×768**. 1024×576 looks soft, especially faces.

## Render-time shaping

`prompts/prompt_builder.py` → `structure_prompt_for_model()` runs on every
ComfyUI image (`images/comfy_image_generator.py`). It is idempotent.

It will:

- strip known style slogans (including old cinematic ones)
- strip invented `an adult {Nationality} with … face` clauses when no person remains
- weave visible ethnicity only when a **role** is attached to the nationality
  (`officer from the UAE`), never `Saudi military` or `Sudan desert`
- add model-specific face framing when a person is named
- force `military convoy of armored military trucks` and drop invented
  shattered/scattered wreckage (`prompts/visual_kit.py`)
- strip haze phrases
- append the current sharp style suffix and a short quality clause

Existing YAML rows are cleaned at generate time. Rebuild prompts if you want
the stored text to match.

## Files

| Path | Role |
| --- | --- |
| `prompts/visual_beats.py` | Extraction, quote lock, beat validation |
| `prompts/model_prompt_service.py` | Locked-beat system instruction, per-model YAML, fail-closed generate |
| `prompts/prompt_grounding.py` | Required tokens; extras: people, garments, architecture, wreckage, race cars |
| `prompts/visual_identity.py` | Person nationality → appearance; Schnell vs other models' face framing |
| `prompts/visual_kit.py` | Military convoy → armored trucks; strip invented wreckage |
| `prompts/prompt_builder.py` | `structure_prompt_for_model`, haze/style strip |
| `prompts/visual_styles.py` | Short per-model style suffixes (no cinematic essays in the live stack) |
| `config/prompt_profiles/*.yaml` | Per-model writing rules |
| `config/project_profiles.yaml` | Fill-in wardrobe/architecture only |
| `workflows/flux1_schnell_image.json` | Schnell graph |
| `workflows/zimage_turbo_image.json` | Z-Image graph (`@sampler` / `@shift`) |
| `workflows/flux1_dev_image.json` | Dev graph (euler + FluxGuidance) |
| `workflows/flux2_image.json` | FLUX.2 Klein graph (euler + FluxGuidance 1.0, Qwen encoder) |
| `workflows/hidream_i1_dev_image.json` | HiDream graph (`@guidance` CFG, `@shift`, no volumetric haze) |
| `tests/test_visual_beats.py` | Contract tests; run with `f:\VID\venv\Scripts\python.exe -m unittest tests.test_visual_beats` |

## What we already learned not to do

- Do not send the full scene narration into prompt generation.
- Do not prepend "Cinematic photograph, photographic depth, motivated light".
- Do not skip grounding extras for extra people/wardrobe/architecture.
- Do not treat a failed prompt as "generated" after a silent template swap.
- Do not inject a face for `from the UAE` on a **drone** or **convoy**.
- Do not describe a convoy strike as "shattered vehicles".
- Do not turn "hides a document in a wall safe" into retrieving a handheld safe.
- Do not leave Z-Image on euler; use `res_multistep`.
- Do not default the canvas to 1024×576 for final stills.
- Keep the misspelled profile key `software_delevopment` for compatibility.

## Regenerating an existing project

1. Re-extract beats only if the locked beats themselves are wrong.
2. Build Prompts to refresh model rows (skips `manually_edited`).
3. Re-run the image stage. Render shaping applies even without step 2.

Preview (Schnell / Z-Image) and lightbox (Dev / HiDream / FLUX.2) both go
through `structure_prompt_for_model`.

All five image models (Schnell, Z-Image Turbo, Dev, FLUX.2, HiDream) now share
this lock: sharp style last, no invented people on kit, military trucks on
convoy beats, wall safes stay in the wall, hide is not retrieve.
