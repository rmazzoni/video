# Sleepy — Rome, Softly

This is the working standard for the Sleepy environment inside VID, as built for the series *Roma, sottovoce* / *Rome, Softly*. It records what the application does, the rules it enforces, and the choices that were considered and left out.

Related papers, which the app does not load:

- `docs/sleep_history_stills.md` — stills craft and the older shot notes
- `docs/rome_softly_master_prompt.md` — prompt assembly and the five style endings
- `docs/rome_softly_ep01_ch01.md` — Episode 1, Chapter 1 examples

When those papers disagree with this file on motion, canvas size, or how many pictures a scene gets, this file is the application.

## 1. What Sleepy is

Sleepy is not a second program. It is the outer tab **Sleepy** next to **Main** in the existing VID window (`main.py`). One editorial app, one pipeline, one ComfyUI. The only separate environment is the cloned voice, which runs in its own Python install so the Qt process never imports `qwen_tts`.

Main is unchanged. Sleepy never calls `set_project_path`, `update_setting`, or `save_settings`. Its picture and mix locks travel as `extra_config` for that run only. Main loudness stays −17 LUFS / −1 dBTP. Main Ken Burns stays the 12-second move. Main still offers several image models and three seed neighbours.

A Sleepy episode is a normal VID project folder whose `vid_project.yaml` says `environment: sleepy`. Main projects are refused on this tab. Sleepy episodes are refused by operations that require a Main project.

## 2. Machine and the two environments

The card is an RTX 4080 SUPER, 16 GB. That is enough if HiDream and the voice never load together.

| Piece | Where | Rule |
| --- | --- | --- |
| VID app | `F:\VID\venv`, Python 3.11 | Qt, tests, HiDream through ComfyUI |
| ComfyUI | `F:\VID\ComfyUI`, port 8188 | Paints the stills |
| Voice | `F:\VID\voice\venv`, Python 3.12 | Qwen3-TTS only. The app starts it as a subprocess |
| Voice weights | `F:\VID\voice\models\Qwen3-TTS-12Hz-1.7B-Base` | Empty checkpoint field uses this folder |
| Voice cache | `F:\VID\voice\hf-home` | `HF_HOME` for that environment |

HiDream in the app stays FP8 at about 1 megapixel. Do not switch it to BF16. The voice worker is allowed BF16 because it is a different model in a different process. Attention there is PyTorch SDPA, not flash-attn. `transformers` stays at 4.57.3. The pinned Qwen3-TTS commit is `022e286`. Primary model is 1.7B-Base. 0.6B is the fallback if 1.7B does not fit, not the default. Streaming is off (`non_streaming_mode=True`) because upstream streaming runs too fast.

The GPU lock is `reserve_gpu` / `gpu_owner`. The voice owner is `sleepy-voice`. A picture run will not start while that owner is set, and Speak will not start while a pipeline owns the card. A Sleepy failure can still surface on Main’s pipeline dialog. That coupling was left as it is.

## 3. Where settings live

Two different config directories:

| Path | What it is |
| --- | --- |
| `F:\VID\config\sleepy.yaml` | The running app’s Sleepy prefs: last episode, up to 8 recent paths, reference clip, transcript, optional checkpoint |
| `F:\VID\src\config\project_profiles.yaml` | Chapter locks. Sleepy lists keys that start with `rome_softly` |
| `F:\VID\src\config\settings.yaml` | Not the file the running app loads |

Episode files, under the episode folder:

| File | Role |
| --- | --- |
| `vid_project.yaml` | Marks the folder `environment: sleepy` |
| `input/narration_it.txt` | Italian script, the picture owner once split |
| `input/narration_en.txt` | English script, added when it exists |
| `input/narration_it.docx` / `narration_en.docx` | The Word file that was loaded |
| `input/narration.txt` | Mirror of whichever language last published the scenes |
| `output/scenes.yaml` | Scene id, spoken text, caption |
| `output/sleepy_stills.yaml` | One row per still: scene, beat, English prompt |
| `output/sleepy_episode.yaml` | Seed, chapter-lock key, language, which language owns the pictures |
| `output/model_prompts.yaml` | Written when a still is painted. HiDream only |
| `output/lightbox/scene_NNN_hidream_bNN_v1.png` | The painted file |
| `output/lightbox_selections.yaml` | Files the final video will use |
| `output/audio/scene_NNN.mp3` | One voice file per scene, plus `timings.yaml` |

Reopening the episode that is already open does not reload. That keeps unsaved script text. Close VID and open it again after a code change. A window that is already open keeps the old list in memory and will write it back if you Split or switch stills in that window.

## 4. The six tabs

Language at the top is Italian or English. It chooses the script on screen and the language the clone will speak. Stills stay English either way.

**Episode.** Create or open an episode. The create dialog asks for a name, a parent folder, the Italian Word file, and a chapter lock. English is not required at creation. The lock is stored on that episode only (`profile_key` in `sleepy_episode.yaml`). It is not a global switch. The only lock shipped today is `rome_softly_ch01`. The default seed is 42. Recent episodes: 8.

A colon in the title becomes ` - ` in the folder name. `< > " / \ | ? *` and control characters become spaces. Reserved Windows names (`CON`, `COM1`, and the rest) gain the word `episode`. An empty name is refused.

**Script.** Save script. Update Italian Word. Add English Word. Split into scenes.

Update Italian Word and Add English Word read a `.docx` only. A `.doc` is refused before any folder is touched. Headings, titles, and subtitles are skipped (English and Italian style names). Tables and headers are not read. Non-breaking spaces collapse. Body paragraphs are joined with a blank line. The Word file is copied into `input/`. Neither button republishes scenes, stills, or the other language. The status line says to split again when the Italian image count and the scenes on disk differ.

Split is what moves the pictures. It writes `scenes.yaml`, fills empty still prompts from the script, and keeps a prompt already typed for that scene id. If English is showing and Italian already owns the pictures, Split saves the English text and leaves the picture scenes on Italian. Speaking English later requires the same scene count.

**Stills.** Headed “Final stills”. One row per still: `Scene NNN · still N`. The scene narration is read-only. The English prompt is editable. Generate this still paints the prompt in the box and shows it on the right. Generate final stills paints every still that already has a prompt and skips the empty ones. Replace existing stills applies to the batch only. Generate this still always replaces that one file. Add still adds another beat for the same scene, sharing the narration. Remove still, when it is an extra beat, deletes the row and deletes the PNG. The last beat of a scene is cleared, not removed.

If a prompt has no Rome Softly ending, the flat City ending is added at paint time. A prompt that already names the flat ending, or the older gouache ending, is left as written.

**Lightbox.** One card per picture, including pictures that are not painted yet. The text beside the frame is the `[IMMAGINE]` caption, not the narration. A painted file appears only while that still is still in the list. Click a painted image to open it. The status line is `N pictures. M painted.`

**Voice.** Reference clip (wav, mp3, flac, or m4a), the transcript of that clip word for word, and an optional checkpoint folder. Speak this language. Speak again replaces audio even when the text has not changed. Speak does nothing until the clip and the transcript are both set. There is no stand-in voice and no public demo clip.

**Final.** Make final video. Open final video. The note on the tab is the motion and mix lock below. The video is refused until every prompted still has a file on disk, and until each scene has an mp3.

Cancel stops the voice subprocess or the pipeline run that this tab started.

## 5. Script standard

A Sleepy script with image cues is one picture per cue, about 75–80 seconds of speech, about one picture every 140 words at the series pace.

Three markers, in this order inside each picture:

```
[IMG 01] [IMMAGINE: Titolo di apertura. Il Tevere al crepuscolo, …]

IMG 01 — PROMPT (EN) [palette: Rural / domestic / dusk]: Wide establishing landscape …
Style: flat vector-style illustration, … no gore.

Buonasera, e benvenuti.
…
```

| Marker | What it is | Spoken? |
| --- | --- | --- |
| `Benvenuti` | Starts the spoken Italian. The title and the production note before it are not read. If the word never appears, narration paragraphs are kept | Yes, from that paragraph on |
| `[IMG NN] [IMMAGINE: …]` | Lightbox caption for that picture. The caption is the text inside the brackets | No |
| `IMG NN — PROMPT (EN)` | Start of the English still prompt. A `[palette: …]` tag may sit between `(EN)` and the description | No |

No extra end-of-prompt marker is required. The prompt is one paragraph. The blank line after it is the separator. The next paragraph is narration. Do not put a blank line inside the prompt, or the following paragraph will be read aloud.

Also dropped, and not spoken:

- A production note that contains `(non leggere)`
- A short line that is only `Capitolo` or `Chapter`
- The English prompt
- A trailing bibliography after the last picture (works-cited lines, classical loci, press names)

A script with no `[IMG NN]` cue still splits on paragraphs, minimum about 20 characters. That path is for a plain narration and for older tests. Episode 1 uses the image cues.

Picture scene ids are the IMG numbers, in document order. They are not paragraph numbers.

On disk for Episode 1, after the image split: 97 scenes, ids 1–97, 97 captions, 97 prompts, 13642 spoken words. Scenes 9, 17, 94, and 97 have a picture and no spoken lines. The voice will not start until each of those has a line, or the scene is removed. The app does not invent silence or a line.

Prompts already typed for scenes 1–5 were kept when the episode was republished. Scene 1’s typed prompt is the longer Tiber text. Scenes 2–5 keep the typed wording, which is the same picture as the script line without the `[palette: …]` prefix. Later scenes took the script prompt. Split again only if the script itself has changed. A typed prompt is not replaced when it is already non-empty.

## 6. Picture standard

One model: HiDream. One seed: offset `[0]`, so the file is always `scene_NNN_hidream_bNN_v1.png`. No draft candidates, no neighbour seeds, no other model in the Sleepy run.

| Setting | Value |
| --- | --- |
| Canvas | 1344 × 768 |
| Final frame | 1920 × 1080 |
| Frame rate | 24 |
| Steps | 28 |
| Guidance | 1.5 |
| Shift | 6.0 |
| Sampler / scheduler | euler / normal |
| Seed offsets | `[0]` |

The canvas stays at 1344 × 768 because FP8 fills 16 GB near 1 megapixel. The style guide’s “at least 2K, ideally 4K” is for a later upscale of keepers, not for the HiDream canvas. The mux frame is already 1920 × 1080.

Generate final stills skips an empty prompt and logs it as left for later. Generate this still requires a prompt and paints only that beat.

HiDream’s negative prompt is not used. Exclusions have to live in the positive prompt, which is why the style ending ends with `no text, no letters, no watermark, no photorealism, no 3D render, no gore.` A tool that does accept a negative can use: text, letters, captions, watermark, logo, photorealistic, 3D render, CGI, painterly brush strokes, watercolour blooms, gouache texture, thick black outlines, cartoon, anime, chibi, neon colours, oversaturated, harsh shadows, lens flare, stylized smoke puffs, cartoon clouds, blood, gore, close combat, modern objects, marble buildings in archaic Rome, Colosseum, legionary segmented armour, coins, plate armour, deformed hands, extra fingers.

## 7. Visual style, v2 (9 October 2026)

Look: flat, poster-like illustration. Clean simplified shapes and silhouettes. Smooth gradient skies. Subtle paper grain. One limited muted palette. Travel poster or a modern illustrated history book. Calm, legible, elegant. Never cartoonish, never photographic.

Rome is a real city of tuff, timber, and painted terracotta, not an endless pastoral idyll.

Flat rules the prompt must carry, not only the ending:

- Few or no outlines. Any outline is thin and in the same colour family. Never a black cartoon contour.
- Faces minimal but dignified.
- Gradients only for skies, water, and light falloff. Everything else flat, or two or three tonal steps.
- Subtle paper grain. No brush strokes, no watercolour blooms, no painterly edges.
- Smoke, written in the scene: “thin straight wisps of smoke rising vertically, no stylized puffs.”
- Mist: soft horizontal gradient bands.
- Light: soft, low-contrast, one source. No hard speculars, no lens flare.
- Depth: three to five overlapping planes, lighter and less saturated toward the horizon.
- No text, letters, captions, or watermark in the image. On-screen titles are an edit layer.

Prompt order, English only: shot and framing, subject and action, place and date with period details, light and time of day, mood, then exactly one style ending.

The ending, with the palette clause in the middle:

> Style: flat vector-style illustration, clean simplified shapes, simplified silhouettes, subtle paper grain texture, smooth gradient sky, limited muted palette of [MOOD PALETTE], soft low-contrast lighting, calm atmosphere, generous negative space, historically accurate, cinematic 16:9 wide composition, no text, no letters, no watermark, no photorealism, no 3D render, no gore.

Hex codes are not sent to HiDream. The words are.

### Five palettes, one per image

| Key | When | Palette text |
| --- | --- | --- |
| Rural | Domestic, dawn, dusk, countryside | apricot, dusk blue, olive green and parchment |
| City | Political, religious, Rome in daylight. The default | tuff stone grey, roman ochre, terracotta and muted bronze |
| Military | Conflict, including an army camp at night | iron grey, dark bronze, deep oxblood red and overcast slate sky, austere mood, soldiers kept at a distance, no close combat |
| Night | Darkness or stillness is the mood | deep indigo and dusk blue with a single warm light source |
| America | Any post-classical scene, including the Florida study at night | cool slate blue, white marble and parchment |

Choice order when two could apply:

1. An army camp is Military, even at night.
2. Anything after antiquity, including the modern study, is America, even at night.
3. Night only when darkness or stillness is the emotional point and the other two do not apply.
4. Otherwise City. Keep Rome urban.
5. Avoid more than two Rural images in a row.

Episode 1’s planned balance is City 36, Rural 20, Military 15, Night 10, America 16.

The Military clause includes “austere mood, soldiers kept at a distance, no close combat” inside the palette phrase, so it sits before “soft low-contrast lighting.” The other four palettes do not add that clause.

If the style ending is missing, the app appends the City ending and does not also append a photographic face line. If the prompt already contains `flat vector-style illustration`, it is kept, including a Rural, Night, Military, or America ending. A second City ending is not stuck on after it. An older prompt that still says `painterly storybook illustration` is also left alone, so stored gouache prompts are not rewritten into photographs or into the flat ending. Replacing those is a script update, then Split, not an automatic conversion.

The marker the code looks for is `flat vector-style illustration`. The legacy marker is `painterly storybook illustration`.

## 8. Historical lock for Chapter 1

`rome_softly_ch01` fills only clothing or place that the beat left unnamed. It must never add people, kings, crowds, or events.

Place, only if unnamed: Rome on the left bank of the Tiber about 509 BC, a real city of grey-brown cappellaccio tuff, timber, mud-brick, thatch or painted terracotta tiles, earth ramparts, and a yellow-brown river. Not an empty pastoral landscape. No marble, no concrete vaults, no Colosseum, no basalt paving, no glass windows.

Clothing, only if the beat already has a person and names no garments: bearded adults with longish hair, a short earth-wool tunic, or a simple rounded mantle. Women in an ankle-length tunic. No imperial toga, no clean-shaven face in an archaic scene, no segmented armour, no red military uniform.

Archaic Rome in the pictures, beyond the profile line: thatch, timber, mud-brick, cappellaccio tuff, terracotta. Bearded men before about 300 BC. Hoplite-style arms. No marble temples, no Colosseum, no lorica segmentata, no coins, no imperial togas, no readable writing. Violence is implied. Soldiers stay at a distance. No gore, no close combat.

The profile text is not a dump of the style essay. Grounding treats profile words as allowed words, so palette names and the style slogan stay out of it.

A later chapter gets its own `rome_softly_…` key, chosen at Create and stored on that episode.

## 9. Motion

Sleepy motion style is `sleepy`. It is separate from Main’s `auto`.

| | Main `auto` | Sleepy |
| --- | --- | --- |
| Zoom | 1.05 → 1.12 | 1.03 → 1.05 |
| Pan | 0.25 ↔ 0.75 of the spare margin | 0.05 ↔ 0.95 of that same small margin |
| Travel | The move finishes at 12 seconds, then the frame holds | The move runs the whole clip, last frame included |
| Purpose | A normal shot | Keep a phone display awake while the viewer sleeps |

Center travel is about 3.5 percent of the image width, locked between 3 and 5 percent. Direction alternates by clip index. Vertical position stays centered. One continuous drift per picture. The picture does not freeze after 12 seconds.

`MOTION_VERSION` was not bumped. Main’s 12-second cap is untouched. `OPTIMAL_SHOT_SECONDS` remains 12 and is not the Sleepy hold.

The final-tab line when this motion is on: “Each still drifts for the whole scene, a pan and zoom of about 3–5%.”

## 10. Lightbox standard

The Lightbox is the contact sheet for the episode, not a dump of every PNG in the folder.

- One card per scene that the script’s `[IMG]` cues define.
- The caption is the `[IMMAGINE: …]` text, shown beside the frame.
- Click a painted image to maximize it. Previous and Next, and the left and right arrow keys, step through the painted stills in Lightbox order. The same caption sits under the large picture. Empty cards are not in that sequence. Close and Escape leave the picture. Tweak Prompt closes it and opens that same still on the Stills tab, with its English prompt ready to edit.
- The frame shows `scene_NNN_hidream_bNN_v1.png` when that beat is still in `sleepy_stills.yaml` and the file exists.
- Otherwise the frame says “Not painted yet”.
- A file left behind after Remove still is not shown. Remove still also deletes that file.
- The final video uses the selection list built from the still rows, not every PNG that happens to be in `output/lightbox`.

Episode 1’s sheet is 97 cards. Scenes 1–5 have a painted still. The mistaken second still of Scene 1 (`scene_001_hidream_b02_v1.png`) was removed from the list and then from disk.

## 11. Voice standard

Italian first. English later, on the same pictures, with the same clone.

The clone is Qwen3-TTS 1.7B-Base, zero-shot from Roberto’s own reference clip plus a word-for-word transcript. A fine-tune checkpoint is optional and stays empty until one is trained. Training has not been started. Do not point the reference at the public demo `clone.wav`.

Contract per scene: one `scene_NNN.mp3` and one duration in `timings.yaml`. Audio is 192 kbps. If the text has not changed, Speak skips that scene unless Speak again is checked.

Pauses, baked into the mp3:

| Boundary | Pause |
| --- | --- |
| Between sentences | 0.8 s |
| Between paragraphs | 2.5 s |
| A hard cut inside one long sentence | none |
| Between scenes | 2.5 s on the last chunk of every scene except the last |

Chunks stay at or under 300 characters, about 30 seconds. Abbreviations such as Mr, Dr, and St are not treated as sentence ends.

Empty scenes abort the whole speak before any audio is written. The message names them: “Scenes 009, 017, 094, 097 have an image but no spoken lines.”

English is spoken on the picture scene ids. If the English split count differs, Speak stops and asks for a matching count. It does not renumber the pictures.

Pace target for the series, used when writing, not measured by the app: about 110 words per minute, episodes of about 2 to 2.5 hours, no cliffhanger at the end of an episode.

## 12. Final mix

Sleepy only, and only when the run carries the keys:

| | Main, keys absent | Sleepy |
| --- | --- | --- |
| Integrated loudness | −17 LUFS | −20 LUFS |
| True peak | −1 dBTP | −3 dBTP |

No sound effects in the episode. If music is added later, it is ducked to about −25 dB under the voice. That ducking is a series rule, not a control on the Final tab.

The clip engine is Ken Burns with the sleepy motion above. Duration of each clip comes from the scene’s mp3.

## 13. Editorial rules the pictures and the words follow

These are series rules. The app enforces the ones in the sections above. The rest are for the script and the prompts, not for a separate checker.

- Calm sleep narration. No cliffhangers. No SFX.
- US parallels are non-partisan, stop around 1990, and do not show living politicians.
- Proper names stay names inside English sentences. They are not translated into descriptions and they are not painted as labels.
- On-screen titles, including “Roma, sottovoce”, are added in the edit. The image leaves clear sky or wall for them and says `no text`.
- One image every 75–80 seconds, for the whole spoken scene.

## 14. Episode 1 on disk

Folder:

`F:\01 Sleepy\La nascita della Repubblica - Lucrezia, Cincinnato e le Dodici Tavole (509–449 a.C.)`

Chapter lock `rome_softly_ch01`. Language Italian. Seed 42. Scenes on disk: 97 image scenes, not the old 419-paragraph split.

The Italian source is the image script in `input/narration_it.txt`. A newer Word file is loaded with Update Italian Word, then Split. Split is what replaces the scene list. Update alone does not.

Reference clip, transcript, and checkpoint in `F:\VID\config\sleepy.yaml` are empty. Speak will refuse until the real recording is set.

## 15. What was considered and not built

The style guide and the voice brief contain work this app does not do. Leaving them out is a decision, not a missing step.

| Proposal | Decision |
| --- | --- |
| A second application | No. One VID app, outer tabs Main and Sleepy |
| 2–4 draft candidates per still | No. One seed, straight to final |
| Pan and zoom of 5–10%, two or three moves per image, a change every 30–60 seconds | No. One 3–5% drift for the whole clip |
| Parallax on about one image in five | No |
| 2–3 second cross-dissolves, a grain overlay | No |
| HiDream at 2K or 4K | No. 1344 × 768, mux at 1920 × 1080, upscale keepers later |
| Thumbnail generator, plate library | No. Editorial, not this app |
| Automatic rewrite of stored gouache prompts into the flat ending | No. A prompt that already has either ending is kept |
| Auto-split when the episode opens | No. Opening must not rewrite the episode. Split does |
| Edge TTS for Sleepy | No. The voice stage is the Qwen worker, not stage `tts` |
| Fine-tune (tasks T4–T14), or the public demo clip as Roberto | Not started. Zero-shot first, from his own recording |
| `VOICE_CONSENT.md` | Not written |
| YouTube “altered or synthetic” flag and a spoken disclosure of the English clone | Agreed for publication. Not a control in the app |

## 16. Code map

| Concern | File |
| --- | --- |
| Episode, script split, stills, lightbox cards, pipeline lock | `sleepy/chapter.py` |
| The Sleepy window | `ui/sleepy_panel.py` |
| Flat style, five palettes, “do not add a second ending” | `prompts/visual_styles.py` |
| Prompt finaliser skips the photographic face line | `prompts/model_prompt_service.py` |
| Chapter 1 place and clothing | `config/project_profiles.yaml` (`rome_softly_ch01`) |
| Sleepy Ken Burns | `video/ken_burns_generator.py` |
| Voice contract, in the app process | `narration/qwen_voice.py` |
| Voice model, out of the app process | `narration/qwen_voice_worker.py` |
| Tests | `tests/test_sleepy.py`, `tests/test_ken_burns.py`, `tests/test_visual_beats.py` |

Tests run with `F:\VID\venv\Scripts\python.exe -m unittest` from `F:\VID\src`, offscreen Qt. They must not construct a full `MainWindow`, must not launch the live GUI, and must not start HiDream or the voice. A panel test may open the real episode from `sleepy.yaml`. That open must not write the episode.
