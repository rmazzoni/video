# How VID works

VID is a Qt desktop app that turns a written narration into a voiced video
with stills. You edit the story in the app. A local ComfyUI server paints
the stills. A local Ollama/Qwen process extracts visual beats and writes
model prompts.

This document is the map. Specialized contracts live in:

- `docs/image_prompt_pipeline.md` — locked beats, prompt rules, per-model style
- `docs/comfy_role.md` — what ComfyUI owns vs what Qt owns
- `docs/comfy_integration.md` — HTTP bridge, lab tab, workflow JSON

## Start it

Run `launch_with_comfy.py` from `src`. That starts ComfyUI (if it is not
already on the configured host/port), then starts `main.py`. Image stages
fail if ComfyUI is down.

Ollama must be running when you extract beats or build prompts (`qwen3:8b`
by default). TTS uses the system voice engine configured in Settings.

A project is a folder. Typical outputs:

| Path | What it is |
| --- | --- |
| `output/narration.txt` | Scene script |
| `output/model_prompts.yaml` | Shared visual beats + per-model prompt rows |
| `output/preview_images/` | Preview stills (usually Schnell or Z-Image) |
| `output/lightbox/` | Final stills (Dev, HiDream, FLUX.2, …) |
| `output/audio/` | Spoken scene tracks (`scene_NNN.mp3`) |
| `output/draft_clips/` | Preview motion clips — one Ken Burns clip per Schnell/Z-Image beat still |
| `output/preview_video/` | `{project}_preview_video.mp4` and `{project}_preview_with_audio.mp4` |
| `output/final_clips/` | Motion clips from selected stills |
| `output/final_video/` | `{project}_final_video.mp4` and `{project}_final_with_audio.mp4` |

Assembled preview/final video and combined audio files are prefixed with the
project name (from `vid_project.yaml`, else the folder name). Opening an older
project renames `draft`, `draft_video`, and `images` → `preview_images`,
`preview` → `preview_video`, `clips` → `final_clips`, and `final` →
`final_video`.

## Two programs, one job

```
You (Pipeline, Script, Beats, Prompts, Lightbox)
        │
        ▼
   Qt app  ──editorial──  scenes, beats, prompts, TTS, Ken Burns, mux
        │
        │  already-shaped prompt + seed/size/steps
        ▼
   ComfyUI ──GPU render──  one still graph per model → PNG
```

Qt never loads Flux/Z-Image/HiDream weights itself for stills. ComfyUI never
sees the narration, the beat, or the project profile. It only sees a positive
prompt string and sampling numbers.

## What you do in the tabs

1. **Pipeline** — run stages in order (or one stage at a time). This is the
   product path for generating stills and assembling the video.
2. **Script** — edit the narration that scenes are split from.
3. **Dubbing** — voices, timing, language.
4. **Beats** — the locked visual moments extracted from each scene. One beat
   is one still. Curate these; they are shared across every image model.
5. **Prompts** — per-model English prompts derived from those beats. You can
   edit a row by hand (`manually_edited`). Build Prompts fills the rest.
6. **Preview Images** — fast stills for checking composition.
7. **Lightbox** — compare model variants and pick the still that goes to
   clips.
8. **Comfy lab** — send a raw graph to ComfyUI. Not the video pipeline. It
   does not lock beats or prompts.
9. **Settings** — canvas size, which models are enabled, steps/guidance,
   voices, Comfy host.

Do not generate the film from Comfy lab. Lab is for debugging a graph.

## Stage by stage

### 1. Narration → scenes

The script is split into scenes (paragraph or sentence). Each scene is a
unit of voice, beats, and pictures.

### 2. Scenes → visual beats

Qwen reads the scene and returns structured beats: a short photographable
moment with `subject`, `action`, `setting`, `objects`, and a `source_quote`
that must appear in the narration. Python drops commentary, abstract lines,
and quotes that are not in the text.

The beat is the only allowed image content. Empty fields mean “not in the
shot,” not “fill this from the project profile.”

### 3. Beats → prompts

For each enabled model, Qwen writes one English prompt from the **locked
beat only** (temperature 0). It does not get the rest of the scene.

Python then:

- checks the prompt still names the beat (grounding). One retry, then fail
  closed (`ungrounded`) instead of inventing a new shot
- weaves visible ethnicity only when a **person** has a nationality
  (`officer from the UAE`), never `Saudi military drone`
- forces a military convoy to **armored military trucks** and strips
  invented wreckage
- keeps hide/insert on a **wall safe**; the safe stays in the wall; that
  shot is not turned into a portrait of someone holding a box
- appends a short sharp style line last (`Sharp photograph, clear air…`)

Each model has a different length and framing. Schnell wants 12–30 words
and a person facing the camera. Z-Image wants a longer structured
paragraph and a medium-full face. Dev, FLUX.2, and HiDream sit in between.
See `docs/image_prompt_pipeline.md`.

### 4. Prompts → stills

`structure_prompt_for_model()` runs again at render so old saved rows get
the same locks. Then `ComfyImageGenerator` loads that model’s JSON graph,
substitutes only the `@params` the graph declares, and posts it to ComfyUI.

If a placeholder is missing or left as `@sampler`, generation stops. The
contract is `comfy_bridge/graphs.py`.

| Model | Graph | Typical sampling |
| --- | --- | --- |
| FLUX Schnell | `flux1_schnell_image.json` | 4 steps, Flux guidance 0, euler hardcoded |
| Z-Image Turbo | `zimage_turbo_image.json` | 9 steps, CFG 1, res_multistep |
| FLUX Dev | `flux1_dev_image.json` | 20 steps, Flux guidance 3.5, euler hardcoded |
| FLUX.2 Klein | `flux2_image.json` | 4 steps, Flux guidance 1.0, euler hardcoded |
| HiDream-I1 Dev | `hidream_i1_dev_image.json` | 28 steps, CFG 1.5, shift 6 |

Negatives are zeroed on these graphs. Exclusions belong in the positive
prompt. Canvas **1280×720 or 1344×768**; 1024×576 looks soft.

Stills are named `scene_NNN_MODEL_bBB_vV.png` (scene, model, beat, seed
variant). Preview Images writes v2 into `output/preview_images/` and copies
that same file into `output/lightbox/` so the Lightbox tab stays current.
Final Images reuses a newer preview v2 instead of generating that slot again
(v1 and v3 are still unique Lightbox seeds). "Update Lightbox" on a single
beat still regenerates all three variants.

### 5. Stills → clips → video

Selected stills become motion with Ken Burns (in-app) or SVD (Diffusers,
still in-process — not Comfy yet). TTS audio is muxed on the timeline.
That editorial mix is Qt, not ComfyUI.

Ken Burns **auto** pans each clip in one direction only (left or right)
and alternates direction on the next clip, with a slight zoom-in. The
crop window is interpolated from start to end so the frame never pans
both ways inside one clip. **static** holds the still. Re-run Final
Clips after a motion-math change; the clip sidecar (`motion_version`)
invalidates older files.

## Why the prompt lock exists

Without it, the models were unpredictable and you had to redo shots by
hand. Typical failures this pipeline now blocks:

| Beat said | Model did | Lock |
| --- | --- | --- |
| Officer from the UAE walks to the exit | European soldier walking into the room | Visible Emirati appearance; medium-full; door behind, not receding |
| Saudi military drone over a convoy | A Saudi man in the desert | Nationality on kit is not a person |
| Drone strike hits an RSF convoy | A kid’s race car (from “Rapid” + “vehicles”) | Armored military trucks; no invented wreckage |
| Officer hides a document in a wall safe | Handheld safe, retrieve, melted hand | Hide stays hide; safe flush in the wall; no portrait hero shot |
| Any scene | Foggy “cinematic depth” | Sharp / clear air; style slogan last |

Rebuild prompts after changing Qwen instructions if you want the YAML to
match. Re-run images after a render-path change; shaping applies even
without a rebuild.

## Comfy lab vs the product path

There are three ways code can talk to ComfyUI. Only the first is how
videos are made:

1. **Pipeline / Lightbox** → product still JSON. This is the product.
2. **Comfy lab tab** → any labeled graph, including leftovers. Diagnostics.
3. **`vid_full_pipeline.json`** → custom nodes call `PipelineWorker`, which
   calls Comfy again. Frozen. Do not add models or stages.

Leftover graphs: `sd3_image.json` (legacy SDXL), `flux2_video.json` (SVD XT,
not FLUX.2 video, unused by the pipeline).

## Settings that actually reach Comfy

The generator only sends keys listed for that graph. Extra Settings fields
are ignored on purpose:

- Schnell / Dev / FLUX.2: prompt, seed, size, steps, guidance, filename.
  Sampler is euler in the JSON.
- Z-Image: prompt, seed, size, steps, sampler, scheduler, shift. Not
  guidance (CFG is 1).
- HiDream: prompt, seed, size, steps, guidance, sampler, scheduler, shift.

If ComfyUI is not running, the error asks you to start with
`launch_with_comfy.py`.

## Where the code lives

| Area | Path |
| --- | --- |
| Qt window and tabs | `ui/main_window.py` |
| Stage runner | `ui/pipeline_controller.py` |
| Beat extraction | `prompts/visual_beats.py` |
| Prompt generation | `prompts/model_prompt_service.py` |
| Grounding | `prompts/prompt_grounding.py` |
| Identity / face framing | `prompts/visual_identity.py` |
| Convoy trucks, wall safes | `prompts/visual_kit.py` |
| Render-time prompt shape | `prompts/prompt_builder.py` |
| Graph contract | `comfy_bridge/graphs.py` |
| HTTP to Comfy | `comfy_bridge/client.py` |
| Still render | `images/comfy_image_generator.py` |
| Product graphs | `workflows/*_image.json` |
| Frozen Comfy stage nodes | `comfy_nodes/vid_pipeline/` |

Tests: `f:\VID\venv\Scripts\python.exe -m unittest tests.test_visual_beats tests.test_comfy_graphs`
