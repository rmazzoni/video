# Rome Softly — master prompt

Creative lock for **Roma, sottovoce** / **Rome, Softly**. The Italian
episode is recorded in Roberto's own voice and mounted on these
pictures. The English episode reuses the same pictures and is read
later by the cloned voice. Prompts are English. HiDream paints them.
Select visual style **Rome Softly** and, for Episode 1 Chapter 1, the
project profile **Rome Softly, Chapter 1**.

The render path leaves a prompt alone when it already contains a flat
style ending, or the older gouache sentence. It does not append “sharp
photograph” or a medium-full face clause. Do not use the words
photograph, motivated light, soft focus, gouache, or watercolour. The
ending itself says “cinematic 16:9”; do not add a second cinematic slogan.

Canvas is **1344×768**. That is the size the HiDream FP8 graph fits on
the 16 GB card. A keeper can be upscaled afterward. Do not ask the
graph for 4K.

HiDream drops negative prompts. The exclusions live in the style
sentence and in the chapter scene. There is no separate negative box.

## Assembly

One still, in this order. Scene first. One style ending last. The
palette is inside that ending.

```
{shot}. {time of day}, {place}, {period}, {who and one action}. {one style ending}
```

The scene is one or two English sentences from the script's image cue.
Name the century. Say the city is inhabited. Put a recurring person in
only with that person's card, copied verbatim.

Do not put two of the same shot scale in a row. The scales are: wide
landscape, medium scene, close object, map, portrait, interior.

| Shot | Framing, inside the scene sentence |
| --- | --- |
| Wide | Wide view, horizon in the upper third, empty foreground, distant figures only. |
| Medium | Medium view, one figure, plain wall or open ground, empty space beside them. |
| Close | Close view of one object, soft light, nothing else competing. |
| Map | Flat land and water filling the frame, no labels, nobody. |
| Portrait | One figure, calm face, plain ground, no action but standing or sitting. |
| Interior | Medium view, one figure, dim room, one warm light. |

On a wide plate do not write king, man, woman, soldier, or worker.
Those words are people. Write “distant figures” instead. A named
person belongs on a medium, portrait, or interior plate.

## Style ending

Style guide v2. Paste exactly one ending after the scene. The palette
is inside the ending. The same five sentences are in
`prompts/visual_styles.py`. If a hand prompt has no ending, the app
adds the City one.

Rural / domestic / dusk: countryside, farms, rivers, dawn and dusk, the opening title.

> Style: flat vector-style illustration, clean simplified shapes, simplified silhouettes, subtle paper grain texture, smooth gradient sky, limited muted palette of apricot, dusk blue, olive green and parchment, soft low-contrast lighting, calm atmosphere, generous negative space, historically accurate, cinematic 16:9 wide composition, no text, no letters, no watermark, no photorealism, no 3D render, no gore.

City / political / religious: Rome by day. This is the default.

> Style: flat vector-style illustration, clean simplified shapes, simplified silhouettes, subtle paper grain texture, smooth gradient sky, limited muted palette of tuff stone grey, roman ochre, terracotta and muted bronze, soft low-contrast lighting, calm atmosphere, generous negative space, historically accurate, cinematic 16:9 wide composition, no text, no letters, no watermark, no photorealism, no 3D render, no gore.

Military / conflict: armies, camps, sieges, and a camp at night. Soldiers stay distant.

> Style: flat vector-style illustration, clean simplified shapes, simplified silhouettes, subtle paper grain texture, smooth gradient sky, limited muted palette of iron grey, dark bronze, deep oxblood red and overcast slate sky, austere mood, soldiers kept at a distance, no close combat, soft low-contrast lighting, calm atmosphere, generous negative space, historically accurate, cinematic 16:9 wide composition, no text, no letters, no watermark, no photorealism, no 3D render, no gore.

Night: darkness or stillness is the mood, including the last images of an episode.

> Style: flat vector-style illustration, clean simplified shapes, simplified silhouettes, subtle paper grain texture, smooth gradient sky, limited muted palette of deep indigo and dusk blue with a single warm light source, soft low-contrast lighting, calm atmosphere, generous negative space, historically accurate, cinematic 16:9 wide composition, no text, no letters, no watermark, no photorealism, no 3D render, no gore.

Modern America / later parallels: any scene after antiquity, including the Florida study at night.

> Style: flat vector-style illustration, clean simplified shapes, simplified silhouettes, subtle paper grain texture, smooth gradient sky, limited muted palette of cool slate blue, white marble and parchment, soft low-contrast lighting, calm atmosphere, generous negative space, historically accurate, cinematic 16:9 wide composition, no text, no letters, no watermark, no photorealism, no 3D render, no gore.

Military beats Night. America beats every other palette. Inside Rome by day, City beats Rural.

## What the pictures refuse

No letters, captions, or watermarks. No stock photo, no film still, no
game render, no anime, no heavy cartoon outline. No blood, wounds, or
a weapon striking a body. Violence is distant smoke, a lowered head, or
spears stacked beside a fire. No New World plants: prickly pear, agave,
maize, tomato, citrus, eucalyptus.

Period mistakes belong in the chapter prompt, not in this sentence.
Episode 1 Chapter 1 is `docs/rome_softly_ep01_ch01.md`.

## Plates

A street, a river, a senate, a road, a desk, and a map that recur are
copies of the keeper PNG. Generate a still only for an event the
library does not have. Two candidates, one seed apart. Keep one. Mark
that prompt `manually_edited`. Do not run Extract Beats again on a
locked episode.

## Worked example

Wide dawn over the river, no named person:

> Wide view, dawn, the yellow-brown Tiber at the ford by the island, Rome about 509 BC, reed beds, thatched huts on the Palatine, distant figures only, empty foreground. Style: flat vector-style illustration, clean simplified shapes, simplified silhouettes, subtle paper grain texture, smooth gradient sky, limited muted palette of apricot, dusk blue, olive green and parchment, soft low-contrast lighting, calm atmosphere, generous negative space, historically accurate, cinematic 16:9 wide composition, no text, no letters, no watermark, no photorealism, no 3D render, no gore.
