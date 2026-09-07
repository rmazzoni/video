# VID Repository Instructions

## Project Context

- This is a Windows-first Python/PyQt6 desktop application for generating narrated videos.
- The application source root is `F:\VID\src`.
- Use the existing interpreter at `F:\VID\venv\Scripts\python.exe`. Do not create another virtual environment.
- ComfyUI is installed at `F:\VID\ComfyUI` and shares the same Python environment.
- ComfyUI connection and installation settings are defined in `config/comfy.yaml`.
- Launch the integrated application with `python launch_with_comfy.py` from the source root.

## Architecture

- Keep UI construction and user interaction in `ui/main_window.py` and focused widgets under `ui/widgets/`.
- Keep long-running pipeline work out of the Qt main thread. Use the existing controller/worker/QThread signal pattern.
- Keep stage orchestration in `ui/pipeline_controller.py`.
- Keep ComfyUI transport and workflow loading in `comfy_bridge/`; do not duplicate REST or WebSocket code in UI modules.
- Keep image, narration, prompt, and video behavior in their existing domain packages.
- Use `utilis/config_loader.py` and existing YAML settings instead of introducing parallel configuration systems.

## ComfyUI Contracts

- Treat files under `workflows/` as executable ComfyUI API-format graphs unless their structure explicitly contains UI-format `nodes` and `links`.
- Preserve placeholder parameters such as `@prompt`, `@seed`, `@width`, `@height`, `@steps`, and `@guidance`.
- API submissions must include only dictionary-valued node entries. Metadata keys such as `_meta_note` are not nodes and can break ComfyUI validation.
- FLUX.1 uses `DualCLIPLoader` with `clip_l`, `t5xxl_fp16`, and type `flux`.
- FLUX.2 Klein uses `CLIPLoader` with `qwen_3_4b` and type `flux2`.
- Z-Image and HiDream have required-model checks in `images/comfy_image_generator.py`; preserve actionable missing-file errors.
- The embedded ComfyUI canvas is frontend-version-sensitive. Verify workflow loading against the running local frontend after changing its JavaScript integration.
- Do not update ComfyUI automatically during normal generation or while its queue is active. Updates must use a clean checkout, fast-forward only, and require a server restart before verification of new code.

## Pipeline And Output Contracts

- Preserve the numbered stage names and stage keys exposed by `PipelineController` unless migration is explicitly requested.
- Model keys are `schnell`, `zimage`, `dev`, `hidream`, and `flux2`; model-type mappings live in the existing prompt/image services.
- Generated image names follow `scene_NNN_MODEL_bBB_vV.png`. Keep parsing, sorting, selection, invalidation, and viewer logic synchronized when changing this format.
- Preserve manually edited prompts during normal regeneration. Explicit per-model regeneration may replace them only after the existing confirmation flow.
- Keep `output/model_prompts.yaml` as the model-specific prompt source and `output/prompts.yaml` as the Schnell compatibility view.
- Lightbox selections are stored in `output/lightbox_selections.yaml`; removing or regenerating images must remove stale selections.
- Final clip duration is derived from dubbed scene audio divided by selected image count. Changes to selection or timing logic must preserve final audio/video synchronization.
- Never delete generated project output broadly. Restrict invalidation to the affected scene, beat, model, and variants.

## Implementation Practices

- Follow existing naming, type hints, Qt signals, and error-reporting patterns.
- Prefer small changes at the behavior-owning layer over UI-only workarounds.
- Keep filesystem paths portable in code. Read configured paths rather than adding new hard-coded machine paths.
- Do not silently fall back to another model's prompt when a model-specific prompt is required. Generate it or report a clear error.
- Preserve user changes in a dirty worktree and do not alter Git staging unless explicitly requested.
- Avoid unrelated refactors, broad formatting changes, generated files, and new dependencies unless required.

## Validation

- After Python edits, run the narrowest relevant test or behavior check.
- At minimum, compile touched Python modules with `F:\VID\venv\Scripts\python.exe -m py_compile <files>` and inspect editor diagnostics.
- Run `git diff --check` after edits; also check `git diff --cached --check` when staged changes already exist.
- For ComfyUI workflow changes, validate JSON parsing, required node classes via `/object_info`, and one representative generation when practical.
- For embedded canvas changes, verify both API-format and UI-format workflow loading against `http://127.0.0.1:8188`.
- For UI changes, verify that long operations remain asynchronous and controls cannot start conflicting workers.
- Do not claim full end-to-end validation when ComfyUI, model files, or a representative project is unavailable.
