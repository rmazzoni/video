"""Product still graphs vs lab/compatibility workflows.

ComfyUI is the GPU render backend. Qt owns beats, prompts, TTS, and assembly.
See docs/comfy_role.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Sequence, Tuple

Requirement = Tuple[str, str, str, str]


@dataclass(frozen=True)
class GraphSpec:
    filename: str
    display_name: str
    role: str
    params: FrozenSet[str]
    requirements: Tuple[Requirement, ...] = ()


_FLUX_STILL_PARAMS = frozenset({
    "prompt", "seed", "width", "height", "steps", "guidance", "filename_prefix",
})
_ZIMAGE_STILL_PARAMS = frozenset({
    "prompt", "seed", "width", "height", "steps", "sampler", "scheduler",
    "shift", "filename_prefix",
})
_HIDREAM_STILL_PARAMS = frozenset({
    "prompt", "seed", "width", "height", "steps", "guidance", "sampler",
    "scheduler", "shift", "filename_prefix",
})

_SCHNELL_REQUIREMENTS = (
    ("UNETLoader", "unet_name", "flux1-schnell.safetensors", "models/diffusion_models"),
    ("DualCLIPLoader", "clip_name1", "clip_l.safetensors", "models/text_encoders"),
    ("DualCLIPLoader", "clip_name2", "t5xxl_fp16.safetensors", "models/text_encoders"),
    ("VAELoader", "vae_name", "flux-ae.safetensors", "models/vae"),
)
_DEV_REQUIREMENTS = (
    ("UNETLoader", "unet_name", "flux1-dev.safetensors", "models/diffusion_models"),
    ("DualCLIPLoader", "clip_name1", "clip_l.safetensors", "models/text_encoders"),
    ("DualCLIPLoader", "clip_name2", "t5xxl_fp16.safetensors", "models/text_encoders"),
    ("VAELoader", "vae_name", "flux-ae.safetensors", "models/vae"),
)
_FLUX2_REQUIREMENTS = (
    ("UNETLoader", "unet_name", "flux2-klein-4b.safetensors", "models/diffusion_models"),
    ("CLIPLoader", "clip_name", "qwen_3_4b.safetensors", "models/text_encoders"),
    ("VAELoader", "vae_name", "flux2-vae.safetensors", "models/vae"),
)
_ZIMAGE_REQUIREMENTS = (
    ("UNETLoader", "unet_name", "z_image_turbo_bf16.safetensors", "models/diffusion_models"),
    ("CLIPLoader", "clip_name", "qwen_3_4b.safetensors", "models/text_encoders"),
    ("VAELoader", "vae_name", "ae.safetensors", "models/vae"),
)
_HIDREAM_REQUIREMENTS = (
    ("UNETLoader", "unet_name", "hidream_i1_dev_fp8.safetensors", "models/diffusion_models"),
    ("QuadrupleCLIPLoader", "clip_name1", "clip_l_hidream.safetensors", "models/text_encoders"),
    ("QuadrupleCLIPLoader", "clip_name2", "clip_g_hidream.safetensors", "models/text_encoders"),
    ("QuadrupleCLIPLoader", "clip_name3", "t5xxl_fp8_e4m3fn_scaled.safetensors", "models/text_encoders"),
    ("QuadrupleCLIPLoader", "clip_name4", "llama_3.1_8b_instruct_fp8_scaled.safetensors", "models/text_encoders"),
    ("VAELoader", "vae_name", "ae.safetensors", "models/vae"),
)

PRODUCT_STILLS: Dict[str, GraphSpec] = {
    "flux-schnell": GraphSpec(
        filename="flux1_schnell_image.json",
        display_name="FLUX Schnell — product still",
        role="product",
        params=_FLUX_STILL_PARAMS,
        requirements=_SCHNELL_REQUIREMENTS,
    ),
    "zimage-turbo": GraphSpec(
        filename="zimage_turbo_image.json",
        display_name="Z-Image Turbo — product still",
        role="product",
        params=_ZIMAGE_STILL_PARAMS,
        requirements=_ZIMAGE_REQUIREMENTS,
    ),
    "flux-dev": GraphSpec(
        filename="flux1_dev_image.json",
        display_name="FLUX Dev — product still",
        role="product",
        params=_FLUX_STILL_PARAMS,
        requirements=_DEV_REQUIREMENTS,
    ),
    "hidream-dev": GraphSpec(
        filename="hidream_i1_dev_image.json",
        display_name="HiDream-I1 Dev — product still",
        role="product",
        params=_HIDREAM_STILL_PARAMS,
        requirements=_HIDREAM_REQUIREMENTS,
    ),
    "flux2": GraphSpec(
        filename="flux2_image.json",
        display_name="FLUX.2 Klein — product still",
        role="product",
        params=_FLUX_STILL_PARAMS,
        requirements=_FLUX2_REQUIREMENTS,
    ),
}

OTHER_WORKFLOWS: Dict[str, GraphSpec] = {
    "sd3_image.json": GraphSpec(
        filename="sd3_image.json",
        display_name="Legacy SDXL still (unused)",
        role="lab",
        params=frozenset({"prompt", "seed"}),
    ),
    "flux2_video.json": GraphSpec(
        filename="flux2_video.json",
        display_name="SVD XT img2vid (not FLUX.2 video; unused by pipeline)",
        role="lab",
        params=frozenset({"image", "seed"}),
    ),
    "vid_full_pipeline.json": GraphSpec(
        filename="vid_full_pipeline.json",
        display_name="VID stage loop — frozen compatibility, not the product path",
        role="compatibility",
        params=frozenset(),
    ),
}

WORKFLOWS = {key: spec.filename for key, spec in PRODUCT_STILLS.items()}
PRODUCT_BY_FILENAME = {spec.filename: spec for spec in PRODUCT_STILLS.values()}


def spec_for_model(model_type: str) -> GraphSpec:
    try:
        return PRODUCT_STILLS[model_type]
    except KeyError as exc:
        raise ValueError(f"Unsupported ComfyUI image model: {model_type}") from exc


def spec_for_filename(filename: str) -> Optional[GraphSpec]:
    if filename in PRODUCT_BY_FILENAME:
        return PRODUCT_BY_FILENAME[filename]
    return OTHER_WORKFLOWS.get(filename)


def lab_workflow_choices() -> List[Tuple[str, str]]:
    """Filename + label for the Comfy lab dropdown (product first)."""
    choices = [(spec.filename, spec.display_name) for spec in PRODUCT_STILLS.values()]
    for spec in OTHER_WORKFLOWS.values():
        choices.append((spec.filename, spec.display_name))
    return choices


def placeholders_in(value: Any) -> FrozenSet[str]:
    found: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, str) and node.startswith("@") and len(node) > 1:
            key = node[1:]
            if key.isidentifier():
                found.add(key)
            return
        if isinstance(node, dict):
            for child in node.values():
                walk(child)
            return
        if isinstance(node, list):
            for child in node:
                walk(child)

    walk(value)
    return frozenset(found)


def params_for_spec(spec: GraphSpec, available: Dict[str, Any]) -> Dict[str, Any]:
    return {key: available[key] for key in spec.params if key in available}


def missing_placeholders(graph: Any, params: Dict[str, Any]) -> FrozenSet[str]:
    return frozenset(key for key in placeholders_in(graph) if key not in params)


def leftover_placeholders(graph: Any) -> FrozenSet[str]:
    return placeholders_in(graph)
