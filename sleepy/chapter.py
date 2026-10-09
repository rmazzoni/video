"""Pure helpers for a Sleepy episode.

Sleepy paints one HiDream still per beat and does not write Main's settings.
"""

from __future__ import annotations

import os
import re
import shutil
from typing import Dict, Iterable, List, Sequence, Tuple

import yaml

from narration.scene_splitter import SceneSplitter
from prompts.visual_styles import ensure_rome_softly_style
from utilis.project_paths import ProjectLayout

LANGUAGES = ("Italian", "English")
DEFAULT_PROFILE_KEY = "rome_softly_ch01"
CANVAS_WIDTH = 1344
CANVAS_HEIGHT = 768
FINAL_WIDTH = 1920
FINAL_HEIGHT = 1080
HIDREAM_STEPS = 28
HIDREAM_GUIDANCE = 1.5
HIDREAM_SHIFT = 6.0
MIN_SCENE_CHARS = 20
# Main's finished mix is left at the value final_video already used.
MAIN_TARGET_LUFS = -17.0
MAIN_TRUE_PEAK_DB = -1.0
# Series mix for a Sleepy final only.
SLEEPY_TARGET_LUFS = -20.0
SLEEPY_TRUE_PEAK_DB = -3.0

DEFAULT_EPISODE = {
    "seed": 42,
    "profile_key": DEFAULT_PROFILE_KEY,
    "language": "Italian",
    "scenes_language": "",
}

DEFAULT_APP_PREFS = {
    "project_path": "",
    "recent": [],
    "reference_wav": "",
    "reference_transcript": "",
    "checkpoint": "",
}


def source_config_dir() -> str:
    """Repo config that holds project profiles (F:\\VID\\src\\config)."""
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")


def normalize_language(value: str) -> str:
    text = str(value or "").strip().lower()
    if text in {"it", "italian", "italiano"}:
        return "Italian"
    if text in {"en", "english"}:
        return "English"
    raise ValueError("Sleepy voice language must be Italian or English.")


def language_suffix(language: str) -> str:
    return "it" if normalize_language(language) == "Italian" else "en"


def resolve_seed_offsets(value) -> List[int]:
    """Main stays on three neighbours. Sleepy passes ``[0]`` for one still."""
    if value is None:
        return [-1, 0, 1]
    if isinstance(value, bool):
        return [-1, 0, 1]
    if isinstance(value, (int, float)):
        return [int(value)]
    if not isinstance(value, (list, tuple)) or not value:
        return [-1, 0, 1]
    return [int(item) for item in value]


def variant_filename(scene_id: int, model_key: str, beat_idx: int, v_idx: int) -> str:
    return (
        f"scene_{int(scene_id):03d}_{model_key}_b{int(beat_idx):02d}_v{int(v_idx)}.png"
    )


def filenames_for_offsets(
    scene_id: int,
    beat_idx: int,
    offsets,
    model_key: str = "hidream",
) -> List[str]:
    """Names final_images writes. ``enumerate(..., 1)`` so one offset is v1."""
    return [
        variant_filename(scene_id, model_key, beat_idx, v_idx)
        for v_idx, _offset in enumerate(resolve_seed_offsets(offsets), 1)
    ]


def still_file_path(project: str, scene_id: int, beat: int) -> str:
    """The one final still for a beat: scene_NNN_hidream_bNN_v1.png."""
    filename = filenames_for_offsets(int(scene_id), int(beat), [0])[0]
    return os.path.join(ProjectLayout(project).lightbox, filename)


_STILL_NAME = re.compile(
    r"^scene_(\d+)_([A-Za-z0-9]+)_b(\d+)_v(\d+)\.png$",
    re.IGNORECASE,
)


def list_lightbox_stills(project: str) -> List[dict]:
    """Painted stills in this episode's lightbox, in scene and beat order."""
    folder = ProjectLayout(project).lightbox
    if not os.path.isdir(folder):
        return []
    rows = []
    for name in os.listdir(folder):
        if not name.lower().endswith(".png"):
            continue
        match = _STILL_NAME.match(name)
        if match:
            scene_id = int(match.group(1))
            model = match.group(2).lower()
            beat = int(match.group(3))
            variant = int(match.group(4))
        else:
            scene_id, model, beat, variant = 0, "", 0, 0
        rows.append({
            "scene_id": scene_id,
            "model": model,
            "beat": beat,
            "variant": variant,
            "filename": name,
            "path": os.path.join(folder, name),
        })
    rows.sort(key=lambda row: (
        int(row["scene_id"]), int(row["beat"]), int(row["variant"]), row["filename"],
    ))
    return rows


def rome_softly_profile_keys(keys: Iterable[str]) -> List[str]:
    found = [str(key) for key in keys if str(key).startswith("rome_softly")]
    return found or [DEFAULT_PROFILE_KEY]


def ensure_rome_softly_prompt(prompt_text: str) -> str:
    """Keep a prompt that already has one palette. Otherwise end with City."""
    return ensure_rome_softly_style(prompt_text)


def narration_path(project: str, language: str) -> str:
    return os.path.join(project, "input", f"narration_{language_suffix(language)}.txt")


def scenes_path(project: str) -> str:
    return os.path.join(project, "output", "scenes.yaml")


def stills_path(project: str) -> str:
    return os.path.join(project, "output", "sleepy_stills.yaml")


def episode_settings_path(project: str) -> str:
    return os.path.join(project, "output", "sleepy_episode.yaml")


def model_prompts_path(project: str) -> str:
    return os.path.join(project, "output", "model_prompts.yaml")


def selections_path(project: str) -> str:
    return os.path.join(project, "output", "lightbox_selections.yaml")


def manifest_path(project: str) -> str:
    return os.path.join(project, "vid_project.yaml")


def app_prefs_path(config_dir: str) -> str:
    return os.path.join(config_dir, "sleepy.yaml")


def _read_yaml(path: str) -> dict:
    if not path or not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data if isinstance(data, dict) else {}


def _write_yaml(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, allow_unicode=True, sort_keys=False)


def read_manifest(project: str) -> dict:
    return _read_yaml(manifest_path(project))


def is_sleepy_project(project: str) -> bool:
    if not project or not os.path.isdir(project):
        return False
    return str(read_manifest(project).get("environment") or "") == "sleepy"


def _paragraph_is_heading(paragraph) -> bool:
    """Skip chapter titles. Body paragraphs are the scenes."""
    style = getattr(paragraph, "style", None)
    if style is None:
        return False
    style_id = str(getattr(style, "style_id", "") or "").replace(" ", "").lower()
    name = str(getattr(style, "name", "") or "").strip().lower()
    if style_id.startswith("heading") or style_id in {"title", "subtitle"}:
        return True
    if name.startswith("heading") or name.startswith("titolo"):
        return True
    if name in {"title", "subtitle", "sottotitolo"} or name.startswith("sottotitolo"):
        return True
    return False


def read_docx_narration(path: str) -> str:
    """Read a .docx into narration text: one body paragraph, then a blank line.

    Headings and title styles are left out. Tables and headers are not read.
    A legacy .doc file is refused so it is not mistaken for narration.
    """
    source = os.path.abspath(str(path or "").strip())
    if not source or not os.path.isfile(source):
        raise ValueError(f"Word file not found: {path}")
    if os.path.splitext(source)[1].lower() != ".docx":
        raise ValueError(
            "Save the narration as a .docx file. Older .doc files are not read."
        )
    try:
        from docx import Document
    except ImportError as exc:
        raise RuntimeError(
            "python-docx is not installed. Run: pip install python-docx"
        ) from exc
    try:
        document = Document(source)
    except Exception as exc:
        raise ValueError(f"Could not read the Word file: {source}") from exc

    paragraphs = []
    for paragraph in document.paragraphs:
        if _paragraph_is_heading(paragraph):
            continue
        text = " ".join(str(paragraph.text or "").replace("\xa0", " ").split())
        if text:
            paragraphs.append(text)
    if not paragraphs:
        raise ValueError(
            "The Word file has no narration paragraphs. "
            "Headings are skipped. Put each scene in its own body paragraph."
        )
    return "\n\n".join(paragraphs) + "\n"


def _require_scenes(text: str, language: str) -> None:
    if text and not split_scenes(text):
        raise ValueError(
            f"The {language} Word file did not produce any scenes. "
            "Use a body paragraph of at least a short sentence for each scene."
        )


# Windows folder names reject these characters.
_FOLDER_FORBIDDEN = '<>:"/\\|?*'
_RESERVED_FOLDER_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def episode_folder_name(name: str) -> str:
    """Turn an episode title into a Windows folder name.

    ``< > : " / \\ | ? *`` cannot appear in the folder. A colon becomes a
    hyphen. Apostrophes, accents, commas, and periods are kept.
    """
    raw = " ".join(str(name or "").split())
    if not raw:
        raise ValueError("Type an episode name.")
    pieces = []
    for character in raw:
        if character in _FOLDER_FORBIDDEN or ord(character) < 32:
            pieces.append(" - " if character == ":" else " ")
        else:
            pieces.append(character)
    folder = " ".join("".join(pieces).split()).rstrip(" .")
    if not folder:
        raise ValueError(
            "Type an episode name using letters or numbers. "
            'A folder cannot contain < > : " / \\ | ? *'
        )
    if folder.upper() in _RESERVED_FOLDER_NAMES:
        folder = f"{folder} episode"
    return folder


def create_episode(
    parent_dir: str,
    name: str,
    italian_docx: str = "",
    english_docx: str = "",
    profile_key: str = "",
) -> str:
    """Create a Sleepy episode folder without touching the Main project.

    The Italian Word file is the narration that starts the episode. English
    can be stored as well, but picture scenes come from Italian when that
    text is present. ``profile_key`` is saved on this episode only.
    """
    cleaned = episode_folder_name(name)
    project = os.path.abspath(os.path.join(parent_dir, cleaned))
    if os.path.exists(project):
        raise FileExistsError(f"Episode already exists: {project}")

    italian_text = read_docx_narration(italian_docx) if str(italian_docx or "").strip() else ""
    english_text = read_docx_narration(english_docx) if str(english_docx or "").strip() else ""
    _require_scenes(italian_text, "Italian")
    _require_scenes(english_text, "English")

    os.makedirs(os.path.join(project, "input"), exist_ok=True)
    ProjectLayout(project).ensure_dirs()
    _write_yaml(manifest_path(project), {
        "format": "vid_project",
        "version": 1,
        "name": cleaned,
        "environment": "sleepy",
        "input_dir": "input",
        "output_dir": "output",
    })
    write_text(narration_path(project, "Italian"), italian_text)
    write_text(narration_path(project, "English"), english_text)
    if str(italian_docx or "").strip():
        shutil.copy2(
            os.path.abspath(italian_docx),
            os.path.join(project, "input", "narration_it.docx"),
        )
    if str(english_docx or "").strip():
        shutil.copy2(
            os.path.abspath(english_docx),
            os.path.join(project, "input", "narration_en.docx"),
        )
    settings = dict(DEFAULT_EPISODE)
    chosen_profile = str(profile_key or "").strip()
    if chosen_profile:
        settings["profile_key"] = chosen_profile
    save_episode_settings(project, settings)
    save_stills(project, [])
    if italian_text:
        publish_scenes(project, "Italian", italian_text)
    elif english_text:
        publish_scenes(project, "English", english_text)
    return project


def load_app_prefs(config_dir: str) -> dict:
    loaded = _read_yaml(app_prefs_path(config_dir))
    prefs = dict(DEFAULT_APP_PREFS)
    prefs.update({key: loaded.get(key, prefs[key]) for key in prefs})
    recent = loaded.get("recent", [])
    prefs["recent"] = [path for path in recent if isinstance(path, str)] if isinstance(recent, list) else []
    return prefs


def save_app_prefs(config_dir: str, prefs: dict) -> None:
    merged = dict(DEFAULT_APP_PREFS)
    merged.update(prefs or {})
    recent = []
    for path in merged.get("recent") or []:
        if isinstance(path, str) and path not in recent:
            recent.append(path)
    merged["recent"] = recent[:8]
    _write_yaml(app_prefs_path(config_dir), merged)


def remember_project(prefs: dict, project: str) -> dict:
    updated = dict(prefs)
    recent = [os.path.abspath(project)]
    for path in updated.get("recent") or []:
        if os.path.abspath(path) not in recent:
            recent.append(os.path.abspath(path))
    updated["recent"] = recent[:8]
    updated["project_path"] = os.path.abspath(project)
    return updated


def load_episode_settings(project: str) -> dict:
    loaded = _read_yaml(episode_settings_path(project))
    settings = dict(DEFAULT_EPISODE)
    settings.update({key: loaded.get(key, settings[key]) for key in settings})
    try:
        settings["seed"] = int(settings["seed"])
    except (TypeError, ValueError):
        settings["seed"] = int(DEFAULT_EPISODE["seed"])
    try:
        settings["language"] = normalize_language(str(settings["language"]))
    except ValueError:
        settings["language"] = "Italian"
    scenes_language = str(settings.get("scenes_language") or "").strip()
    if scenes_language:
        try:
            settings["scenes_language"] = normalize_language(scenes_language)
        except ValueError:
            settings["scenes_language"] = ""
    settings["profile_key"] = str(settings.get("profile_key") or DEFAULT_PROFILE_KEY)
    return settings


def save_episode_settings(project: str, settings: dict) -> None:
    merged = dict(DEFAULT_EPISODE)
    merged.update(settings or {})
    merged["seed"] = int(merged["seed"])
    merged["language"] = normalize_language(str(merged["language"]))
    if merged.get("scenes_language"):
        merged["scenes_language"] = normalize_language(str(merged["scenes_language"]))
    else:
        merged["scenes_language"] = ""
    _write_yaml(episode_settings_path(project), merged)


def read_text(path: str) -> str:
    if not os.path.isfile(path):
        return ""
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


# One picture per [IMG NN] cue. The English prompt under the cue is not spoken.
_IMG_CUE = re.compile(r"^\s*\[IMG\s*(\d+)\]", re.IGNORECASE)
_PROMPT_LINE = re.compile(
    r"^\s*IMG\s*(\d+)\s*[—–\-:]+?\s*PROMPT\s*\(\s*EN\s*\)\s*:\s*(.*)$",
    re.IGNORECASE,
)
_PROMPT_BARE = re.compile(r"^\s*PROMPT\s*\(\s*EN\s*\)\s*:\s*(.*)$", re.IGNORECASE)
_STAGE_DIRECTION = re.compile(r"^\s*\[IMMAGINE\s*:", re.IGNORECASE)
_PRODUCTION_NOTE = re.compile(r"\(\s*non leggere\s*\)", re.IGNORECASE)
_CHAPTER_TITLE = re.compile(r"^(?:capitolo|chapter)\b", re.IGNORECASE)


def _narration_paragraphs(text: str) -> List[str]:
    paragraphs = []
    for block in re.split(r"\n{2,}", str(text or "")):
        cleaned = " ".join(line.strip() for line in block.splitlines() if line.strip())
        if cleaned:
            paragraphs.append(cleaned)
    return paragraphs


def _looks_like_source_note(paragraph: str) -> bool:
    """A works-cited line, not a sentence of the sleep narration."""
    text = " ".join(str(paragraph or "").split())
    if not text:
        return False
    if _PRODUCTION_NOTE.search(text):
        return True
    loci = re.findall(r"\b[IVXLC]{1,8}\.\d+", text)
    if len(loci) >= 2 or (loci and text.count(";") >= 1):
        return True
    if re.search(
        r"\b(?:CIL\b|Ab Urbe condita|Routledge|University Press|Harvard|Oxford University)\b",
        text,
    ):
        return True
    has_year = re.search(r"\b(?:1[5-9]\d{2}|20\d{2})\b", text)
    if (
        has_year
        and len(text.split()) <= 45
        and text.count(",") >= 1
        and not re.search(r"\b(?:che|quando|perché|perche|oggi|stasera)\b", text, re.IGNORECASE)
    ):
        return True
    return False


def _strip_trailing_sources(paragraphs: Sequence[str]) -> List[str]:
    """Drop a bibliography that follows the last picture. Spoken lines stay."""
    rows = list(paragraphs or [])
    for index, paragraph in enumerate(rows):
        if not _looks_like_source_note(paragraph):
            continue
        tail = rows[index:]
        if len(tail) < 3:
            continue
        hits = sum(1 for item in tail if _looks_like_source_note(item))
        if hits >= 3 and hits * 2 >= len(tail):
            return rows[:index]
    return rows


def parse_image_script(text: str) -> List[dict] | None:
    """One scene per ``[IMG NN]`` cue.

    Returns None when the script has no image cues, so a plain narration
    still splits on paragraphs. Spoken text is the paragraphs after each
    cue. Stage directions, the English prompt, the production note, and a
    trailing bibliography are not spoken. The prompt is kept for the still.
    """
    paragraphs = _narration_paragraphs(text)
    if not any(_IMG_CUE.match(paragraph) for paragraph in paragraphs):
        return None
    blocks: Dict[int, dict] = {}
    order: List[int] = []
    current: int | None = None
    for paragraph in paragraphs:
        cue = _IMG_CUE.match(paragraph)
        if cue:
            number = int(cue.group(1))
            if number not in blocks:
                blocks[number] = {"id": number, "spoken": [], "prompt": ""}
                order.append(number)
            current = number
            continue
        prompt_line = _PROMPT_LINE.match(paragraph)
        if prompt_line:
            number = int(prompt_line.group(1))
            if number not in blocks:
                blocks[number] = {"id": number, "spoken": [], "prompt": ""}
                order.append(number)
            body = str(prompt_line.group(2) or "").strip()
            if body and not blocks[number]["prompt"]:
                blocks[number]["prompt"] = body
            current = number
            continue
        if current is None:
            continue
        bare = _PROMPT_BARE.match(paragraph)
        if bare:
            body = str(bare.group(1) or "").strip()
            if body and not blocks[current]["prompt"]:
                blocks[current]["prompt"] = body
            continue
        if _STAGE_DIRECTION.match(paragraph) or _PRODUCTION_NOTE.search(paragraph):
            continue
        if _CHAPTER_TITLE.match(paragraph) and len(paragraph) < 80:
            continue
        blocks[current]["spoken"].append(paragraph)
    if order:
        last = blocks[order[-1]]
        last["spoken"] = _strip_trailing_sources(last["spoken"])
    return [
        {
            "id": number,
            "text": "\n\n".join(blocks[number]["spoken"]),
            "prompt": blocks[number]["prompt"],
        }
        for number in order
    ]


def uses_image_cues(text: str) -> bool:
    return parse_image_script(text) is not None


def image_prompt_map(text: str) -> Dict[int, str]:
    parsed = parse_image_script(text)
    if not parsed:
        return {}
    return {
        int(row["id"]): str(row.get("prompt") or "")
        for row in parsed
        if str(row.get("prompt") or "").strip()
    }


def split_scenes(text: str) -> List[dict]:
    """Image cues become one scene each. Plain text stays one paragraph each."""
    image_scenes = parse_image_script(text)
    if image_scenes is not None:
        return [
            {"id": int(row["id"]), "text": str(row.get("text") or "")}
            for row in image_scenes
        ]
    return SceneSplitter(min_sentence_length=MIN_SCENE_CHARS).split_into_scenes(
        text or "",
        method="paragraph",
    )


def add_narration(project: str, language: str, docx_path: str) -> str:
    """Store one language from a Word file on an episode that already exists.

    Picture scenes, stills, and the other language stay as they are.
    Italian is the narration that owns those scenes once it has been split.
    """
    if not is_sleepy_project(project):
        raise ValueError(
            "That folder is not a Sleepy episode. "
            "Create one here. Main projects stay on the Main tab."
        )
    language = normalize_language(language)
    text = read_docx_narration(docx_path)
    _require_scenes(text, language)
    write_text(narration_path(project, language), text)
    shutil.copy2(
        os.path.abspath(docx_path),
        os.path.join(project, "input", f"narration_{language_suffix(language)}.docx"),
    )
    return text


def align_narration_to_scenes(
    text: str,
    picture_scenes: Sequence[dict],
    language: str,
) -> List[dict]:
    """Speak a later language on the scene ids the pictures already use."""
    language = normalize_language(language)
    spoken = split_scenes(text)
    pictures = list(picture_scenes or [])
    if len(spoken) != len(pictures):
        raise ValueError(
            f"{language} has {len(spoken)} scenes and the episode has "
            f"{len(pictures)} picture scenes. The pictures stay on the original "
            "scenes. Match the scene count before speaking this language. "
            "An image script uses one scene per [IMG] cue."
        )
    return [
        {"id": int(picture["id"]), "text": str(spoken_row["text"])}
        for picture, spoken_row in zip(pictures, spoken)
    ]


def scene_counts(italian_text: str, english_text: str) -> Tuple[int, int]:
    italian = split_scenes(italian_text) if str(italian_text or "").strip() else []
    english = split_scenes(english_text) if str(english_text or "").strip() else []
    return len(italian), len(english)


def load_scenes(project: str) -> List[dict]:
    data = _read_yaml(scenes_path(project))
    scenes = data.get("scenes") or []
    if not isinstance(scenes, list):
        return []
    cleaned = []
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        try:
            scene_id = int(scene.get("id"))
        except (TypeError, ValueError):
            continue
        cleaned.append({"id": scene_id, "text": str(scene.get("text") or "")})
    return cleaned


def stills_for_scenes(
    scenes: Sequence[dict],
    stills: Sequence[dict],
    script_text: str = "",
) -> List[dict]:
    """One still per scene. A prompt already typed is kept.

    Empty stills take the English prompt written under that image cue.
    """
    prompts = image_prompt_map(script_text)
    aligned = align_stills(scenes, stills)
    if not prompts:
        return aligned
    filled = []
    for row in aligned:
        prompt = str(row.get("prompt") or "")
        if int(row["beat"]) == 1 and not prompt.strip():
            scripted = prompts.get(int(row["scene_id"]), "")
            if scripted:
                prompt = scripted
        filled.append({
            "scene_id": int(row["scene_id"]),
            "beat": int(row["beat"]),
            "prompt": prompt,
        })
    return filled


def publish_scenes(
    project: str,
    language: str,
    text: str,
    stills: Sequence[dict] | None = None,
) -> List[dict]:
    """Write scenes from one language and mirror that text to narration.txt.

    Image cues also fill empty still prompts. A prompt already stored for
    that scene is left as it was.
    """
    language = normalize_language(language)
    scenes = split_scenes(text)
    if not scenes:
        raise ValueError(
            "No scenes were produced. Leave a blank line between paragraphs, "
            "or mark each picture with [IMG 01]."
        )
    write_text(narration_path(project, language), text)
    write_text(os.path.join(project, "input", "narration.txt"), text)
    _write_yaml(scenes_path(project), {"scenes": scenes})
    existing = list(stills) if stills is not None else load_stills(project)
    save_stills(project, stills_for_scenes(scenes, existing, text))
    settings = load_episode_settings(project)
    settings["scenes_language"] = language
    settings["language"] = language
    save_episode_settings(project, settings)
    return scenes


def load_stills(project: str) -> List[dict]:
    data = _read_yaml(stills_path(project))
    rows = data.get("stills") or []
    if not isinstance(rows, list):
        return []
    stills = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            scene_id = int(row.get("scene_id"))
            beat = int(row.get("beat"))
        except (TypeError, ValueError):
            continue
        if scene_id <= 0 or beat <= 0:
            continue
        stills.append({
            "scene_id": scene_id,
            "beat": beat,
            "prompt": str(row.get("prompt") or ""),
        })
    stills.sort(key=lambda item: (item["scene_id"], item["beat"]))
    return stills


def save_stills(project: str, stills: Sequence[dict]) -> None:
    rows = []
    for row in stills or []:
        rows.append({
            "scene_id": int(row["scene_id"]),
            "beat": int(row["beat"]),
            "prompt": str(row.get("prompt") or ""),
        })
    rows.sort(key=lambda item: (item["scene_id"], item["beat"]))
    _write_yaml(stills_path(project), {"stills": rows})


def align_stills(scenes: Sequence[dict], stills: Sequence[dict]) -> List[dict]:
    """Keep prompts for scene ids that remain. New scenes get one empty still."""
    grouped: Dict[int, List[dict]] = {}
    for row in stills or []:
        try:
            scene_id = int(row["scene_id"])
            beat = int(row["beat"])
        except (KeyError, TypeError, ValueError):
            continue
        grouped.setdefault(scene_id, []).append({
            "scene_id": scene_id,
            "beat": beat,
            "prompt": str(row.get("prompt") or ""),
        })
    aligned: List[dict] = []
    for scene in scenes or []:
        scene_id = int(scene["id"])
        rows = grouped.get(scene_id) or [{
            "scene_id": scene_id,
            "beat": 1,
            "prompt": "",
        }]
        rows.sort(key=lambda item: item["beat"])
        aligned.extend(rows)
    return aligned


def prompts_missing(stills: Sequence[dict]) -> List[str]:
    missing = []
    for row in stills or []:
        if str(row.get("prompt") or "").strip():
            continue
        missing.append(
            f"Scene {int(row['scene_id']):03d} still {int(row['beat'])}"
        )
    return missing


def build_model_prompts(scenes: Sequence[dict], stills: Sequence[dict]) -> dict:
    """HiDream rows only. Hand text is marked manually_edited."""
    by_scene: Dict[int, List[dict]] = {}
    for row in stills or []:
        prompt = ensure_rome_softly_prompt(str(row.get("prompt") or ""))
        if not prompt:
            continue
        scene_id = int(row["scene_id"])
        beat = int(row["beat"])
        by_scene.setdefault(scene_id, []).append({
            "id": f"scene_{scene_id:03d}_beat_{beat:02d}_hidream",
            "beat": beat,
            "text": prompt,
            "source": "manually_edited",
        })
    payload = {}
    for scene in scenes or []:
        scene_id = int(scene["id"])
        rows = by_scene.get(scene_id) or []
        if not rows:
            continue
        rows.sort(key=lambda item: int(item["beat"]))
        payload[scene_id] = {
            "scene_id": scene_id,
            "models": {"hidream": {"prompts": rows}},
        }
    return payload


def write_model_prompts(project: str, prompts: dict) -> str:
    path = model_prompts_path(project)
    _write_yaml(path, prompts)
    return path


def selections_for_stills(
    stills: Sequence[dict],
    lightbox_dir: str,
) -> Tuple[dict, List[str]]:
    """Map scene id to the single v1 file. Report filenames that are not on disk."""
    selections: Dict[int, List[str]] = {}
    missing: List[str] = []
    ordered = sorted(
        stills or [],
        key=lambda row: (int(row["scene_id"]), int(row["beat"])),
    )
    for row in ordered:
        if not str(row.get("prompt") or "").strip():
            continue
        scene_id = int(row["scene_id"])
        name = filenames_for_offsets(scene_id, int(row["beat"]), [0])[0]
        if os.path.isfile(os.path.join(lightbox_dir, name)):
            selections.setdefault(scene_id, []).append(name)
        else:
            missing.append(name)
    return selections, missing


def write_selections(project: str, selections: dict) -> str:
    path = selections_path(project)
    _write_yaml(path, {int(key): list(names) for key, names in selections.items()})
    return path


def sleepy_pipeline_config(
    seed: int,
    profile_key: str,
    replace: bool = False,
    scene_id: int = 0,
    beat: int = 0,
) -> dict:
    """extra_config for a Sleepy run. This is not saved into Main settings.

    A scene id limits the run to that scene. A beat limits it to one still.
    """
    scene_id = int(scene_id or 0)
    beat = int(beat or 0)
    return {
        "visual_style": "rome_softly",
        "style_preset": "illustration",
        "enabled_image_models": ["hidream"],
        "image_width": CANVAS_WIDTH,
        "image_height": CANVAS_HEIGHT,
        "output_width": FINAL_WIDTH,
        "output_height": FINAL_HEIGHT,
        "seed": int(seed),
        "seed_offsets": [0],
        "hidream_steps": HIDREAM_STEPS,
        "hidream_guidance": HIDREAM_GUIDANCE,
        "hidream_shift": HIDREAM_SHIFT,
        "hidream_sampler": "euler",
        "hidream_scheduler": "normal",
        "clip_engine": "ken_burns",
        "ken_burns_motion": "sleepy",
        "project_profile_key": profile_key or DEFAULT_PROFILE_KEY,
        "final_target_lufs": SLEEPY_TARGET_LUFS,
        "final_true_peak_db": SLEEPY_TRUE_PEAK_DB,
        "lightbox_scene_id": scene_id,
        "lightbox_beat_index": beat,
        "lightbox_model_key": "hidream" if scene_id else "",
        "force_lightbox_update": bool(replace),
        "fps": 24,
    }


def profile_text(profiles: dict, key: str) -> str:
    return str((profiles or {}).get(key) or "")
