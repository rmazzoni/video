# Show types, still models, and motion

How the whole app fits together is in `docs/how_it_works.md`. Prompt lock
and per-model still graphs are in `docs/image_prompt_pipeline.md`. ComfyUI
owns GPU render only (`docs/comfy_role.md`).

This file is the production reference for **which still model, visual
style, project profile, and clip engine to use** for a given kind of
show. It records decisions, not a shopping list. Hardware assumed in
`config/models.yaml`: **RTX 5060, 8 GB VRAM**. One heavy graph at a time;
evict stills before any image-to-video run.

Nothing in the “add later” sections is wired into the pipeline yet.
Shipping product stills remain Schnell, Z-Image Turbo, FLUX Dev, FLUX.2
Klein, and HiDream-I1 Dev. Shipping motion is Ken Burns (default) or
legacy SVD (do not use).

## Product rule

VID is still-first. Lightbox stills own identity, kit, period, and
composition. Motion only animates a picked still. Do not generate a
sequence from the narration and hope the lock survives.

| Layer | What it is | Who owns it |
| --- | --- | --- |
| Locked visual beat | The only image content | Qt / Qwen extract |
| Project profile | Fill-in unnamed clothing or place | Qt YAML |
| Visual style | Photograph vs editorial illustration | Settings + `prompts/visual_styles.py` |
| Still model | Paints the beat | ComfyUI graph |
| Clip engine | Ken Burns pan/zoom, or later image-to-video | Qt; I2V would be Comfy |
| Timeline / TTS | Duration, pad, mux | Qt |

## Still models in the product

| Model | Role | Strength | Weakness on this card |
| --- | --- | --- | --- |
| FLUX Schnell | Fast preview | Cheap 4-step draft | Distilled; Hollywood tropes; garbles diagrams and text |
| Z-Image Turbo | Fast preview | Sharp photo draft; same Alibaba family as Qwen-Image | Photo-biased; fights illustration slogans; no readable schemas |
| FLUX Dev | Photo final | Follows a long locked beat; period costume and masonry | Slow; not for labeled diagrams |
| FLUX.2 Klein 4B | Photo variant | 8 GB friendly final-ish look | Weaker than Dev on hard costume lock |
| HiDream-I1 Dev | Painted or photo final | Best of the five at authored illustration; also usable photo | Slow (28 steps); not for infographics |

Negatives are zeroed. Exclusions go in the positive prompt. Canvas
**1280×720 or 1344×768**. Preview stills: Schnell / Z-Image. Finals:
Dev / HiDream / FLUX.2, picked in Lightbox.

## Visual styles in the product

Settings has two live styles (`prompts/visual_styles.py`):

| Key | Display name | Use |
| --- | --- | --- |
| `cinematic` | Cinematic | Photograph. Default. Style slogan last: sharp, clear air, no haze unless the beat names weather. |
| `cinematic_editorial_illustrator` | Cinematic Editorial Illustrator | Painted editorial still, not a photograph. Natural proportions, limited palette, no anime, no plastic 3D. |

Older `style_presets.py` names (`anime`, `ghibli`, `watercolor`, …) are
legacy prompt-builder strings. They are not a substitute for a model
that was trained on that look.

**Style slogans go last.** Distilled models overweight the start of the
prompt. If “sharp photograph” leads, Schnell and Z-Image will stay
photographic even when the style is illustration.

## Project profiles

Profiles fill **only** unnamed clothing or place. They never add people,
crowds, flags, or events. They are skipped when the beat already names
subject and setting.

Every shipped profile in `config/project_profiles.yaml` is
**contemporary** (modern dress, modern rooms). `middle_east_modern`
explicitly says “not ancient.” There is **no historical / Roman /
ancient Mediterranean profile** yet. Using a modern profile on a period
show will dress the beat in suits and glass.

Keep the misspelled key `software_delevopment` if you touch that file.

## Motion in the product

| Engine | Where | Use |
| --- | --- | --- |
| **Ken Burns** (`clip_engine: ken_burns`) | `video/ken_burns_generator.py` via ffmpeg crop/scale | Default. One pan direction per clip, alternate L/R, slight zoom. Preview 1280×720 parallel; finals 1920×1080 parallel. |
| **SVD XT** (`clip_engine` not ken_burns) | Diffusers in-process, `video/video_generator.py` | Legacy. ~14 frames, no motion prompt, warps the still. **Do not use.** |
| `workflows/flux2_video.json` | Leftover SVD graph | Unused. Reserved if clips move to Comfy img2vid later. |
| **Blender** (not wired) | Headless `blender --background` as a later `clip_engine` | Optional 2.5D camera on a Lightbox still. Not a 3D DCC inside Qt. See `docs/blender_role.md`. |

Ken Burns **auto** interpolates the crop (zoom 1.12→1.38), never starts
at zoom 1.0, and does not pan both ways inside one clip. **static**
holds the still. Re-run clips after a motion-math change; the sidecar
`motion_version` invalidates old files.

Preview clips are **one Ken Burns clip per beat still**, not one clip
per scene. Scene TTS is split across that scene’s clips; the assembler
freeze-pads only the last clip of the group.

## Show type: technical drafts and schemas

Diagrams, architecture overviews, flowcharts, labeled boards, PPT-like
slides, whiteboards.

**Do not use the photo models as the finished diagram.** They paint a
photograph of a whiteboard. Labels are fake text; boxes and arrows
wander.

| Shot | Model | Style | Profile |
| --- | --- | --- | --- |
| Labeled schema, infographic, slide, readable text | **Qwen-Image** (add later; 2.0 7B or original 20B GGUF Q4 + Lightning 8-step) | New technical/diagram profile, not cinematic | New: white or grid ground, thin black lines, sans-serif labels, no people unless named, no haze |
| Illustrated system drawing around a schema | Qwen-Image | Graphic illustration, not oil-paint editorial | Same technical profile |
| Exact topology (CAD, IEC, wiring that must be right) | **Not diffusion.** Render Mermaid / Graphviz / draw.io to PNG, then Ken Burns | n/a | n/a |

`software_delevopment` currently **forbids readable screens**. A
technical show needs a different profile, the opposite of that line.

On 8 GB: Qwen-Image original FP8 wants ~16 GB. Use **GGUF Q4 + Lightning**
or **Qwen-Image 2.0 (7B)**. Ideogram 4.0 is stronger at boxed JSON
layouts but wants ~12–16 GB; not the first add.

Motion for schemas is **Ken Burns only**. Image-to-video smears lines
and text.

## Show type: illustration

Painted, graphic, comic, or anime video made of stills plus Ken Burns
(or later I2V on character shots).

You already have the illustration path. Turn on **Cinematic Editorial
Illustrator** before adding a sixth photo model.

| Look | Model | Style | Notes |
| --- | --- | --- | --- |
| Editorial / documentary painting (New Yorker, history plate) | **HiDream** final, Dev as alt | Cinematic Editorial Illustrator | Schnell / Z-Image only as drafts; they slip back to plastic skin |
| Graphic, poster, comic panel, labeled illustration | **Qwen-Image** (add later) | Illustration / graphic, not cinematic | Same model as technical schemas |
| Anime / Ghibli / character sheets | **SDXL Illustrious or NoobAI** (add later) | anime / ghibli preset | Current illustration style **forbids** anime. Do not prompt FLUX or HiDream into it. |

Ken Burns on painted shapes is cleaner than on photographs.

## Show type: historical reconstruction (e.g. Roman Empire)

Photoreal “living period” documentary. This is **not** a new still
architecture. It is a period-lock problem.

| Shot | Model | Style |
| --- | --- | --- |
| People, streets, interiors, battles | Dev or HiDream final; Z-Image / Schnell draft | Cinematic |
| Maps, campaign diagrams, timelines, readable Latin | Qwen-Image (add later) | Technical / diagram |
| Painted history plate | HiDream | Cinematic Editorial Illustrator |

Do not mix photoreal reconstruction and painted plates in one cut unless
the show is deliberately two languages (living scene vs map).

**Add a period project profile before generating.** Example fill-in only
when the beat is silent:

- Person, no garments: role-correct 1st-century dress (tunic / toga /
  lorica for the named rank). No Hollywood leather, no medieval plate.
- Place, unnamed: inhabited period setting (insula, forum, castra,
  painted plaster). Not the modern tourist ruin, not glass and steel.
- Never invent crowds, eagles, or battles the beat did not name.

Two beat rules matter more than the model:

1. **Living city vs ruin.** Unqualified “Rome” in these models is today’s
   Forum. If the narration is the Empire at work, the beat must say
   inhabited 1st-century Rome, not ruins.
2. **Name the century and the role.** “A Roman soldier” is a costume
   party. “A 1st-century legionary in lorica segmentata on a packed
   street of insulae” is paintable.

Distilled preview models Hollywood the shot: too-clean marble, leather
miniskirts, modern gym bodies, SPQR banners on everything. Keep them off
the final Lightbox pick.

## Show type: generated video sequences (not Ken Burns)

Short **image-to-video** clips from a Lightbox still. First frame = the
picked still. Optional last frame = the next beat still, so a scene can
walk from beat 1 to beat 2.

This is **not** in the product. `docs/comfy_role.md` already reserved
Comfy for later img2vid. Do not put beats, TTS, or timeline into Comfy.
Do not text-to-video from the narration.

| Job | Model (add later) | Why |
| --- | --- | --- |
| Photoreal motion (street, people, physics) | **Wan 2.2 5B**, or 14B GGUF Q4 + Lightning | Best I2V look; 5B fits 8 GB; 14B is ~3 min per 5s at 480p |
| Faster / stylized / camera moves | **LTX-2.3 GGUF** | 8 GB default; start/mid/end still pinning |
| Maps, schemas, labeled plates | Ken Burns | I2V smears line and type |
| Draft of a 33-scene show | Ken Burns | I2V is too slow to preview the cut |
| SVD XT | Do not use | Warp, no prompt, obsolete |

How a show would cut once I2V exists:

- Preview Clips stay Ken Burns.
- Final Clips: I2V only on shots that need body or camera motion. Ken
  Burns on maps, titles, diagrams, and holds.
- Native takes are **4–5 seconds**. TTS is often longer; the assembler
  already freeze-pads the last clip of a scene. Do not ask the video
  model for a 20s take on 8 GB.
- Generate at **480p**, upscale if needed. Native 1080p I2V will OOM.
- Identity across shots still comes from the still (and a last-frame
  still), not from the video model remembering a face.
- Unload the T2I graph before loading I2V. 8 GB will not hold both.

These models make short shots, not acts. A Roman Empire “movie” is still
a sequence of locked stills, some of them animated.

## Show type: real political figures

Photoreal show with a named public figure (president, minister, other
recognizable person). This is an **identity-lock** problem. Canonical
write-up: `docs/real_political_figures.md`.

Shipping stills are prompt-only. Naming the person in the beat is
allowed; the face will still drift shot to shot. Political project
profiles fill unnamed clothes and rooms only — they do not lock a face.

| Cast | Identity tool | Still model |
| --- | --- | --- |
| Two or three recurring figures | FLUX Dev person LoRA (not wired; prove in Comfy lab first) | Dev final; Schnell / Z-Image draft only |
| Rotating / large cast | Reference photo kit + PuLID-FLUX or IP-Adapter (add later) | Dev final |
| Prompt-only name test | None | Dev; expect drift |

A LoRA in `ComfyUI/models/loras` does nothing until the Dev product
graph loads it. LoRAs do not transfer to Z-Image, HiDream, or FLUX.2
Klein. This machine has **16 GB VRAM**, so Dev + one LoRA or a
reference-identity graph is in range; still unload T2I before heavy I2V.

## Quick pick

| You are making | Still model | Style | Profile | Motion |
| --- | --- | --- | --- | --- |
| Photo documentary (modern) | Z-Image / Schnell draft; Dev or HiDream final | Cinematic | Matching contemporary profile | Ken Burns; later Wan I2V on action shots |
| Technical video, drafts, schemas | Qwen-Image (add) | Technical / diagram (add) | New technical profile; not `software_delevopment` | Ken Burns only |
| Painted editorial | HiDream | Cinematic Editorial Illustrator | Topic profile, contemporary or period | Ken Burns; later LTX on character shots |
| Graphic / comic / poster | Qwen-Image (add) | Graphic illustration | Topic profile | Ken Burns |
| Anime | SDXL Illustrious / NoobAI (add) | anime / ghibli | Topic profile | Ken Burns; later LTX |
| Historical reconstruction | Dev / HiDream | Cinematic | **New period profile** (none ships today) | Ken Burns; later Wan I2V on living action |
| Historical maps and inscriptions | Qwen-Image (add) | Technical / diagram | Period profile | Ken Burns |
| Real political figures (recurring) | Dev final; Schnell / Z-Image draft | Cinematic | Matching `*_political` profile | Ken Burns; later Wan I2V on the still. Identity: Dev LoRA (see `docs/real_political_figures.md`) |
| Real political figures (rotating cast) | Dev final | Cinematic | Matching `*_political` profile | Ken Burns. Identity: reference kit (add) |

If you add **one** new still model for both technical shows and graphic
illustration (and historical maps), add **Qwen-Image**. If the shows are
painted stills of real events, you do not need a new model: turn on
Cinematic Editorial Illustrator, enable HiDream, leave Schnell/Z-Image
off the final pick. If you add **one** video model later, add **Wan 2.2
I2V** for photoreal/history or **LTX-2.3** for speed/illustration. Keep
Ken Burns as the editorial default.

## Do not

- Use Schnell or Z-Image as finished diagrams, finished illustration, or
  finished period reconstruction.
- Use a contemporary project profile on an ancient show.
- Put “sharp photograph” first on an illustration prompt.
- Replace Ken Burns with SVD.
- Generate the timeline inside ComfyUI.
- Mix photo-Rome and painted-Rome in one cut without intending it.
- Expect I2V to hold a face, a legion, or a schema for a whole scene.
- Drop a person LoRA into ComfyUI and expect Pipeline/Lightbox to use it.
- Treat `usa_political` / `europe_political` as a likeness lock.
- Swallow Blender’s editor into this app, or start a second VID to host it.
- Keep FLUX Dev and Cycles loaded together on 16 GB.
