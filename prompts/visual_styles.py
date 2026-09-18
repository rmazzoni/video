"""Global visual styles with model-specific prompt-writing guidance."""

from typing import Dict


DEFAULT_VISUAL_STYLE = "cinematic"

VISUAL_STYLES: Dict[str, Dict[str, object]] = {
    "cinematic": {
        "display_name": "Cinematic",
        "fallback_preset": "cinematic",
        "prompt_anchors": {
            "schnell": "Sharp photograph, clear air, simple staging.",
            "zimage": "Sharp photograph, clear air, tactile materials, directional daylight, fine detail.",
            "dev": "Sharp photograph, clear air, directional daylight, fine detail.",
            "hidream": "Clear photograph, distinct faces, natural materials, directional room light.",
            "flux2": "Precise photographic scene, realistic surfaces, directional light.",
        },
        "models": {
            "schnell": (
                "Use a short concrete photograph: one subject, one action, one place. "
                "Keep the air clear and the focus sharp. Do not add haze, fog, bloom, "
                "bokeh, or soft focus. If a person is named, a simple medium shot facing "
                "the camera. Do not invent a person for a vehicle, drone, or landscape."
            ),
            "zimage": (
                "Use concise photographic language with a strong readable composition, "
                "specific natural materials, directional daylight, and clear spatial "
                "relationships. Keep the air clear and the focus sharp. Do not add haze, "
                "fog, bloom, bokeh, volumetric light, or soft focus unless the beat names "
                "weather. If a person is named, use a medium or medium-full shot with "
                "a sharply detailed face; do not hide the face by receding from camera. "
                "Preserve literal subject identity and action rather than substituting "
                "an attractive generic scene."
            ),
            "dev": (
                "Use concrete photographic language with one decisive moment, directional "
                "daylight, and clear air. Do not add haze, fog, bloom, bokeh, or soft focus "
                "unless the beat names weather. If a person is named, a medium-full shot with "
                "a readable face; do not recede from camera. Do not invent a person for a "
                "vehicle, drone, or landscape. A military convoy is armored military trucks."
            ),
            "hidream": (
                "Use clear, spatially staged photography with natural anatomy, readable faces, "
                "tactile materials, and distinct foreground, middle, and background planes. "
                "HiDream muddies when prompts stack volumetric light, haze, bloom, or repeated "
                "cinematic adjectives — prefer one lighting direction, clear air, and concrete "
                "furniture or terrain. Describe the room and people; do not sandwich the beat "
                "between style slogans."
            ),
            "flux2": (
                "Use precise cinematic photography with purposeful composition, spatial "
                "depth, material detail, and motivated light. Translate the beat into a "
                "specific captured moment with explicit left-right and near-far placement. "
                "Avoid polished stock-photo staging, portrait formulas, and keyword piles."
            ),
        },
    },
    "cinematic_editorial_illustrator": {
        "display_name": "Cinematic Editorial Illustrator",
        "fallback_preset": "illustration",
        "prompt_anchors": {
            "schnell": (
                "Cinematic editorial illustration, visibly hand-painted, flat designed shapes, "
                "simplified forms, limited color palette; not a photograph."
            ),
            "zimage": (
                "Cinematic editorial illustration, visibly painted graphic shapes, controlled "
                "edges, tactile pigment texture, limited authored palette; not a photograph."
            ),
            "dev": (
                "Cinematic editorial illustration, visibly painterly layered shapes, expressive "
                "brush texture, designed color relationships; not photorealistic."
            ),
            "hidream": (
                "Cinematic editorial illustration, richly painted dimensional forms, expressive "
                "surface texture, designed color relationships; clearly non-photographic."
            ),
            "flux2": (
                "Cinematic editorial illustration, clearly painted surface, controlled graphic "
                "shapes and edges, authored color palette; unmistakably non-photographic."
            ),
        },
        "models": {
            "schnell": (
                "Render as a cinematic editorial illustration, not a photograph: bold readable "
                "shapes, simplified natural anatomy, controlled edges, selective painted texture, "
                "a limited cohesive palette, and clear value grouping. Keep the composition direct "
                "and uncluttered for Schnell, with one dominant action and a graphic silhouette. "
                "Avoid plastic 3D rendering, anime conventions, heavy outlines, and tiny decorative detail."
            ),
            "zimage": (
                "Render as a cinematic editorial illustration with bold designed shapes, natural "
                "proportions, selective painterly texture, clear value grouping, and an authored "
                "limited palette. Keep the stated action and spatial relationships literal while "
                "making the result unmistakably illustrated rather than photographic or 3D."
            ),
            "dev": (
                "Render as a refined cinematic editorial illustration: natural proportions, "
                "expressive restrained faces, layered painted shapes, tactile brush texture, "
                "selective fine detail, atmospheric depth, and a cohesive authored color palette. "
                "Use editorial composition and visual hierarchy to interpret the narration rather "
                "than imitate a photograph. Avoid glossy 3D surfaces, photoreal skin, anime styling, "
                "and uniform comic-book outlines."
            ),
            "hidream": (
                "Render as a richly authored cinematic editorial illustration with natural anatomy, "
                "layered painted forms, nuanced expressions, tactile surface variation, atmospheric "
                "depth, and intentional color relationships. Keep the narrated action literal and "
                "readable while avoiding photographic skin, synthetic 3D polish, and anime styling."
            ),
            "flux2": (
                "Render as a sophisticated cinematic editorial illustration with designed shapes, "
                "natural anatomy, nuanced expressions, painterly surface variation, controlled edge "
                "hierarchy, atmospheric perspective, and intentional color relationships. Combine "
                "the clarity of editorial art with cinematic scale and lighting while remaining "
                "visibly illustrated. Avoid photographic skin texture, synthetic 3D polish, anime "
                "features, heavy contour lines, and indiscriminate micro-detail."
            ),
        },
    },
}


def visual_style_choices() -> Dict[str, str]:
    return {key: str(value["display_name"]) for key, value in VISUAL_STYLES.items()}


def visual_style_instruction(style_key: str, model_key: str) -> str:
    style = VISUAL_STYLES.get(style_key, VISUAL_STYLES[DEFAULT_VISUAL_STYLE])
    models = style["models"]
    if not isinstance(models, dict):
        return ""
    return str(models.get(model_key, ""))


def visual_style_fallback_preset(style_key: str) -> str:
    style = VISUAL_STYLES.get(style_key, VISUAL_STYLES[DEFAULT_VISUAL_STYLE])
    return str(style.get("fallback_preset", "cinematic"))


def visual_style_prompt_anchor(style_key: str, model_key: str) -> str:
    style = VISUAL_STYLES.get(style_key, VISUAL_STYLES[DEFAULT_VISUAL_STYLE])
    anchors = style.get("prompt_anchors", {})
    if not isinstance(anchors, dict):
        return ""
    return str(anchors.get(model_key, ""))
