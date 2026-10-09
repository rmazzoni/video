# Sleep history stills

Production sheet for **Roma, sottovoce** / **Rome, Softly**. The
narration runs from the founding of the Republic toward Byzantium, with
quiet parallels to the United States. The Italian episode is recorded
in Roberto's voice. The English episode reuses the same pictures and is
dubbed later with the cloned voice. Videos are about two to two and a
half hours, meant to be listened to while falling asleep.

The words to paste are in `docs/rome_softly_master_prompt.md`. Episode 1
Chapter 1 is in `docs/rome_softly_ep01_ch01.md`. This file is how those
prompts sit in the app: one painted look, shared plates, and the
settings that keep a later episode from drifting.

How the app fits together is in `docs/how_it_works.md`. Which model to
use for a kind of show is in `docs/show_types_and_models.md`.

## Series lock

Set these on every episode project before generating. If a setting
differs, the episode is not in series.

| Setting | Locked value |
| --- | --- |
| Visual style | Rome Softly |
| Final still model | HiDream only |
| Preview models | Off for this series. Schnell and Z-Image slip back to photographs |
| Project profile | The chapter profile when one exists. Episode 1 Chapter 1 uses `rome_softly_ch01`. Contemporary profiles will dress a silent beat in suits |
| Canvas | 1344×768. Upscale a keeper afterward. Do not render 4K in HiDream |
| Seeds per beat | Two candidates on a new plate. Keep one. Do not keep both |
| Clip engine | Ken Burns, slow pan and zoom. No SVD, no image-to-video |
| Hold | About 45–60 seconds. The last ten minutes may hold a night plate longer |
| Voice | Italian master: the recorded voice, mounted after the stills. English: the Qwen clone, same pictures, later |

FLUX Dev is the standby if a night of HiDream is too slow. Do not mix
Dev plates and HiDream plates in one episode or across the library.
Pick one model and keep it.

Ken Burns auto is a slow zoom and a single pan. Use static on a plate
that feels restless. Leave SVD and image-to-video off. Extra motion
fights the format.

The Lightbox badge assumes a new still every 12 seconds
(`OPTIMAL_SHOT_SECONDS` in `video/ken_burns_generator.py`). On a
three-hour narration that is about 900 images. Clip length is the
scene’s audio divided by how many stills you select, so fewer stills
mean longer shots. An orange “under” count is the intended state for
this channel.

Write scenes of about three to six minutes, with four to eight beats
each. Plan on **80–120 unique stills** for the first episode, many of
them shown again every fifteen or twenty minutes. Later episodes add
only the events the library does not already contain.

## What stays the same, what may change

Uniformity comes from repeating the same plates and the same sentences,
not from hoping a new prompt lands near the last one.

| Locked across episodes | May change, after this file is updated |
| --- | --- |
| Style sentence, palettes, shot grammar | A new century’s costume row and place row |
| HiDream, Rome Softly, 1344×768 | The event a scene is about |
| Costume and place rows already in the tables below | A new canonical plate, accepted only beside its shot-type reference |
| Ken Burns and the 45–60 second hold | |
| Recurring institutions: copy the PNG, do not regenerate it | |

A newly generated “Forum” will not match the old Forum. Recurring
streets, senates, roads, harbors, desks, and maps are **copies** from
the plate library. New art is for an event the library does not have.

Change the style lock only by editing this document, regenerating the
proof set below, and replacing library plates that no longer match.
An episode already in progress keeps the library as it stood when that
episode started.

## Style sentence

Put this sentence, unchanged, at the end of every beat. It is the same
sentence as `ROME_SOFTLY_STYLE_SENTENCE` in `prompts/visual_styles.py`.

> Painterly storybook illustration in gouache and watercolour on textured paper, soft brush edges, light ink accents, low contrast, soft light, generous empty space, no text, no letters, no photorealism, no 3D render, no gore.

A prompt that contains “painterly storybook illustration” is rendered
as written. The app does not add “sharp photograph” or a medium-full
face line. Do not write photograph, cinematic, motivated light, or
soft focus. Marker words that pull the other way: ultra detailed,
epic sky, god rays, anime, crowds filling the frame, readable inscriptions.

## Palettes

Append one palette sentence, unchanged, before the style sentence.
The full set is in `docs/rome_softly_master_prompt.md`.

| World | Palette sentence |
| --- | --- |
| Rome and Constantinople | Pigments of parchment cream, Roman ochre, terracotta, olive green, and Tiber brown, dusk blue in the shadows. |
| United States | Cooler pigments of slate blue, white marble, and dusk blue, with a little warm candlelight. |
| Night | Night pigments of indigo and dusk blue, one warm lamp or fire. |

Muted gold belongs only on the single Hagia Sophia interior plate.
It is not part of the Constantinople series palette. A gold note on
every Byzantine beat makes those episodes busier than the Roman ones.

## Shot grammar

Six compositions. New beats use one of these framing sentences, so a
road in episode 10 is framed like the road in episode 1.

| Type | Framing sentence | Who is in it |
| --- | --- | --- |
| Wide city | Wide view, horizon in the upper third, empty foreground, distant figures only. | No named role |
| Interior | Medium view, one figure, plain wall behind, empty floor. | One role from the costume table |
| Road | Wide view, the column small in the frame, open sky above. | Distant figures, or “legionaries” / “infantry” |
| Harbor | Wide view, water as a large flat shape, few vessels. | No named role |
| Desk | Medium view, one figure seated, bare wall, papers with no writing. | One role from the costume table |
| Map | Flat painted shapes filling the frame. | Nobody |

Place the subject on the left third or the right third so the Ken Burns
pan has room. Leave the center empty.

Wide city, harbor, road, and map beats stay free of portrait words.
The render path adds a sharply detailed face and a medium-full shot
when the beat contains any of: soldier, president, king, man, woman,
officer, person, leader, minister, commander. For a wide plate say
“distant figures,” “legionaries,” “infantry,” or “a senator.” Save
“a figure in …” for desk and interior plates. “Senator,” “emperor,”
“legionary,” and “figure” do not trigger that face line.

Do not write Turkish, Egyptian, or Syrian onto a place. Those words
attach a modern nationality and a face. Sixth-century Constantinople
is an Eastern Roman city.

## Costume and place

Episode 1 Chapter 1 does not use the rows below. That night is about
509 BC, and lorica segmentata, marble, and an imperial toga are
forbidden. Use `docs/rome_softly_ep01_ch01.md`.

Default centuries for later episodes:

- Rome: 1st and 2nd centuries, the city inhabited.
- Constantinople: the 6th century. Sea walls, Hagia Sophia, late
  antique clothes. Add the 11th or the 15th only when an episode is
  about that century, and add the rows here first.
- United States: whichever decade the episode is about. Add a costume
  row and a place row before generating that decade.

| Role | Clothes and body | Place, when the shot needs one |
| --- | --- | --- |
| Roman street | Distant figures in tunics | Inhabited 2nd-century Rome, plaster insulae, a working street |
| Senator | Wool toga, wooden bench | The Curia, plain plaster, 1st century |
| Legionaries | Lorica segmentata, on foot | A paved road in open country, 1st century |
| Emperor | One figure on a low dais, wool and a plain cloak | A shallow hall, painted plaster, no inscriptions |
| Constantinopolitan street | Distant figures in late antique tunics and cloaks | Inhabited 6th-century Constantinople, sea walls and domes over the Golden Horn |
| Court figure | Chlamys | A plain hall, flat colored wall, 6th century |
| Hagia Sophia | One standing figure, late antique cloak | Interior in the 6th century, marble and gold reduced to flat shapes |
| US figure, 1790s | Dark coat, waistcoat, breeches | A plain federal room, wooden furniture |
| US figure, 1860s | Black frock coat | A wooden desk or a bare civic room |
| US infantry, 1860s | Sack coat, on foot | A dirt road, open sky |
| US figure, 1960s | Dark suit, narrow tie | A plain office, bare wall |
| Capitol | No figure | The building as a painted mass, empty foreground, daylight |

Unqualified “Rome” renders as today’s ruins. Unqualified
“Byzantium” mixes Greek temples, Ottoman Istanbul, and fantasy palaces.
Name the century and say the city is inhabited.

An emperor or a president is a type in the clothes above. Naming
Lincoln or Justinian does not lock the face, and the face will change
from still to still. Keep the face small. A tall figure in the locked
clothes is the series design.

## Beat template

One beat is one still. Fill the braces, then append the palette
sentence and the style sentence.

```
{shot type}. {who}, {clothes from the table}, {one action}, {place from the table}, {century}. {framing sentence} {palette sentence} {style sentence}
```

Example, Roman interior:

> Interior. A senator in a wool toga seated on a wooden bench in the Curia, 1st century. Medium view, one figure, plain wall behind, empty floor. Pigments of parchment cream, Roman ochre, terracotta, olive green, and Tiber brown, dusk blue in the shadows. Painterly storybook illustration in gouache and watercolour on textured paper, soft brush edges, light ink accents, low contrast, soft light, generous empty space, no text, no letters, no photorealism, no 3D render, no gore.

Example, United States road:

> Road. Infantry in sack coats marching, small in the frame, on a dirt road, 1860s. Wide view, the column small in the frame, open sky above. Cooler pigments of slate blue, white marble, and dusk blue, with a little warm candlelight. Painterly storybook illustration in gouache and watercolour on textured paper, soft brush edges, light ink accents, low contrast, soft light, generous empty space, no text, no letters, no photorealism, no 3D render, no gore.

Write beats by hand from this template. Extract Beats will replace
curated beats when the scene text no longer matches the stored source.
On an episode whose beats are already locked, do not run Extract Beats.

Build Prompts may paraphrase a beat into a busier prompt. If the still
drifts, paste the template back into that prompt and mark the row
`manually_edited`. Keeper prompts stay `manually_edited` so a later
Build Prompts does not restyle them.

Maps carry no labels. These models cannot spell Latin or English.
A title card, outside the image model, is where a name belongs.

## Plate library

Keep one VID project as the library. Canonical plates live there and
are copied into episode projects. Episode projects generate only new
events.

Suggested keepers for the first library, using the default centuries:

| Id | Shot | World |
| --- | --- | --- |
| R-street | Wide city | Rome |
| R-senate | Interior | Rome |
| R-road | Road | Rome |
| R-harbor | Harbor | Rome |
| R-desk | Desk | Rome |
| R-map | Map of the Mediterranean, land and water only | Rome |
| C-walls | Wide city, sea walls | Constantinople |
| C-church | Hagia Sophia interior | Constantinople |
| C-court | Interior, court hall | Constantinople |
| C-harbor | Harbor | Constantinople |
| C-map | Map of the eastern Mediterranean, land and water only | Constantinople |
| U-civic | Wide city, Capitol | United States, decade of the first episode |
| U-chamber | Interior | United States |
| U-road | Road | United States |
| U-harbor | Harbor | United States |
| U-desk | Desk | United States |
| U-map | Map of North America, land and water only | United States |

To repeat a plate in an episode, copy the approved PNG over that
scene’s Lightbox file after the beat exists, select it, and do not
regenerate that slot. HiDream files are named
`scene_NNN_hidream_bNN_vN.png`.

Accept a new library plate only while it is open beside the canonical
plate of the same shot type. All five have to hold:

1. The same flat painted medium.
2. The palette of that world, and no extra pigments.
3. A large quiet area still in the frame.
4. Clothes and buildings from the tables.
5. No letters, no ruins, no tourist foreground, no photographic skin.

If two of the five fail, rewrite the beat. Do not keep a near miss in
the library. A near miss becomes the reference the next episode drifts
toward.

## Proof set

Generate these twelve once, one HiDream seed each, and keep the PNGs
in the library project. They are the regression test. When a VID
change touches styles or prompt shaping, run them again and compare.

Keep:

1. Inhabited 2nd-century Rome, a street of plaster insulae. Wide city framing. Roman palette. Style sentence.
2. A senator in a wool toga on a wooden bench in the 1st-century Curia. Interior framing. Roman palette. Style sentence.
3. Legionaries in lorica segmentata, small on a paved road, 1st century. Road framing. Roman palette. Style sentence.
4. Inhabited 6th-century Constantinople, sea walls and the Golden Horn, domes, late antique cloaks. Wide city framing. Roman palette. Style sentence.
5. Hagia Sophia interior, 6th century, one standing figure, flat shapes. Interior framing. Roman palette. Style sentence.
6. A painted map of the Mediterranean, ochre land, dusty blue water. Map framing. Style sentence.
7. A figure in a black 1860s frock coat at a wooden desk, papers with no writing. Desk framing. United States palette. Style sentence.
8. The Capitol as a painted building, empty foreground, daylight. Wide city framing. United States palette. Style sentence.
9. Infantry in 1860s sack coats, small on a dirt road. Road framing. United States palette. Style sentence.
10. A painted map of North America, graphite land, cool gray water. Map framing. Style sentence.

Expect these two to fail. If they succeed, the lock is not what you
think it is:

11. “The Roman Forum,” with no century, no inhabitants, and no style sentence. This comes back as ruins.
12. “The President in the Oval Office,” with no decade and no style sentence. This comes back as a modern photograph.

## Episode checklist

1. Create the episode project. Match the series lock table.
2. Confirm the episode’s decades already have costume and place rows in this file.
3. Copy library PNGs onto the recurring beats. Select them.
4. Write new beats from the template. One action, one shot type.
5. Generate HiDream, one seed, 1344×768.
6. Reject beside the canonical plate of that shot type, using the five checks.
7. Mark keeper prompts `manually_edited`. Add a new canonical plate to the library only if it passes beside the reference.
8. Assemble with Ken Burns. Leave the orange shot badge orange.
9. Do not run Extract Beats again on this episode.

## Later, only if the series earns it

A period profile can fill clothes and rooms when a beat forgets them.
It does not replace the sentences in this file. A 45-second shot target
would make the Lightbox badge agree with the hold. A shared plate shelf
inside the app would replace the file copy. None of these is required
to start.

Stay off Qwen-Image, person LoRAs, image-to-video, and Blender for
this channel. Labeled maps and locked likenesses are a different show.
