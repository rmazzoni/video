# ComfyUI's role in VID

Decision: **ComfyUI is the GPU render backend for still images (and later
optional img2vid). The Qt app remains the editorial product.**

Do not migrate beats, prompt lock, TTS, Ken Burns, or timeline assembly into
Comfy graphs. Those are VID-specific and UI-curated. ComfyUI loads weights,
runs the model graph, and returns a PNG.

## How the models talk to ComfyUI today

Every still goes through the same Python path:

```
Pipeline tab / lightbox / prompt-image popup
  → PipelineWorker._make_image_gen()
  → structure_prompt_for_model()          # VID-owned prompt lock
  → ComfyImageGenerator.generate_image()
  → ComfyClient.execute_workflow()        # substitute @params, POST /prompt
  → wait /history, GET /view
  → write scene_NNN_MODEL_bBB_vV.png
```

`launch_with_comfy.py` starts the ComfyUI server first. Image generation
fails if that process is down. Diffusers is no longer used for Schnell,
Z-Image, Dev, HiDream, or FLUX.2 stills. SVD clips still run in-process
via Diffusers (`video/video_generator.py`).

### Per-model graphs

| App model | Workflow | Encoder | What the graph actually honors | What Python sends that the graph ignores |
| --- | --- | --- | --- | --- |
| FLUX Schnell | `flux1_schnell_image.json` | CLIP-L + T5 | `@prompt` `@seed` `@width` `@height` `@steps` `@guidance` (FluxGuidance). Sampler **hardcoded** euler/simple. CFG 1. Negative zeroed. | `sampler`, `scheduler`, `shift` |
| Z-Image Turbo | `zimage_turbo_image.json` | Qwen 3 4B (lumina2) | `@prompt` `@seed` `@width` `@height` `@steps` `@sampler` `@scheduler` `@shift`. CFG **hardcoded 1**. Negative zeroed. | `guidance` (`zimage_guidance` is a Diffusers leftover) |
| FLUX Dev | `flux1_dev_image.json` | CLIP-L + T5 | Same as Schnell, FluxGuidance default 3.5. Sampler hardcoded euler/simple. | `sampler`, `scheduler`, `shift` |
| FLUX.2 Klein | `flux2_image.json` | Qwen 3 4B (flux2) | Same as Schnell/Dev, FluxGuidance default 1.0. | `sampler`, `scheduler`, `shift` |
| HiDream-I1 Dev | `hidream_i1_dev_image.json` | four CLIP/T5/Llama | `@prompt` `@seed` `@width` `@height` `@steps` `@guidance` (KSampler cfg) `@sampler` `@scheduler` `@shift`. Negative zeroed. | none of the usual keys |

`ComfyImageGenerator` always posts the full param bag. Placeholders that are
absent from a graph are left as the string `@foo` only if the key is missing
from params; extra params are simply unused. That is why Schnell/Dev/FLUX.2
stay on euler even if the Settings sampler dropdown says otherwise, and why
Z-Image stays CFG 1 even if `zimage_guidance` is non-zero.

Prompt text is VID-owned. ComfyUI never sees the locked beat, the project
profile, or Qwen. It only sees the already-shaped positive string.

## Three ways to run ComfyUI (only one is the product)

1. **Product path (keep).** Pipeline / Prompts / Lightbox → `PipelineWorker` →
   native T2I JSON. This is how users generate the video stills.
2. **Lab path (keep, secondary).** The ComfyUI tab loads any `workflows/*.json`,
   injects the tab's prompt/seed/size widgets, and can embed the Comfy web UI.
   Useful for debugging a graph. Not the editorial workflow. `NodeEditorStub`
   is still a placeholder.
3. **Compatibility loop (do not grow).** `vid_full_pipeline.json` plus
   `comfy_nodes/vid_pipeline` wrap each VID stage as a Comfy node that calls
   `PipelineWorker`, which for images calls ComfyUI again. Comfy → Python →
   Comfy. The settings node also omits Z-Image and HiDream fields. Freeze this
   path; do not add stages to it.

Leftover graphs that are not on the product path:

- `sd3_image.json` — SDXL, named for old compatibility, unused by the pipeline
- `flux2_video.json` — **SVD XT**, not FLUX.2 video. Unused; clips still use
  Diffusers Ken Burns / SVD in `PipelineWorker`

## Future role

**Own:** model graphs, checkpoints, VRAM, samplers, and returning stills
(and later img2vid frames) over the HTTP API.

**Do not own:** scene splitting, visual beats, prompt generation, grounding,
identity/kit/prop lock, project profiles, TTS, Ken Burns editorial motion,
timeline assembly, loudness, or the Prompts/Lightbox UI.

### Implemented contract

- Product still graphs and their `@params` live in `comfy_bridge/graphs.py`.
  `ComfyImageGenerator` sends only those keys. Leftover `@placeholders` fail
  closed instead of posting `@sampler` into ComfyUI.
- Schnell / Dev / FLUX.2 keep euler/simple hardcoded. HiDream and Z-Image
  honor sampler/shift from Settings.
- The Qt tab is **Comfy lab**. It lists product graphs first and labels
  leftover JSON (SVD XT, legacy SDXL, frozen VID stage loop).
- `comfy_nodes/vid_pipeline` is frozen compatibility. Do not add models.

If SVD clips move off Diffusers later, reuse `flux2_video.json` as img2vid
the same way stills work. Do not invent a FLUX.2 video model that is not
installed.

### Not in scope unless the product changes

- Replacing Qt with Comfy as the user-facing app
- An in-app node graph editor (`NodeEditorStub`)
- Expanding `vid_full_pipeline.json` into the real pipeline
- Putting Qwen/Ollama inside Comfy
