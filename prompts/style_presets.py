"""
Centralized style preset definitions for the prompt builder.
Each preset describes the visual look, mood, and rendering style.
This is the single source of truth — imported by both PromptBuilder and the
Settings UI dropdown, so the two never drift out of sync.
"""

STYLE_PRESETS = {
    "cinematic": (
        "cinematic lighting, volumetric light, high detail, 35mm lens, "
        "soft shadows, realistic textures, depth of field, dramatic atmosphere"
    ),
    "realistic": (
        "ultra realistic, natural lighting, detailed textures, photographic quality"
    ),
    "anime": (
        "anime style, vibrant colors, clean line art, expressive characters"
    ),
    "watercolor": (
        "soft watercolor painting, gentle brush strokes, pastel tones"
    ),
    "illustration": (
        "digital illustration, clean shading, stylized shapes, bold colors"
    ),
    "noir": (
        "black and white photography, dramatic chiaroscuro, deep shadows, "
        "1940s detective atmosphere, high contrast, rain-slicked streets"
    ),
    "baroque": (
        "baroque painting style, ornate composition, dramatic lighting, "
        "rich jewel tones, deep shadow, oil painting texture, Rembrandt lighting"
    ),
    "concept art": (
        "professional concept art, detailed environment design, "
        "matte painting, epic scale, studio quality, bold composition"
    ),
    "oil painting": (
        "oil painting, thick impasto brushwork, rich saturated colour, "
        "canvas texture, classical technique, museum quality"
    ),
    "impressionist": (
        "impressionist painting, loose expressive brushwork, dappled light, "
        "soft edges, vibrant colour palette, plein air atmosphere"
    ),
    "ghibli": (
        "Studio Ghibli style, soft anime aesthetic, lush detailed backgrounds, "
        "warm natural lighting, gentle colour palette, hand-drawn feel"
    ),
    "golden hour": (
        "golden hour lighting, warm orange and amber tones, long soft shadows, "
        "lens flare, photorealistic, rich depth of field"
    ),
    "ethereal": (
        "ethereal dreamlike atmosphere, soft glowing light, pastel mist, "
        "otherworldly beauty, delicate details, surreal fantasy"
    ),
    "fantasy": (
        "epic fantasy art, magical lighting, ethereal atmosphere, ornate details, "
        "mythical elements, painterly textures"
    ),
    "sci-fi": (
        "futuristic sci-fi aesthetic, neon lighting, holographic effects, "
        "high-tech environments, sleek metallic surfaces"
    ),
    "surreal": (
        "surreal dreamlike imagery, impossible geometry, symbolic elements, "
        "ethereal lighting, abstract composition"
    ),
}
