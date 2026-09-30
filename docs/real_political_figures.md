# Real political figures

How the whole app fits together is in `docs/how_it_works.md`. Prompt lock
and per-model still graphs are in `docs/image_prompt_pipeline.md`. ComfyUI
owns GPU render only (`docs/comfy_role.md`). Show-type picks are in
`docs/show_types_and_models.md`.

This file is the production reference for **painting a recognizable real
person** (a named president, minister, or other public figure) and keeping
that face across beats. It records what the app does today, whether a
ComfyUI LoRA would work, and what to add without moving editorial work
into Comfy.

Nothing in the “add later” sections is wired into the pipeline yet.
Shipping product stills remain prompt-only T2I: Schnell, Z-Image Turbo,
FLUX Dev, FLUX.2 Klein, and HiDream-I1 Dev. No LoRA, IP-Adapter, PuLID,
InstantID, or reference image is on the product path.

## Hardware on this machine

This machine has **16 GB VRAM**. One FLUX Dev still plus a single LoRA
fits with room to spare. A reference-identity graph (PuLID-FLUX or
IP-Adapter) is also in range. Unload the T2I graph before a heavy
image-to-video run; 16 GB will not hold FLUX Dev and a 14B I2V model
at once.

`config/models.yaml` still describes the older **8 GB / RTX 5060**
target. Do not treat that file as the VRAM budget for this box. The
8 GB notes in `docs/show_types_and_models.md` are the conservative
product default, not this machine.

| Job | 8 GB box | This 16 GB box |
| --- | --- | --- |
| FLUX Dev still | Fits (fp8 / Comfy default dtype) | Comfortable |
| Dev + one person LoRA | Tight but usual | Comfortable |
| PuLID-FLUX / IP-Adapter + insightface | Often OOM or quantized-only | Realistic |
| Qwen-Image original 20B FP8 | Not suitable | Borderline; prefer 7B or GGUF Q4 |
| Wan 2.2 14B I2V | GGUF Q4 + Lightning, 480p | Same, less eviction panic |
| T2I and I2V loaded together | No | Still no |

## Product rule

VID locks **beats**, not likeness. A named person in the narration is
allowed into the prompt. The model then paints whatever face it
associates with that name. That is not identity.

| Layer | What it locks today | What it does not lock |
| --- | --- | --- |
| Locked visual beat | Who is in the shot (role, action, place) | A specific human face |
| Prompt | That beat, in English, per model | LoRA trigger words |
| Identity (`prompts/visual_identity.py`) | Nationality → generic appearance; face framing | Macron, Biden, Xi as a person |
| Project profile (`usa_political`, `europe_political`, …) | Unnamed clothes and civic rooms | People, flags, party symbols, outcomes |
| Comfy product graph | Positive prompt + seed/size/steps | LoRA, ControlNet, reference image |

ComfyUI never sees the beat or the name as a special object. It only
sees the already-shaped positive string (`docs/comfy_role.md`).

Political profiles already exist in `config/project_profiles.yaml`.
They fill a suit and a generic civic interior when the beat is silent.
They **never add people**. Using `usa_political` will not produce a
recognizable US official.

## What happens if you only name them

Zero-code path:

1. Put the real name in the narration.
2. Curate the beat `subject` to that name (`Emmanuel Macron`, not
   `the French president`).
3. Optionally mark the prompt row `manually_edited` and keep the name
   at the **start** of the prompt (distilled models overweight the
   start).
4. Generate. Pick in Lightbox.

Grounding (`prompts/prompt_grounding.py` `extra_proper_names`) allows a
proper name that is already in the beat. Qwen will not invent a
politician the beat did not name.

What you get:

- FLUX Dev and HiDream sometimes know a very famous public figure from
  training data. Shot-to-shot the face still drifts.
- Schnell, Z-Image Turbo, and FLUX.2 Klein 4B are the wrong finals for
  a recognizable person. Same rule as period reconstruction: distilled
  models Hollywood the shot.
- Identity lock may add a generic ethnicity clause (`East Asian
  features`) for non-Western names. That fights a specific likeness.
  Western names get face framing only (`clearly detailed face`), not
  likeness.
- Each beat is a different “version” of the person. Ken Burns and later
  I2V cannot fix that. Motion inherits the still.

Use this path only to test whether the name survives the prompt lock.
Do not ship a political show on it.

## Would a ComfyUI LoRA work?

**As a likeness tool on FLUX Dev: yes.** A person LoRA is the usual way
to pin one recurring public figure.

**As a drop-in for this app: no.** Three gaps.

### 1. Product graphs do not load LoRAs

`workflows/flux1_dev_image.json` is `UNETLoader → DualCLIP → KSampler`.
There is no `LoraLoader`. `docs/comfy_integration.md` already records
that no LoRA or ControlNet files are installed or referenced.

Dropping a `.safetensors` into `ComfyUI/models/loras` does nothing
until the graph VID posts wires it in. `ComfyImageGenerator` only
substitutes `@params` the graph declares (`comfy_bridge/graphs.py`).
Extra Settings fields are ignored on purpose.

### 2. LoRAs are per model family

| Still model | Person LoRA from FLUX.1-Dev |
| --- | --- |
| FLUX Dev | Yes — this is the target |
| FLUX Schnell | Sometimes, weaker; do not use as the likeness final |
| Z-Image Turbo | No |
| HiDream-I1 Dev | No |
| FLUX.2 Klein 4B | No |

If you only LoRA the Dev graph, Preview Images stay generic faces and
Lightbox Dev stills can look like the person. That split is usable:
previews are composition, Lightbox is identity.

Do not train or hunt a LoRA for every shipping model. One likeness
graph is enough.

### 3. The prompt lock does not know trigger words

Character LoRAs need a trigger (`ohwx person`, `macron_flux`, …) near
the front of the prompt. Qwen, grounding, and
`structure_prompt_for_model()` will keep a name that is **in the beat**.
They will not insert a LoRA token. They may bury the name under
ethnicity and framing clauses.

VRAM is not the blocker on this 16 GB card. Wiring and prompt lock are.

## Which identity tool to add

| Cast | Mechanism | Why |
| --- | --- | --- |
| Two or three recurring figures (one president, two ministers) | **FLUX Dev person LoRA** | Highest still fidelity; one file per person; cheap on 16 GB |
| Many different politicians per episode | **Reference photo kit** + PuLID-FLUX or IP-Adapter | You will not train a LoRA zoo |
| One-off experiment | Name in the beat + Dev Lightbox pick | No code; likeness will drift |
| Painted editorial of real events | HiDream + Cinematic Editorial Illustrator | Likeness is weaker; style may be the point |
| Exact news photograph | Do not generate. Import a still into Lightbox (not wired) | Diffusion is the wrong tool |

LoRA is the wrong default if the script names whoever is in this week’s
news. Then Qt should own a small **identity kit** (name → reference
still and/or LoRA + trigger) and Comfy should only receive the extra
graph inputs.

Keep that split. Do not put the kit, the beat, or Qwen inside Comfy
(`docs/comfy_role.md`).

## Show type: photoreal political documentary

Photoreal “living present” show with named public figures. This is an
**identity-lock** problem, not a new still architecture.

| Shot | Model | Style | Identity |
| --- | --- | --- | --- |
| Named public figure, medium or medium-full | **FLUX Dev** final | Cinematic | LoRA (small cast) or reference kit (large cast) |
| Crowd, street, building, empty chamber | Dev or HiDream; Z-Image / Schnell draft | Cinematic | None — do not invent faces |
| Maps, seating charts, readable captions | Qwen-Image (add later) | Technical / diagram | None |
| Painted editorial plate of a real event | HiDream | Cinematic Editorial Illustrator | Optional; painted likeness is looser |

Profile: the matching contemporary political profile
(`usa_political`, `europe_political`, `china_usa_political`, …) for
unnamed clothes and rooms only. The profile must not add the figure.

Beat rules that matter more than the model:

1. **Name the person in `subject`.** `the president` is a costume.
   `Emmanuel Macron at a podium in the Élysée press room` is paintable.
2. **Do not invent a person from a country or an institution.**
   `the White House` is a building. `the French government` is not a
   face. Same lock as `Saudi military drone` is a drone.
3. **One face per beat unless the beat names two.** Extra aides and
   crowds are the usual failure mode. Grounding already flags extra
   people.
4. **Keep Schnell / Z-Image off the final Lightbox pick** for the
   named person. They are drafts for blocking.

Do not mix photoreal likeness and painted plates in one cut unless the
show is deliberately two languages (living scene vs commentary plate).

Motion: Ken Burns on the picked still. Later I2V (Wan 2.2 on this
card) should pin the Lightbox still as first frame. Identity across
clips still comes from the still, not from the video model remembering
a face.

## What to do, in order

Do not start by rewriting the Qt pipeline.

### 1. Prove likeness in Comfy lab

- Install a **FLUX.1-Dev** person LoRA into `ComfyUI/models/loras`.
- In the Comfy web UI, duplicate the Dev graph. Add `LoraLoader` (or
  `LoraLoaderModelOnly`) between the UNET and the sampler. Strength
  about 0.8–1.0.
- Prompt with the trigger **first**, then the beat.
- Run from **Comfy lab** or the Comfy UI. Pipeline / Lightbox will not
  use that graph until VID posts it.

If likeness fails here, it will fail in the product too.

### 2. Name them in the beat

Even with a LoRA, the beat is the only image content. Empty `subject`
means “no one.”

- Narration and beat `subject` use the real name.
- Prompt row `manually_edited`; trigger at the start.
- Enable Dev (and maybe HiDream as a non-LoRA alt). Leave Schnell /
  Z-Image as preview only.

### 3. Wire LoRA into the product path (small recurring cast)

Keep identity selection in Qt; keep weights in Comfy.

Minimum change:

- Add `LoraLoader` to `workflows/flux1_dev_image.json`.
- Extend `GraphSpec.params` in `comfy_bridge/graphs.py` with
  `lora_name` and `lora_strength`. Missing placeholders already fail
  closed — a half-wired graph must error, not silently ignore the LoRA.
- Have `images/comfy_image_generator.py` pass those keys.
- Map **person → LoRA file + trigger** at project or beat level. Do
  not hide this inside Qwen.
- Teach `structure_prompt_for_model()` to prepend the trigger and not
  overwrite a specific face with the generic nationality clause.

Do not add LoRA loading to `vid_full_pipeline.json` or
`comfy_nodes/vid_pipeline`. Those paths are frozen.

Preview graphs can stay LoRA-free.

### 4. Add a reference kit instead (large or changing cast)

On 16 GB this is the better product for political shows:

- Qt: named people + one reference portrait each.
- Comfy: LoadImage + PuLID-FLUX or IP-Adapter on the Dev graph (or a
  dedicated likeness graph).
- Beat `subject` matches a kit key; unmatched people stay prompt-only.

Bigger graph than a LoRA loader. Still Qt-owned kit, Comfy-owned
weights. Not in the product graphs today.

## Files that would change

Only if you wire this. The research itself does not require edits.

| Path | Role |
| --- | --- |
| `workflows/flux1_dev_image.json` | Add `LoraLoader` (or reference-image nodes) |
| `comfy_bridge/graphs.py` | Declare the new `@params` |
| `images/comfy_image_generator.py` | Pass LoRA / reference keys |
| `prompts/prompt_builder.py` | Prepend trigger; skip generic identity when a kit face is set |
| `prompts/visual_identity.py` | Do not weave ethnicity over a locked likeness |
| `prompts/prompt_grounding.py` | Allow trigger tokens that are in the kit |
| New: project identity kit YAML | Name → LoRA and/or reference still |

Do not change beat extraction to invent public figures. The beat still
has to quote the narration.

## Quick pick

| You are making | Still model | Identity | Profile | Motion |
| --- | --- | --- | --- | --- |
| Photoreal political, 2–3 recurring figures | Dev final; Schnell / Z-Image draft | FLUX Dev LoRA, proven in lab then wired on Dev only | Matching `*_political` profile | Ken Burns; later Wan I2V on the still |
| Photoreal political, rotating cast | Dev final | Reference kit + PuLID / IP-Adapter (add) | Matching `*_political` profile | Same |
| Political maps, seating, captions | Qwen-Image (add) | None | Technical / diagram (add) | Ken Burns only |
| Painted editorial of real events | HiDream | Optional / none | Topic profile | Ken Burns |
| Prompt-only name test | Dev | None (name in beat) | Matching profile | Ken Burns; expect face drift |

## Do not

- Drop a LoRA into `models/loras` and expect Pipeline or Lightbox to
  use it.
- Use Schnell, Z-Image Turbo, or FLUX.2 Klein as the finished likeness.
- Treat `usa_political` / `europe_political` as a face lock.
- Train a LoRA for every shipping still model.
- Put beats, Qwen, or the identity kit inside a Comfy graph.
- Grow `vid_full_pipeline.json` to load LoRAs.
- Ask I2V to remember a politician for a whole scene. Pin the Lightbox
  still.
- Weave generic nationality appearance on top of a LoRA or reference
  face.
- Invent aides, flags, or crowds the beat did not name.
- Keep FLUX Dev and a 14B video graph loaded together, even on 16 GB.
