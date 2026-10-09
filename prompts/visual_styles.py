"""Global visual styles with model-specific prompt-writing guidance."""

from typing import Dict


DEFAULT_VISUAL_STYLE = "cinematic"

# Style guide v2 (9 Oct 2026): flat illustration, one mood palette inside the ending.
# The older gouache sentence is still recognised so a stored prompt is not rewritten.
ROME_SOFTLY_MARKER = "flat vector-style illustration"
ROME_SOFTLY_LEGACY_MARKER = "painterly storybook illustration"
_ROME_SOFTLY_PALETTE_TEXT = {
    "rural": "apricot, dusk blue, olive green and parchment",
    "city": "tuff stone grey, roman ochre, terracotta and muted bronze",
    "military": (
        "iron grey, dark bronze, deep oxblood red and overcast slate sky, "
        "austere mood, soldiers kept at a distance, no close combat"
    ),
    "night": "deep indigo and dusk blue with a single warm light source",
    "america": "cool slate blue, white marble and parchment",
}


def rome_softly_style_sentence(palette: str = "city") -> str:
    """One ready-made style ending. City is the default inside Rome by day."""
    phrase = _ROME_SOFTLY_PALETTE_TEXT.get(str(palette or "").strip().lower())
    if not phrase:
        phrase = _ROME_SOFTLY_PALETTE_TEXT["city"]
    return (
        "Style: flat vector-style illustration, clean simplified shapes, simplified silhouettes, "
        "subtle paper grain texture, smooth gradient sky, limited muted palette of "
        f"{phrase}, soft low-contrast lighting, calm atmosphere, generous negative space, "
        "historically accurate, cinematic 16:9 wide composition, no text, no letters, "
        "no watermark, no photorealism, no 3D render, no gore."
    )


ROME_SOFTLY_STYLE_SENTENCE = rome_softly_style_sentence("city")


def prompt_is_rome_softly(prompt_text: str) -> bool:
    """True when the prompt already carries a Rome Softly style ending."""
    lower = str(prompt_text or "").lower()
    return ROME_SOFTLY_MARKER in lower or ROME_SOFTLY_LEGACY_MARKER in lower


def ensure_rome_softly_style(prompt_text: str) -> str:
    """Keep a prompt that already chose a palette. Otherwise end with City."""
    text = " ".join(str(prompt_text or "").split())
    if not text:
        return ""
    if prompt_is_rome_softly(text):
        return text
    if text[-1] not in ".!?":
        text += "."
    return text + " " + ROME_SOFTLY_STYLE_SENTENCE


def _rome_softly_writer() -> str:
    choices = "\n".join(
        f"- {label}: {rome_softly_style_sentence(key)}"
        for label, key in (
            ("Rural, domestic, dawn, or dusk", "rural"),
            ("City, political, or religious. Default for Rome in daylight", "city"),
            ("Military or conflict, including an army camp at night", "military"),
            ("Night, when darkness or stillness is the mood", "night"),
            ("Modern America or any later age, including the Florida study", "america"),
        )
    )
    return (
        "Write one English flat illustration of the locked beat only. "
        "Scene first: shot and framing, subject and action, place and date, light, then mood. "
        "Use clean flat colour and simplified silhouettes. No black contour lines, no brush strokes, "
        "no watercolour blooms, no gouache. Where smoke appears, write "
        "\"thin straight wisps of smoke rising vertically, no stylized puffs\". "
        "Soldiers stay distant: no gore, no close combat. No text in the image. "
        "End with exactly one style sentence below, copied unchanged. "
        "Do not add a second palette. Do not write photograph, motivated light, or soft focus.\n"
        + choices
    )

VISUAL_STYLES: Dict[str, Dict[str, object]] = {
    "cinematic": {
        "display_name": "Cinematic",
        "fallback_preset": "cinematic",
        "prompt_anchors": {
            "schnell": "Sharp photograph, clear air, simple staging.",
            "zimage": "Sharp photograph, clear air, tactile materials, directional daylight, fine detail.",
            "dev": "Sharp photograph, clear air, directional daylight, fine detail.",
            "hidream": "Sharp photograph, clear air, one lighting direction, fine detail.",
            "flux2": "Sharp photograph, clear air, directional daylight, fine detail.",
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
                "Use concrete photographic language with one decisive moment, one lighting "
                "direction, and clear air. Do not add haze, fog, bloom, bokeh, volumetric light, "
                "or soft focus unless the beat names weather. If a person is named, a medium-full "
                "shot with a readable face; do not recede from camera. Do not invent a person for "
                "a vehicle, drone, or landscape. A military convoy is armored military trucks. "
                "A wall safe stays in the wall. Do not repeat color adjectives."
            ),
            "flux2": (
                "Use concrete photographic language with one decisive moment, directional "
                "daylight, and clear air. Do not add haze, fog, bloom, bokeh, or soft focus "
                "unless the beat names weather. If a person is named, a medium-full shot with "
                "a readable face; do not recede from camera. Do not invent a person for a "
                "vehicle, drone, or landscape. A military convoy is armored military trucks."
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
    "rome_softly": {
        "display_name": "Rome Softly",
        "fallback_preset": "illustration",
        "prompt_anchors": {
            "schnell": ROME_SOFTLY_STYLE_SENTENCE,
            "zimage": ROME_SOFTLY_STYLE_SENTENCE,
            "dev": ROME_SOFTLY_STYLE_SENTENCE,
            "hidream": ROME_SOFTLY_STYLE_SENTENCE,
            "flux2": ROME_SOFTLY_STYLE_SENTENCE,
        },
        "models": {
            "schnell": _rome_softly_writer(),
            "zimage": _rome_softly_writer(),
            "dev": _rome_softly_writer(),
            "hidream": _rome_softly_writer(),
            "flux2": _rome_softly_writer(),
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
