"""Global visual styles with model-specific prompt-writing guidance."""

from typing import Dict


DEFAULT_VISUAL_STYLE = "cinematic"

VISUAL_STYLES: Dict[str, Dict[str, object]] = {
    "cinematic": {
        "display_name": "Cinematic",
        "fallback_preset": "cinematic",
        "models": {
            "schnell": (
                "Use a cinematic photographic language with concrete, economical detail. "
                "Let the scene determine framing, perspective, palette, weather, atmosphere, "
                "and lighting. Favor one readable action and a strong silhouette or focal point, "
                "but do not reduce every scene to a centered portrait. Use dramatic light, deep "
                "space, environmental texture, and unusual angles when supported by the narration."
            ),
            "dev": (
                "Use expressive cinematic photography with deliberate visual hierarchy. Choose "
                "lens perspective, camera distance, blocking, atmosphere, color contrast, and "
                "directional light from the dramatic needs of this scene. Preserve environmental "
                "detail and visual tension; avoid a generic commercial portrait or uniformly soft, "
                "flat illumination."
            ),
            "flux2": (
                "Use sophisticated cinematic photography with purposeful composition, spatial "
                "depth, material detail, and motivated light. Translate the narration into a "
                "specific captured moment, allowing wide tableaux, dynamic perspective, restrained "
                "visual metaphor, or intimate observation as appropriate. Avoid polished stock-photo "
                "staging and repeated portrait formulas."
            ),
        },
    },
    "cinematic_editorial_illustrator": {
        "display_name": "Cinematic Editorial Illustrator",
        "fallback_preset": "illustration",
        "models": {
            "schnell": (
                "Render as a cinematic editorial illustration, not a photograph: bold readable "
                "shapes, simplified natural anatomy, controlled edges, selective painted texture, "
                "a limited cohesive palette, and clear value grouping. Keep the composition direct "
                "and uncluttered for Schnell, with one dominant action and a graphic silhouette. "
                "Avoid plastic 3D rendering, anime conventions, heavy outlines, and tiny decorative detail."
            ),
            "dev": (
                "Render as a refined cinematic editorial illustration: natural proportions, "
                "expressive restrained faces, layered painted shapes, tactile brush texture, "
                "selective fine detail, atmospheric depth, and a cohesive authored color palette. "
                "Use editorial composition and visual hierarchy to interpret the narration rather "
                "than imitate a photograph. Avoid glossy 3D surfaces, photoreal skin, anime styling, "
                "and uniform comic-book outlines."
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
