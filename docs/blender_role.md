# Blender's role in VID

How the whole app fits together is in `docs/how_it_works.md`. ComfyUI owns
GPU stills (and later optional img2vid) in `docs/comfy_role.md`. Show-type
picks are in `docs/show_types_and_models.md`. Named public figures are in
`docs/real_political_figures.md`.

This file records whether Blender belongs **inside this app** or as a
**separate 3D product**. It is a decision document. Nothing here is wired.

Shipping motion is Ken Burns (`clip_engine: ken_burns`). SVD is leftover.
There is no Blender binary, `.blend` template, or clip engine in the tree.

## Decision

**Keep this app. Do not start a second VID. Do not swallow Blender’s
editor into the Qt tabs.**

Blender only belongs here if it is another **frame backend**, the same
way ComfyUI is: Qt still owns the story, beats, Lightbox, TTS, and mux.
Blender runs headless, returns PNGs or an MP4, and exits.

```
You (Pipeline, Script, Beats, Prompts, Lightbox)
        │
        ▼
   Qt app  ──editorial──  scenes, beats, prompts, TTS, Ken Burns, mux
        │
        ├── already-shaped prompt + seed/size/steps
        ▼
   ComfyUI ──GPU stills──  one still graph per model → PNG
        │
        └── (later, optional) still path + motion request
            ▼
   Blender ──headless──  clip or PNG sequence → assembler
```

Do not put the outliner, shaders, camera rigs, or VSE inside Pipeline,
Lightbox, or a “Blender lab” tab. That is a different product, and it
would fight the contracts you already have.

## What this app already is

VID is still-first 2D editorial:

```
narration → beats → prompts → Comfy still → Lightbox pick
         → Ken Burns (or later I2V) → mux
```

Comfy never sees the beat. Ken Burns never sees a 3D world. A `.blend`
file, a camera rig, and a Cycles sample count are a third language.
Lightbox comparing Schnell / Dev / HiDream variants has no equivalent
in Blender.

Clip engines today (`ui/pipeline_controller.py`, Settings):

| Engine | Status |
| --- | --- |
| `ken_burns` | Product default. ffmpeg crop/scale on the picked still. |
| `svd` | Legacy Diffusers. Do not use. |
| Comfy img2vid | Reserved (`workflows/flux2_video.json`). Not product. |
| Blender | **Not present.** Would be a fourth engine, not a new app. |

A third (or fourth) `clip_engine` value is a real extension point. A
Blender authoring tab is not.

## Hardware on this machine

This machine has **16 GB VRAM**. That is enough for FLUX Dev plus a
LoRA, **or** for Cycles, **or** for a heavy I2V graph. It is not enough
for two of those loaded together.

Unload Comfy stills before Blender touches the GPU. Same eviction rule
as T2I vs I2V in `docs/show_types_and_models.md` and
`docs/real_political_figures.md`. `config/models.yaml` still describes
the older 8 GB / RTX 5060 target; do not treat that file as this box’s
budget.

## What “AI rendering in Blender” usually means

The answer changes with the job.

| Job | Integrate into VID? | New app? |
| --- | --- | --- |
| AI denoise on Cycles/EEVEE (OptiX, OIDN) | No — ordinary 3D, not this pipeline | Use Blender itself |
| Parallax / real camera move on a Lightbox still (still on a plane, camera flies) | **Yes, later** — new `clip_engine`, `blender --background` | No |
| Depth/normal from a crude 3D block-in → Comfy ControlNet | Possible as a backend, heavy | Not a new VID |
| Rigged 3D doubles of politicians, reusable sets, lighting, animation | No | **Yes — or just work in Blender** |
| Text-to-3D mesh, then lookdev and render | No | New 3D product |
| Replace the timeline/mux with Blender VSE | No | No; ffmpeg already owns that |

Cycles with AI denoise is not generative identity. It will not paint a
named public figure from a locked beat. It renders meshes you already
have.

## When integration is the right move

Add Blender **inside this app** only if the contract stays:

```
Qt  →  already-chosen Lightbox still (and/or a tiny motion request)
        ↓
Blender (no UI)  →  MP4 or PNG sequence
        ↓
existing clip assembler / TTS mux
```

The one job that fits: **better motion than Ken Burns on a picked
still** (slight parallax, real ease, maybe a 2.5D projection). That is
a clip engine, not a new application.

How it would sit:

- Preview clips stay Ken Burns (fast, parallel, 1280×720).
- Final clips could call headless Blender the same way they might later
  call Wan I2V — only on shots that need it.
- Maps, diagrams, titles, and holds stay Ken Burns.
- Qt does not load `.blend` authoring.
- Do not grow `vid_full_pipeline.json` or `comfy_nodes/vid_pipeline`.
- Motion params belong in Qt (or a sidecar), not in a Blender scene the
  user must open.

Suggested later key, not wired: `clip_engine: blender` next to
`ken_burns`. Do not overload the `svd` branch.

## When you should not stuff it in here

A photoreal 3D political or history show (reusable character, forum,
chamber, camera package) is **not** a VID feature. This app locks 2D
beats and prompt strings. It has no asset library, no rig, no shot
layout, no lighting.

Building that in Qt means reimplementing Blender badly, while also
keeping Comfy, Qwen, TTS, and Ken Burns. That is how the product stops
being shippable.

For that work: use Blender (or a small Blender-centric tool) as the
DCC. You can still **import** a rendered still into Lightbox later if
you want VID to voice and assemble it. That is a file handoff, not a
merge. Import-into-Lightbox is not wired today.

Do not:

- Start a second Qt app that is “VID but with Blender.”
- Embed the Blender UI, Python scripting workspace, or VSE.
- Put beats, Qwen, or project profiles into a `.blend`.
- Expect a 3D double to replace the likeness path in
  `docs/real_political_figures.md` (FLUX Dev LoRA or a reference kit).

## What to build next instead

For the shows already on the map (named public figures, still-first
film, historical reconstruction, schemas), Blender is the wrong next
piece.

1. **Likeness** — FLUX Dev LoRA or a reference kit
   (`docs/real_political_figures.md`).
2. **Living motion** — Comfy image-to-video from the Lightbox still,
   not Cycles (`docs/show_types_and_models.md`).
3. **Ken Burns** — keep for maps, diagrams, holds, and preview.

Blender becomes interesting **after** those, and only as headless
motion or as a separate 3D show.

## Product vs later

| Layer | Today | Later, if ever |
| --- | --- | --- |
| Editorial app | Qt VID | Unchanged |
| Stills | Comfy T2I graphs | Unchanged; likeness on Dev |
| Preview motion | Ken Burns | Ken Burns |
| Final motion | Ken Burns (SVD unused) | I2V on action stills; optional headless Blender on 2.5D shots |
| 3D character/set show | Out of scope | Separate Blender product; optional PNG handoff into Lightbox |
| Timeline / TTS | Qt + ffmpeg | Unchanged |

## Files that would change

Only if you add a headless clip engine. This document does not require
those edits.

| Path | Role |
| --- | --- |
| `ui/pipeline_controller.py` | Branch on `clip_engine` for preview/final clips |
| `ui/main_window.py` | Settings combo (`ken_burns`, `svd` today) |
| New: `video/blender_generator.py` | `blender --background` + template `.blend` |
| New: a motion template `.blend` | Still-on-plane, camera start/end, output size |
| `docs/show_types_and_models.md` | Motion table |

Do not add a Blender tab next to Comfy lab. Lab is for debugging a
Comfy graph. Blender debugging happens in Blender.

## Do not

- Develop a new VID to host Blender.
- Put Blender’s scene editor in this Qt app.
- Treat Cycles AI denoise as a likeness or still-generation backend.
- Keep FLUX Dev and Blender Cycles loaded together on 16 GB.
- Replace Ken Burns previews with Blender.
- Replace ffmpeg mux with the VSE.
- Grow the frozen Comfy stage loop to call Blender.
- Expect I2V or Cycles to remember a face; pin the Lightbox still.
