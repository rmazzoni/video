# Rome Softly — master prompt

Creative lock for **Roma, sottovoce** / **Rome, Softly**. The Italian
episode is recorded in Roberto's own voice and mounted on these
pictures. The English episode reuses the same pictures and is read
later by the cloned voice. Prompts are English. HiDream paints them.
Select visual style **Rome Softly** and, for Episode 1 Chapter 1, the
project profile **Rome Softly, Chapter 1**.

The render path leaves a prompt alone when it already contains the
style sentence below. It does not append “sharp photograph” or a
medium-full face clause. Do not use the words photograph, cinematic,
motivated light, or soft focus. Those phrases are either deleted or
pull the still back toward a photo.

Canvas is **1344×768**. That is the size the HiDream FP8 graph fits on
the 16 GB card. A keeper can be upscaled afterward. Do not ask the
graph for 4K.

HiDream drops negative prompts. The exclusions live in the style
sentence and in the chapter scene. There is no separate negative box.

## Assembly

One still, in this order. Scene first. Palette next. Style sentence
last, unchanged.

```
{shot}. {time of day}, {place}, {period}, {who and one action}. {palette sentence} {style sentence}
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
| Map | Flat painted land and water filling the frame, no labels, nobody. |
| Portrait | One figure, calm face, plain ground, no action but standing or sitting. |
| Interior | Medium view, one figure, dim room, one warm light. |

On a wide plate do not write king, man, woman, soldier, or worker.
Those words are people. Write “distant figures” instead. A named
person belongs on a medium, portrait, or interior plate.

## Style sentence

Unchanged on every still:

> Painterly storybook illustration in gouache and watercolour on textured paper, soft brush edges, light ink accents, low contrast, soft light, generous empty space, no text, no letters, no photorealism, no 3D render, no gore.

## Palette sentences

Use one. Put it immediately before the style sentence.

| Plate | Sentence |
| --- | --- |
| Rome and the Latin world | Pigments of parchment cream, Roman ochre, terracotta, olive green, and Tiber brown, dusk blue in the shadows. |
| United States, including the Florida study | Cooler pigments of slate blue, white marble, and dusk blue, with a little warm candlelight. |
| Night and closing | Night pigments of indigo and dusk blue, one warm lamp or fire. |
| Map | Pigments of parchment cream and dusk blue, soft hand-painted land and water, no labels. |

Pompeian red is a small accent inside a Rome scene sentence, not a
fifth palette. Muted gold waits for a later Hagia Sophia plate and is
not used on archaic Rome.

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

> Wide view, dawn, the yellow-brown Tiber at the ford by the island, Rome about 509 BC, reed beds, thatched huts on the Palatine, distant figures only, empty foreground. Pigments of parchment cream, Roman ochre, terracotta, olive green, and Tiber brown, dusk blue in the shadows. Painterly storybook illustration in gouache and watercolour on textured paper, soft brush edges, light ink accents, low contrast, soft light, generous empty space, no text, no letters, no photorealism, no 3D render, no gore.
