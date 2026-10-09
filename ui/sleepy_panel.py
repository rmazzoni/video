"""Sleepy episode environment.

One HiDream model, one seed, no drafts, straight to the final stills.
Italian and English narration use the cloned voice in the voice venv.
Nothing here is written into Main's settings.yaml.
"""

from __future__ import annotations

import os

from PyQt6.QtCore import QObject, QThread, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QImage, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from narration.qwen_voice import VoiceCancelled, VoiceRun, synthesize_scenes, validate_request
from prompts.project_profiles import load_project_profiles
from sleepy.chapter import (
    DEFAULT_PROFILE_KEY,
    LANGUAGES,
    add_narration,
    align_narration_to_scenes,
    align_stills,
    build_model_prompts,
    create_episode,
    episode_folder_name,
    ensure_rome_softly_prompt,
    filenames_for_offsets,
    is_sleepy_project,
    lightbox_cards,
    load_app_prefs,
    load_episode_settings,
    load_scenes,
    load_stills,
    narration_path,
    normalize_language,
    parse_image_script,
    profile_text,
    prompts_missing,
    publish_scenes,
    read_text,
    remember_project,
    rome_softly_profile_keys,
    save_app_prefs,
    save_episode_settings,
    save_stills,
    scene_counts,
    selections_for_stills,
    sleepy_pipeline_config,
    still_file_path,
    stills_for_scenes,
    source_config_dir,
    uses_image_cues,
    write_model_prompts,
    write_selections,
    write_text,
)
from utilis.project_paths import ProjectLayout

_GPU_OWNER = "sleepy-voice"


class _VoiceWorker(QObject):
    progress = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, kwargs: dict, voice_run: VoiceRun):
        super().__init__()
        self._kwargs = kwargs
        self._voice_run = voice_run

    def run(self) -> None:
        try:
            synthesize_scenes(
                on_progress=self.progress.emit,
                voice_run=self._voice_run,
                **self._kwargs,
            )
            self.finished.emit(True, "Voice finished.")
        except VoiceCancelled as exc:
            self.finished.emit(False, str(exc))
        except Exception as exc:
            self.finished.emit(False, str(exc))


class _StillPreview(QLabel):
    """Shows the painted still for the prompt that is open."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(320, 180)
        self.setStyleSheet(
            "background:#1D1B20; color:#B7B3B8; border:1px solid #3A3640;"
        )
        self._path = ""
        self._source = QPixmap()
        self._painting = False
        self.setText("Select a still to see the painted image.")

    def show_path(self, path: str) -> None:
        self._path = path or ""
        image = QImage(self._path) if self._path and os.path.isfile(self._path) else QImage()
        self._source = QPixmap.fromImage(image) if not image.isNull() else QPixmap()
        self._paint()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._paint()

    def _paint(self) -> None:
        if self._painting:
            return
        self._painting = True
        try:
            if self._source.isNull():
                self.setPixmap(QPixmap())
                if not self._path:
                    self.setText("Select a still to see the painted image.")
                elif not os.path.isfile(self._path):
                    self.setText("Not painted yet.\n" + os.path.basename(self._path))
                else:
                    self.setText("The still file could not be read.")
                return
            target = self.contentsRect().size()
            if target.width() < 2 or target.height() < 2:
                return
            scaled = self._source.scaled(
                target,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.setText("")
            self.setPixmap(scaled)
        finally:
            self._painting = False


class _EpisodeIntakeDialog(QDialog):
    """Name, folder, Italian Word file, and this episode's chapter lock."""

    def __init__(self, parent=None, initial_folder: str = "", profiles=None):
        super().__init__(parent)
        self.setWindowTitle("Create Sleepy episode")
        self.setMinimumWidth(640)
        self._initial_folder = initial_folder or ""
        self.setStyleSheet(
            "QDialog { background:#0F0D13; color:#E8E4EA; }"
            "QLabel { color:#E8E4EA; }"
            "QLineEdit, QComboBox, QPlainTextEdit { background:#1D1B20; color:#E8E4EA; "
            "border:1px solid #3A3640; padding:4px; }"
            "QComboBox QAbstractItemView { background:#1D1B20; color:#E8E4EA; }"
            "QPushButton { background:#1D1B20; color:#E8E4EA; "
            "border:1px solid #3A3640; padding:4px 10px; }"
            "QPushButton:hover { background:#2A282F; }"
        )
        layout = QVBoxLayout(self)
        hint = QLabel(
            "Create this episode from the Italian Word file. "
            "Each body paragraph becomes one picture scene. Headings are left out. "
            "English is added later from the Script tab. "
            "The chapter lock below is saved with this episode only."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._name = QLineEdit()
        self._folder = QLineEdit(self._initial_folder)
        self._italian = QLineEdit()
        self._italian.setPlaceholderText("Italian Word file for this episode")
        self._profiles = profiles or {}
        self._profile = QComboBox()
        for key in rome_softly_profile_keys(self._profiles):
            self._profile.addItem(key, key)
        self._lock = QPlainTextEdit()
        self._lock.setReadOnly(True)
        self._lock.setMaximumHeight(110)
        self._profile.currentIndexChanged.connect(self._refresh_lock)
        self._refresh_lock()
        layout.addLayout(self._labeled_row("Episode name", self._name))
        name_hint = QLabel(
            'A folder name cannot contain < > : " / \\ | ? *. '
            "A colon in the title is saved as a hyphen."
        )
        name_hint.setWordWrap(True)
        layout.addWidget(name_hint)
        layout.addLayout(self._path_row(
            "Folder", self._folder, "Choose folder", self._browse_folder,
        ))
        layout.addLayout(self._path_row(
            "Italian narration", self._italian, "Italian .docx",
            lambda _checked=False: self._browse_docx(self._italian, "Italian narration"),
        ))
        layout.addLayout(self._labeled_row("Chapter lock", self._profile))
        lock_label = QLabel("Chapter lock for this episode")
        lock_label.setStyleSheet("color:#D7B58A;")
        layout.addWidget(lock_label)
        layout.addWidget(self._lock)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Create")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _labeled_row(self, label: str, field: QLineEdit) -> QHBoxLayout:
        row = QHBoxLayout()
        name = QLabel(label)
        name.setMinimumWidth(140)
        row.addWidget(name)
        row.addWidget(field, 1)
        return row

    def _path_row(self, label: str, field: QLineEdit, button_text: str, slot) -> QHBoxLayout:
        row = self._labeled_row(label, field)
        button = QPushButton(button_text)
        button.clicked.connect(slot)
        row.addWidget(button)
        return row

    def _browse_folder(self, _checked: bool = False) -> None:
        start = self._folder.text().strip() or self._initial_folder
        folder = QFileDialog.getExistingDirectory(
            self, "Folder for the new episode", start,
        )
        if folder:
            self._folder.setText(folder)

    def _browse_docx(self, field: QLineEdit, title: str) -> None:
        start = self._folder.text().strip() or self._initial_folder
        path, _selected = QFileDialog.getOpenFileName(
            self, title, start, "Word (*.docx)",
        )
        if not path:
            return
        field.setText(path)
        if not self._name.text().strip():
            stem = os.path.splitext(os.path.basename(path))[0]
            try:
                stem = episode_folder_name(stem)
            except ValueError:
                pass
            self._name.setText(stem)

    def _refresh_lock(self, _index: int = 0) -> None:
        key = str(self._profile.currentData() or "")
        self._lock.setPlainText(profile_text(self._profiles, key))

    def accept(self) -> None:
        folder = self._folder.text().strip()
        try:
            episode_name = episode_folder_name(self._name.text())
        except ValueError as exc:
            QMessageBox.warning(self, "Create episode", str(exc))
            return
        self._name.setText(episode_name)
        if not folder or not os.path.isdir(folder):
            QMessageBox.warning(
                self, "Create episode",
                "Choose the folder that will hold the episode.",
            )
            return
        italian = self._italian.text().strip()
        if italian:
            if os.path.splitext(italian)[1].lower() != ".docx":
                QMessageBox.warning(
                    self, "Create episode",
                    "Save the narration as a .docx file. Older .doc files are not read.",
                )
                return
            if not os.path.isfile(italian):
                QMessageBox.warning(
                    self, "Create episode",
                    "The Italian Word file was not found.",
                )
                return
        super().accept()

    def values(self) -> tuple:
        return (
            self._name.text().strip(),
            self._folder.text().strip(),
            self._italian.text().strip(),
            str(self._profile.currentData() or DEFAULT_PROFILE_KEY),
        )


class SleepyPanel(QWidget):
    """Top-level Sleepy environment. It does not switch the Main project."""

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self._config_dir = controller.config_dir
        self._project = ""
        self._episode_profile = ""
        self._prefs = load_app_prefs(self._config_dir)
        self._profiles = {}
        try:
            self._profiles = load_project_profiles(source_config_dir())
        except Exception:
            self._profiles = {}
        self._scenes: list = []
        self._stills: list = []
        self._shown_language = "Italian"
        self._editing_index = None
        self._loading = False
        self._busy = False
        self._sleepy_stage = ""
        self._then: list = []
        self._voice_run: VoiceRun | None = None
        self._voice_thread: QThread | None = None
        self._voice_worker: _VoiceWorker | None = None
        self._action_buttons: list = []
        self._lightbox_frames: list = []

        self._build_ui()
        self.controller.pipeline_started.connect(self._on_pipeline_started)
        self.controller.pipeline_progress.connect(self._on_pipeline_progress)
        self.controller.pipeline_log.connect(self._on_pipeline_log)
        self.controller.pipeline_finished.connect(self._on_pipeline_finished)

        last = str(self._prefs.get("project_path") or "")
        if is_sleepy_project(last):
            self._open_path(last, announce=False)

    def save_all(self) -> None:
        """Save the script, still prompts, and episode settings."""
        if not self._project:
            return
        self._save_script_file()
        self._store_prompt()
        save_stills(self._project, self._stills)
        self._save_episode_from_form()
        self._save_voice_prefs()
        self._log("Saved.")
        self._status.setText("Saved")

    def shutdown(self) -> None:
        self._then = []
        self._sleepy_stage = ""
        self._stop_voice()
        if self._project:
            try:
                self._store_prompt()
                save_stills(self._project, self._stills)
                self._save_script_file()
            except Exception:
                pass
            self.controller.cancel_owned(self._project)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        top = QHBoxLayout()
        lang_label = QLabel("Language")
        lang_label.setStyleSheet("color:#D7B58A; font-weight:bold;")
        top.addWidget(lang_label)
        self._language = QComboBox()
        for language in LANGUAGES:
            self._language.addItem(language, language)
        self._language.setToolTip("Script and cloned voice use this language. Stills stay in English.")
        self._language.currentIndexChanged.connect(self._on_language_changed)
        top.addWidget(self._language)
        self._path_label = QLabel("No Sleepy episode open")
        self._path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        top.addWidget(self._path_label, 1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self._cancel_work)
        top.addWidget(cancel)
        root.addLayout(top)

        self.inner_tabs = QTabWidget()
        self.inner_tabs.tabBar().setObjectName("sleepyTabBar")
        self.inner_tabs.addTab(self._build_episode_tab(), "Episode")
        self.inner_tabs.addTab(self._build_script_tab(), "Script")
        self.inner_tabs.addTab(self._build_stills_tab(), "Stills")
        self.inner_tabs.addTab(self._build_lightbox_tab(), "Lightbox")
        self.inner_tabs.addTab(self._build_voice_tab(), "Voice")
        self.inner_tabs.addTab(self._build_final_tab(), "Final")
        self.inner_tabs.currentChanged.connect(self._on_inner_tab)
        root.addWidget(self.inner_tabs, 1)

        self._progress = QProgressBar()
        self._progress.setValue(0)
        root.addWidget(self._progress)
        self._status = QLabel("Create or open a Sleepy episode.")
        root.addWidget(self._status)
        self._log_view = QPlainTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setMaximumHeight(120)
        root.addWidget(self._log_view)

    def _heading(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("color:#D7B58A; font-weight:bold; font-size:13px;")
        return label

    def _build_episode_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._heading("Episode"))
        note = QLabel(
            "HiDream only  ·  Rome Softly  ·  1344×768  ·  one seed  ·  "
            "no drafts  ·  straight to final  ·  Ken Burns 1920×1080  ·  "
            "mix −20 LUFS / −3 dBTP"
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        row = QHBoxLayout()
        create = QPushButton("Create episode")
        create.clicked.connect(self._create_episode)
        open_btn = QPushButton("Open episode")
        open_btn.clicked.connect(self._browse_episode)
        self._action_buttons.extend([create, open_btn])
        row.addWidget(create)
        row.addWidget(open_btn)
        row.addWidget(QLabel("Recent"))
        self._recent = QComboBox()
        self._recent.setMinimumWidth(280)
        self._recent.activated.connect(self._on_recent)
        row.addWidget(self._recent, 1)
        layout.addLayout(row)
        intake = QLabel(
            "Create asks for the Italian Word file and the chapter lock for that episode. "
            "Add the English Word file afterwards from the Script tab."
        )
        intake.setWordWrap(True)
        layout.addWidget(intake)
        self._refresh_recent()

        seed_row = QHBoxLayout()
        seed_row.addWidget(QLabel("Seed for this episode"))
        self._seed = QSpinBox()
        self._seed.setRange(0, 2_147_483_647)
        self._seed.setValue(42)
        self._seed.setToolTip("One seed for this episode. Final stills use it with no neighbours.")
        self._seed.valueChanged.connect(self._on_seed_changed)
        seed_row.addWidget(self._seed)
        seed_row.addStretch(1)
        layout.addLayout(seed_row)

        layout.addWidget(self._heading("Chapter lock for this episode"))
        self._profile_name = QLabel("No episode open")
        layout.addWidget(self._profile_name)
        self._profile_view = QPlainTextEdit()
        self._profile_view.setReadOnly(True)
        self._profile_view.setMaximumHeight(140)
        layout.addWidget(self._profile_view)
        self._refresh_profile_preview()

        layout.addWidget(self._heading("What this tab does not do"))
        limits = QLabel(
            "No extra seeds, no draft variants, no other image models, and no Edge TTS. "
            "The Stills tab shows the painted file. "
            "These settings stay in the episode and in config/sleepy.yaml. "
            "They are not written into Main settings."
        )
        limits.setWordWrap(True)
        layout.addWidget(limits)
        layout.addStretch(1)
        return page

    def _build_script_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._heading("Narration"))
        hint = QLabel(
            "Picture scenes come from the Italian narration. "
            "Benvenuti starts the spoken script. "
            "[IMG 01] [IMMAGINE: ...] is the Lightbox caption, and it is not spoken. "
            "IMG 01 — PROMPT (EN) starts the English still prompt. "
            "Keep that prompt in one paragraph. The blank line after it separates it from the narration. "
            "One [IMG] cue is one scene, about one picture every 75–80 seconds. "
            "A script without those cues still uses one paragraph per scene. "
            "Update Italian Word loads a revised Italian file. "
            "Add the English Word file when the translation is ready. "
            "Neither file moves the pictures until you split again."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self._script = QPlainTextEdit()
        self._script.setPlaceholderText("Paste the narration for the selected language.")
        layout.addWidget(self._script, 1)
        self._counts = QLabel("Split a script to count scenes.")
        self._counts.setWordWrap(True)
        layout.addWidget(self._counts)
        row = QHBoxLayout()
        save = QPushButton("Save script")
        save.clicked.connect(self.save_all)
        update_italian = QPushButton("Update Italian Word")
        update_italian.clicked.connect(self._update_italian_narration)
        add_english = QPushButton("Add English Word")
        add_english.clicked.connect(self._add_english_narration)
        split = QPushButton("Split into scenes")
        split.clicked.connect(self._split)
        self._action_buttons.extend([save, update_italian, add_english, split])
        row.addWidget(save)
        row.addWidget(update_italian)
        row.addWidget(add_english)
        row.addWidget(split)
        row.addStretch(1)
        layout.addLayout(row)
        return page

    def _build_stills_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._heading("Final stills"))
        hint = QLabel(
            "One English HiDream prompt per still. If the style ending is missing, "
            "the flat City palette is added. A prompt that already names a palette "
            "is left as written. Generate this still paints the prompt you are "
            "editing, and the image appears on the right: "
            + filenames_for_offsets(1, 1, [0])[0].replace("scene_001_hidream_b01", "scene_NNN_hidream_bNN")
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        splitter = QSplitter()
        self._still_list = QListWidget()
        self._still_list.currentRowChanged.connect(self._on_still_selected)
        splitter.addWidget(self._still_list)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("Scene narration"))
        self._scene_view = QPlainTextEdit()
        self._scene_view.setReadOnly(True)
        self._scene_view.setMaximumHeight(90)
        right_layout.addWidget(self._scene_view)
        right_layout.addWidget(QLabel("English prompt"))
        self._prompt = QPlainTextEdit()
        self._prompt.setPlaceholderText("Time of day, place, period, and one action. Then the palette.")
        self._prompt.textChanged.connect(self._store_prompt)
        right_layout.addWidget(self._prompt, 1)
        generate_one = QPushButton("Generate this still")
        generate_one.setToolTip(
            "Paint the prompt in this box. Other stills can wait."
        )
        generate_one.clicked.connect(self._generate_current)
        self._action_buttons.append(generate_one)
        right_layout.addWidget(generate_one)
        splitter.addWidget(right)
        self._still_preview = _StillPreview()
        splitter.addWidget(self._still_preview)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 2)
        self._still_list.setMinimumWidth(180)
        layout.addWidget(splitter, 1)

        row = QHBoxLayout()
        add = QPushButton("Add still")
        add.setToolTip("Another final still for this scene. The scene's narration is shared across its stills.")
        add.clicked.connect(self._add_still)
        remove = QPushButton("Remove still")
        remove.clicked.connect(self._remove_still)
        generate = QPushButton("Generate final stills")
        generate.setToolTip("Paint every still that already has a prompt.")
        generate.clicked.connect(self._generate)
        self._replace_stills = QCheckBox("Replace existing stills")
        self._action_buttons.extend([add, remove, generate])
        row.addWidget(add)
        row.addWidget(remove)
        row.addWidget(generate)
        row.addWidget(self._replace_stills)
        row.addStretch(1)
        layout.addLayout(row)
        return page

    def _build_lightbox_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._heading("Lightbox"))
        note = QLabel(
            "One card per picture. The caption is the [IMMAGINE] line from the script. "
            "The card stays empty until that still is painted. "
            "Click a painted image to see it larger. Previous and Next step through the painted stills."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        row = QHBoxLayout()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self._refresh_lightbox)
        self._action_buttons.append(refresh)
        self._lightbox_status = QLabel("Open an episode to see its stills.")
        self._lightbox_status.setWordWrap(True)
        row.addWidget(refresh)
        row.addWidget(self._lightbox_status, 1)
        layout.addLayout(row)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._lightbox_host = QWidget()
        self._lightbox_layout = QVBoxLayout(self._lightbox_host)
        self._lightbox_layout.addStretch(1)
        scroll.setWidget(self._lightbox_host)
        layout.addWidget(scroll, 1)
        return page

    def _build_voice_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._heading("Cloned voice"))
        note = QLabel(
            "Qwen3-TTS 1.7B-Base, in the voice environment, for Italian and English. "
            "Both languages use your reference clip. Speak does nothing until that clip "
            "and its transcript are set. A checkpoint folder is optional and empty until you train one. "
            "Do not generate stills while the voice is loaded."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        ref_row = QHBoxLayout()
        ref_row.addWidget(QLabel("Reference clip"))
        self._ref_path = QLineEdit()
        self._ref_path.setPlaceholderText("Your recording, wav or mp3")
        self._ref_path.setText(str(self._prefs.get("reference_wav") or ""))
        ref_row.addWidget(self._ref_path, 1)
        browse_ref = QPushButton("Browse")
        browse_ref.clicked.connect(self._browse_ref)
        ref_row.addWidget(browse_ref)
        layout.addLayout(ref_row)

        layout.addWidget(QLabel("Transcript of that clip, word for word"))
        self._ref_text = QPlainTextEdit()
        self._ref_text.setPlaceholderText("The exact words spoken in the reference clip.")
        self._ref_text.setPlainText(str(self._prefs.get("reference_transcript") or ""))
        self._ref_text.setMaximumHeight(80)
        layout.addWidget(self._ref_text)

        ckpt_row = QHBoxLayout()
        ckpt_row.addWidget(QLabel("Checkpoint"))
        self._checkpoint = QLineEdit()
        self._checkpoint.setPlaceholderText("Empty uses Qwen3-TTS-12Hz-1.7B-Base")
        self._checkpoint.setText(str(self._prefs.get("checkpoint") or ""))
        ckpt_row.addWidget(self._checkpoint, 1)
        browse_ckpt = QPushButton("Browse")
        browse_ckpt.clicked.connect(self._browse_checkpoint)
        ckpt_row.addWidget(browse_ckpt)
        layout.addLayout(ckpt_row)

        row = QHBoxLayout()
        speak = QPushButton("Speak this language")
        speak.clicked.connect(self._speak)
        self._replace_voice = QCheckBox("Speak again")
        self._replace_voice.setToolTip("Replace scene audio even when the text has not changed.")
        self._action_buttons.append(speak)
        row.addWidget(speak)
        row.addWidget(self._replace_voice)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(1)
        return page

    def _build_final_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._heading("Final video"))
        note = QLabel(
            "Each still drifts for the whole scene: a slow pan and zoom of about 3–5%, "
            "so the picture keeps moving and the phone display stays awake. "
            "The finished mix is −20 LUFS with true peak −3 dBTP. "
            "Only the single-seed stills are edited in."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self._final_path = QLabel("Open an episode to see the final video path.")
        self._final_path.setWordWrap(True)
        self._final_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._final_path)
        row = QHBoxLayout()
        make = QPushButton("Make final video")
        make.clicked.connect(self._make_video)
        open_final = QPushButton("Open final video")
        open_final.clicked.connect(self._open_final)
        self._action_buttons.append(make)
        row.addWidget(make)
        row.addWidget(open_final)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(1)
        return page

    def _log(self, message: str) -> None:
        text = str(message or "").strip()
        if text:
            self._log_view.appendPlainText(text)

    def _fail(self, message: str) -> None:
        self._log(message)
        self._status.setText("Needs attention")
        QMessageBox.warning(self, "Sleepy", message)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        for button in self._action_buttons:
            button.setEnabled(not busy)
        self._script.setReadOnly(busy)
        self._prompt.setReadOnly(busy)
        self._language.setEnabled(not busy)

    def _require_project(self) -> bool:
        if self._project and is_sleepy_project(self._project):
            return True
        self._fail("Create or open a Sleepy episode first.")
        return False

    def _language_value(self) -> str:
        return normalize_language(str(self._language.currentData() or "Italian"))

    def _profile_key(self) -> str:
        return str(self._episode_profile or DEFAULT_PROFILE_KEY)

    def _set_language(self, language: str) -> None:
        target = normalize_language(language)
        index = self._language.findData(target)
        if index >= 0:
            self._language.setCurrentIndex(index)

    def _refresh_recent(self) -> None:
        self._recent.blockSignals(True)
        self._recent.clear()
        self._recent.addItem("Recent episodes", "")
        for path in self._prefs.get("recent") or []:
            if is_sleepy_project(path):
                self._recent.addItem(path, path)
        self._recent.blockSignals(False)

    def _refresh_profile_preview(self) -> None:
        if not self._project:
            self._profile_name.setText("No episode open")
            self._profile_view.setPlainText(
                "The chapter lock is chosen when you create an episode. "
                "It is saved with that episode only."
            )
            return
        key = self._profile_key()
        self._profile_name.setText(key)
        self._profile_view.setPlainText(profile_text(self._profiles, key))

    def _on_seed_changed(self, _value: int) -> None:
        if not self._loading:
            self._save_episode_from_form()

    def _save_episode_from_form(self) -> None:
        if not self._project:
            return
        current = load_episode_settings(self._project)
        current["seed"] = int(self._seed.value())
        current["profile_key"] = self._profile_key()
        current["language"] = self._language_value()
        save_episode_settings(self._project, current)

    def _save_voice_prefs(self) -> None:
        self._prefs["reference_wav"] = self._ref_path.text().strip()
        self._prefs["reference_transcript"] = self._ref_text.toPlainText().strip()
        self._prefs["checkpoint"] = self._checkpoint.text().strip()
        if self._project:
            self._prefs = remember_project(self._prefs, self._project)
        save_app_prefs(self._config_dir, self._prefs)

    def _save_script_file(self) -> None:
        if not self._project or not self._shown_language:
            return
        write_text(
            narration_path(self._project, self._shown_language),
            self._script.toPlainText(),
        )

    def _load_script(self) -> None:
        if not self._project:
            self._script.setPlainText("")
            return
        path = narration_path(self._project, self._shown_language)
        self._script.blockSignals(True)
        self._script.setPlainText(read_text(path))
        self._script.blockSignals(False)

    def _on_language_changed(self, _index: int) -> None:
        if self._loading:
            return
        new_language = self._language_value()
        if self._project and self._shown_language and self._shown_language != new_language:
            write_text(
                narration_path(self._project, self._shown_language),
                self._script.toPlainText(),
            )
        self._shown_language = new_language
        self._load_script()
        self._save_episode_from_form()
        self._update_counts()

    def _texts_for_counts(self) -> tuple:
        if not self._project:
            return "", ""
        italian = read_text(narration_path(self._project, "Italian"))
        english = read_text(narration_path(self._project, "English"))
        if self._shown_language == "Italian":
            italian = self._script.toPlainText()
        elif self._shown_language == "English":
            english = self._script.toPlainText()
        return italian, english

    def _update_counts(self) -> None:
        if not self._project:
            self._counts.setText("Split a script to count scenes.")
            return
        italian, english = self._texts_for_counts()
        italian_count, english_count = scene_counts(italian, english)
        scenes_language = load_episode_settings(self._project).get("scenes_language") or "not split"
        again = ""
        if (
            uses_image_cues(italian)
            and self._scenes
            and italian_count
            and italian_count != len(self._scenes)
            and str(scenes_language) == "Italian"
        ):
            again = "    Split again: one scene per image cue."
        self._counts.setText(
            f"Italian scenes: {italian_count}    English scenes: {english_count}    "
            f"Split language: {scenes_language}    Scenes on disk: {len(self._scenes)}"
            f"{again}"
        )
        if italian_count and english_count and italian_count != english_count:
            self._counts.setStyleSheet("color:#E7C07A;")
        else:
            self._counts.setStyleSheet("color:#8E8B90;")

    def _create_episode(self) -> None:
        initial = os.path.dirname(self._project) if self._project else ""
        dialog = _EpisodeIntakeDialog(self, initial, self._profiles)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, parent, italian_docx, profile_key = dialog.values()
        try:
            project = create_episode(
                parent,
                name,
                italian_docx=italian_docx,
                profile_key=profile_key,
            )
        except Exception as exc:
            self._fail(str(exc))
            return
        self._open_path(project)
        if italian_docx:
            italian_count, _english_count = scene_counts(*self._texts_for_counts())
            self._log(
                f"Italian narration stored ({italian_count} scenes). "
                f"Chapter lock for this episode: {profile_key}. "
                "Add the English Word file later from the Script tab."
            )
        else:
            self._log(f"Episode created. Chapter lock for this episode: {profile_key}.")

    def _update_italian_narration(self) -> None:
        if not self._require_project():
            return
        path, _selected = QFileDialog.getOpenFileName(
            self,
            "Italian narration",
            self._project,
            "Word (*.docx)",
        )
        if not path:
            return
        existing = read_text(narration_path(self._project, "Italian"))
        if self._shown_language == "Italian":
            existing = self._script.toPlainText()
        if existing.strip():
            answer = QMessageBox.question(
                self,
                "Replace Italian narration",
                "This episode already has an Italian narration. "
                "Replace it with this Word file?\n\n"
                "The pictures stay as they are until you split again.",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            text = add_narration(self._project, "Italian", path)
        except Exception as exc:
            self._fail(str(exc))
            return
        if self._shown_language == "Italian":
            self._script.blockSignals(True)
            self._script.setPlainText(text)
            self._script.blockSignals(False)
        self._update_counts()
        italian_count, _english_count = scene_counts(*self._texts_for_counts())
        self._log(
            f"Italian narration updated ({italian_count} scenes). "
            "Picture scenes stay until you split again."
        )
        if self._scenes and italian_count != len(self._scenes):
            self._status.setText("Italian updated; split again to use it")
        else:
            self._status.setText("Italian narration updated")

    def _add_english_narration(self) -> None:
        if not self._require_project():
            return
        path, _selected = QFileDialog.getOpenFileName(
            self,
            "English narration",
            self._project,
            "Word (*.docx)",
        )
        if not path:
            return
        existing = read_text(narration_path(self._project, "English"))
        if self._shown_language == "English":
            existing = self._script.toPlainText()
        if existing.strip():
            answer = QMessageBox.question(
                self,
                "Replace English narration",
                "This episode already has an English narration. "
                "Replace it with this Word file?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            text = add_narration(self._project, "English", path)
        except Exception as exc:
            self._fail(str(exc))
            return
        if self._shown_language == "English":
            self._script.blockSignals(True)
            self._script.setPlainText(text)
            self._script.blockSignals(False)
        self._update_counts()
        italian_count, english_count = scene_counts(*self._texts_for_counts())
        self._log(
            f"English narration added ({english_count} scenes). "
            f"Picture scenes stay Italian ({italian_count})."
        )
        if italian_count and english_count and italian_count != english_count:
            self._log(
                "The paragraph counts differ. Match them before speaking English."
            )
            self._status.setText("English added; scene counts differ")
        else:
            self._status.setText("English narration added")

    def _browse_episode(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Open Sleepy episode")
        if folder:
            self._open_path(folder)

    def _on_recent(self, index: int) -> None:
        path = self._recent.itemData(index)
        if path:
            self._open_path(str(path))

    def _open_path(self, path: str, announce: bool = True) -> None:
        path = os.path.abspath(path)
        if not is_sleepy_project(path):
            self._fail(
                "That folder is not a Sleepy episode. "
                "Create one here. Main projects stay on the Main tab."
            )
            return
        if self._project and os.path.abspath(self._project) == path:
            return
        if self._project:
            self._save_script_file()
            self._store_prompt()
            save_stills(self._project, self._stills)
            self._save_episode_from_form()
        self._project = path
        self._prefs = remember_project(self._prefs, path)
        save_app_prefs(self._config_dir, self._prefs)
        self._refresh_recent()
        settings = load_episode_settings(path)
        self._loading = True
        self._seed.setValue(int(settings["seed"]))
        self._episode_profile = str(settings["profile_key"])
        self._set_language(str(settings["language"]))
        self._loading = False
        self._shown_language = normalize_language(str(settings["language"]))
        self._load_script()
        self._scenes = load_scenes(path)
        stored = load_stills(path)
        scene_ids = {int(scene["id"]) for scene in self._scenes}
        stored_ids = {int(row["scene_id"]) for row in stored}
        italian = read_text(narration_path(path, "Italian"))
        # The still file can still list the old paragraph split after the
        # picture scenes were published. Show one row per picture and keep a
        # prompt that was already typed. Do not write here: opening the panel
        # must not change the episode, including when a test opens it.
        if (
            scene_ids
            and stored_ids - scene_ids
            and str(settings.get("scenes_language") or "") == "Italian"
            and uses_image_cues(italian)
        ):
            self._stills = stills_for_scenes(self._scenes, stored, italian)
        else:
            self._stills = align_stills(self._scenes, stored) if self._scenes else stored
        self._path_label.setText(path)
        self._final_path.setText(ProjectLayout(path).final_with_audio)
        self._refresh_profile_preview()
        self._update_counts()
        self._rebuild_still_list()
        if announce:
            self._log(f"Episode: {path}")
            self._status.setText("Episode open")

    def _picture_language(self) -> str:
        if not self._project:
            return ""
        return str(load_episode_settings(self._project).get("scenes_language") or "")

    def _split(self) -> bool:
        if not self._require_project():
            return False
        self._save_script_file()
        self._save_episode_from_form()
        language = self._language_value()
        owner = self._picture_language()
        if owner and owner != language and self._scenes:
            self._update_counts()
            italian_count, english_count = scene_counts(*self._texts_for_counts())
            count = english_count if language == "English" else italian_count
            self._log(
                f"{language} narration saved ({count} scenes). "
                f"Picture scenes stay on the {owner} narration."
            )
            if italian_count and english_count and italian_count != english_count:
                self._status.setText("Narration saved; scene counts differ")
            else:
                self._status.setText(f"{language} narration saved")
            return True
        italian, english = self._texts_for_counts()
        italian_count, english_count = scene_counts(italian, english)
        if italian_count and english_count and italian_count != english_count:
            answer = QMessageBox.question(
                self,
                "Scene counts differ",
                f"Italian splits into {italian_count} scenes and English into {english_count}. "
                "Stills follow scene numbers.\n\n"
                f"Split {language} anyway?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False
        self._store_prompt()
        try:
            self._scenes = publish_scenes(
                self._project,
                language,
                self._script.toPlainText(),
                stills=self._stills,
            )
        except ValueError as exc:
            self._fail(str(exc))
            return False
        self._stills = load_stills(self._project)
        self._update_counts()
        self._rebuild_still_list()
        self._log(f"Split {language} into {len(self._scenes)} scenes.")
        if uses_image_cues(self._script.toPlainText()):
            self._log(
                "Each [IMG] cue is one scene. Empty stills took the English prompt "
                "from the script. A prompt you already typed was left in place."
            )
        self._status.setText(f"{len(self._scenes)} scenes")
        return True

    def _scene_text(self, scene_id: int) -> str:
        for scene in self._scenes:
            if int(scene["id"]) == int(scene_id):
                return str(scene.get("text") or "")
        return ""

    def _store_prompt(self) -> None:
        index = self._editing_index
        if index is None or not (0 <= index < len(self._stills)):
            return
        self._stills[index]["prompt"] = self._prompt.toPlainText()

    def _show_still(self, index) -> None:
        self._editing_index = index
        self._prompt.blockSignals(True)
        self._scene_view.blockSignals(True)
        if index is None or not (0 <= index < len(self._stills)):
            self._prompt.setPlainText("")
            self._scene_view.setPlainText("Split the script, then write one English prompt per still.")
        else:
            still = self._stills[index]
            self._prompt.setPlainText(str(still.get("prompt") or ""))
            self._scene_view.setPlainText(self._scene_text(int(still["scene_id"])))
        self._prompt.blockSignals(False)
        self._scene_view.blockSignals(False)
        self._show_still_image(index)

    def _show_still_image(self, index) -> None:
        if (
            not self._project
            or index is None
            or not (0 <= index < len(self._stills))
        ):
            self._still_preview.show_path("")
            return
        still = self._stills[index]
        self._still_preview.show_path(
            still_file_path(self._project, int(still["scene_id"]), int(still["beat"]))
        )

    def _on_still_selected(self, row: int) -> None:
        if row == self._editing_index:
            return
        self._store_prompt()
        if self._project:
            save_stills(self._project, self._stills)
        self._show_still(row if row >= 0 else None)

    def _rebuild_still_list(self, select=None) -> None:
        chosen = select
        if chosen is None and self._editing_index is not None and 0 <= self._editing_index < len(self._stills):
            current = self._stills[self._editing_index]
            chosen = (int(current["scene_id"]), int(current["beat"]))
        # Drop the editor binding first so a stale text box cannot overwrite memory.
        self._editing_index = None
        self._still_list.blockSignals(True)
        self._still_list.clear()
        for row in self._stills:
            self._still_list.addItem(
                f"Scene {int(row['scene_id']):03d} · still {int(row['beat'])}"
            )
        self._still_list.blockSignals(False)
        if not self._stills:
            self._show_still(None)
            return
        target = 0
        if chosen is not None:
            for index, row in enumerate(self._stills):
                if (int(row["scene_id"]), int(row["beat"])) == chosen:
                    target = index
                    break
        self._editing_index = None
        self._still_list.setCurrentRow(target)

    def _add_still(self) -> None:
        if not self._require_project() or not self._stills:
            if self._project and not self._stills:
                self._fail("Split the script before adding stills.")
            return
        self._store_prompt()
        current = self._stills[self._editing_index or 0]
        scene_id = int(current["scene_id"])
        beat = max(int(row["beat"]) for row in self._stills if int(row["scene_id"]) == scene_id) + 1
        self._stills.append({"scene_id": scene_id, "beat": beat, "prompt": ""})
        self._stills.sort(key=lambda row: (int(row["scene_id"]), int(row["beat"])))
        save_stills(self._project, self._stills)
        self._rebuild_still_list(select=(scene_id, beat))

    def _remove_still(self) -> None:
        if not self._stills or self._editing_index is None:
            return
        self._store_prompt()
        current = self._stills[self._editing_index]
        scene_id = int(current["scene_id"])
        siblings = [row for row in self._stills if int(row["scene_id"]) == scene_id]
        if len(siblings) <= 1:
            current["prompt"] = ""
            self._show_still(self._editing_index)
        else:
            self._discard_still_file(scene_id, int(current["beat"]))
            del self._stills[self._editing_index]
            self._editing_index = None
        if self._project:
            save_stills(self._project, self._stills)
        self._rebuild_still_list()

    def _pipeline_config(self, replace: bool = False, scene_id: int = 0, beat: int = 0) -> dict:
        return sleepy_pipeline_config(
            int(self._seed.value()),
            self._profile_key(),
            replace=replace,
            scene_id=scene_id,
            beat=beat,
        )

    def _on_inner_tab(self, index: int) -> None:
        if self.inner_tabs.tabText(index) == "Lightbox":
            self._refresh_lightbox()

    def _discard_still_file(self, scene_id: int, beat: int) -> None:
        """Remove the painted file for a still that left the list."""
        if not self._project:
            return
        path = still_file_path(self._project, scene_id, beat)
        if not os.path.isfile(path):
            return
        try:
            os.remove(path)
        except OSError:
            self._log(f"Could not remove {os.path.basename(path)}. Close the picture and try again.")

    def _lightbox_scene_rows(self) -> list:
        """Picture cards follow the image cues, with captions from the script."""
        italian = ""
        if self._shown_language == "Italian":
            italian = self._script.toPlainText()
        elif self._project:
            italian = read_text(narration_path(self._project, "Italian"))
        parsed = parse_image_script(italian) if italian else None
        if parsed and (
            not self._scenes
            or [int(scene["id"]) for scene in self._scenes]
            != [int(row["id"]) for row in parsed]
        ):
            return [
                {
                    "id": int(row["id"]),
                    "text": str(row.get("text") or ""),
                    "caption": str(row.get("caption") or ""),
                }
                for row in parsed
            ]
        captions = {
            int(row["id"]): str(row.get("caption") or "")
            for row in (parsed or [])
        }
        rows = []
        for scene in self._scenes:
            row = dict(scene)
            if not str(row.get("caption") or "").strip():
                row["caption"] = captions.get(int(scene["id"]), "")
            rows.append(row)
        return rows

    def _refresh_lightbox(self) -> None:
        while self._lightbox_layout.count() > 1:
            item = self._lightbox_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if not self._project:
            self._lightbox_status.setText("Open an episode to see its stills.")
            return
        scenes = self._lightbox_scene_rows()
        if not scenes:
            self._lightbox_status.setText(
                "Split the script to build one card per picture."
            )
            return
        cards = lightbox_cards(scenes, self._stills, self._project)
        self._lightbox_frames = []
        for card in cards:
            for image in card["images"]:
                if not image["path"]:
                    continue
                self._lightbox_frames.append({
                    "path": str(image["path"]),
                    "scene_id": int(card["scene_id"]),
                    "beat": int(image.get("beat") or 1),
                    "caption": str(card.get("caption") or ""),
                })
        painted = len(self._lightbox_frames)
        self._lightbox_status.setText(f"{len(cards)} pictures. {painted} painted.")
        for card in cards:
            widget = self._lightbox_scene_card(card)
            self._lightbox_layout.insertWidget(self._lightbox_layout.count() - 1, widget)

    def _lightbox_scene_card(self, card: dict) -> QWidget:
        scene_id = int(card["scene_id"])
        widget = QWidget()
        widget.setStyleSheet(
            "background:#1D1B20; border:1px solid #36343B; border-radius:4px;"
        )
        outer = QHBoxLayout(widget)
        outer.setContentsMargins(10, 8, 10, 8)
        number = QLabel(f"{scene_id:03d}")
        number.setFixedWidth(72)
        number.setAlignment(Qt.AlignmentFlag.AlignCenter)
        number.setStyleSheet(
            "color:#D7B58A; font-size:28px; font-weight:bold; "
            "background:transparent; border:none;"
        )
        outer.addWidget(number, 0, Qt.AlignmentFlag.AlignTop)
        pictures = QVBoxLayout()
        pictures.setSpacing(6)
        for image in card["images"]:
            pictures.addWidget(self._lightbox_thumb(image))
        outer.addLayout(pictures, 0)
        caption = QLabel(str(card.get("caption") or ""))
        caption.setWordWrap(True)
        caption.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        caption.setStyleSheet(
            "color:#E8E4EA; background:transparent; border:none;"
        )
        outer.addWidget(caption, 1)
        return widget

    def _lightbox_thumb(self, image: dict) -> QWidget:
        cell = QWidget()
        cell.setStyleSheet("background:transparent; border:none;")
        layout = QVBoxLayout(cell)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        path = str(image.get("path") or "")
        button = QPushButton()
        button.setFixedSize(240, 135)
        if not path:
            button.setText("Not painted yet")
            button.setEnabled(False)
        else:
            picture = QImage(path)
            if picture.isNull():
                button.setText("Unreadable")
            else:
                pixmap = QPixmap.fromImage(picture).scaled(
                    240, 135,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                button.setIcon(QIcon(pixmap))
                button.setIconSize(pixmap.size())
                button.clicked.connect(
                    lambda _checked=False, image_path=path: self._open_still_viewer(image_path)
                )
        layout.addWidget(button)
        beat = int(image.get("beat") or 0)
        label = QLabel(f"Still {beat}" if beat else "")
        label.setStyleSheet(
            "color:#8E8B90; font-size:11px; background:transparent; border:none;"
        )
        layout.addWidget(label)
        return cell

    def _open_still_viewer(self, path: str) -> None:
        frames = list(self._lightbox_frames)
        if not frames or not any(str(frame.get("path") or "") == path for frame in frames):
            frames = self._painted_lightbox_frames()
        dialog = self._build_lightbox_viewer(frames, path)
        dialog.exec()

    def _painted_lightbox_frames(self) -> list:
        """Painted stills in Lightbox order, each with its [IMMAGINE] caption."""
        frames = []
        for card in lightbox_cards(self._lightbox_scene_rows(), self._stills, self._project or ""):
            for image in card["images"]:
                if not image["path"]:
                    continue
                frames.append({
                    "path": str(image["path"]),
                    "scene_id": int(card["scene_id"]),
                    "beat": int(image.get("beat") or 1),
                    "caption": str(card.get("caption") or ""),
                })
        return frames

    def _build_lightbox_viewer(self, frames: list, path: str) -> QDialog:
        """Maximized still with Previous, Next, and the picture caption."""
        frames = [frame for frame in frames if str(frame.get("path") or "")]
        if not any(str(frame.get("path") or "") == path for frame in frames):
            frames.append({
                "path": path,
                "scene_id": 0,
                "beat": 1,
                "caption": "",
            })
        start = 0
        for index, frame in enumerate(frames):
            if str(frame.get("path") or "") == path:
                start = index
                break

        screen = self.screen().availableGeometry() if self.screen() is not None else None
        if screen is None or screen.width() < 200 or screen.height() < 200:
            max_w, max_h = 960, 540
        else:
            max_w = int(screen.width() * 0.88)
            max_h = int(screen.height() * 0.72)

        dialog = QDialog(self)
        dialog.setModal(True)
        dialog.setStyleSheet(
            "QDialog { background:#0F0D13; }"
            "QLabel { color:#E8E4EA; background:transparent; border:none; }"
            "QPushButton { background:#36343B; color:#E8E4EA; border:none;"
            " border-radius:4px; padding:5px 18px; }"
            "QPushButton:disabled { color:#555555; }"
        )
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        image_label = QLabel()
        image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(image_label, 1)

        caption = QLabel()
        caption.setObjectName("lightboxViewerCaption")
        caption.setWordWrap(True)
        caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(caption)

        nav = QHBoxLayout()
        previous = QPushButton("◀  Prev")
        tweak = QPushButton("Tweak Prompt")
        info = QLabel()
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info.setStyleSheet("color:#8E8B90; font-size:11px;")
        nxt = QPushButton("Next  ▶")
        close = QPushButton("Close")
        for button in (previous, tweak, nxt, close):
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        nav.addWidget(previous)
        nav.addWidget(tweak)
        nav.addStretch(1)
        nav.addWidget(info)
        nav.addStretch(1)
        nav.addWidget(nxt)
        nav.addSpacing(12)
        nav.addWidget(close)
        layout.addLayout(nav)

        state = {"idx": start}

        def load(index: int) -> None:
            index = max(0, min(len(frames) - 1, index))
            state["idx"] = index
            frame = frames[index]
            image_path = str(frame.get("path") or "")
            picture = QImage(image_path)
            if picture.isNull():
                image_label.setPixmap(QPixmap())
                image_label.setText("The still file could not be read.")
            else:
                pixmap = QPixmap.fromImage(picture).scaled(
                    max_w,
                    max_h,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                image_label.setText("")
                image_label.setPixmap(pixmap)
            scene_id = int(frame.get("scene_id") or 0)
            beat = int(frame.get("beat") or 1)
            if scene_id:
                dialog.setWindowTitle(f"Scene {scene_id:03d} · still {beat}")
            else:
                dialog.setWindowTitle(os.path.basename(image_path))
            caption.setText(str(frame.get("caption") or ""))
            info.setText(f"{index + 1} / {len(frames)}    ← → to move    Esc to close")
            previous.setEnabled(index > 0)
            nxt.setEnabled(index < len(frames) - 1)
            tweak.setEnabled(int(frame.get("scene_id") or 0) > 0)

        def tweak_prompt() -> None:
            frame = frames[state["idx"]]
            scene_id = int(frame.get("scene_id") or 0)
            beat = int(frame.get("beat") or 1)
            dialog.accept()
            if scene_id:
                self._show_still_on_stills_tab(scene_id, beat)

        previous.clicked.connect(lambda: load(state["idx"] - 1))
        tweak.clicked.connect(tweak_prompt)
        nxt.clicked.connect(lambda: load(state["idx"] + 1))
        close.clicked.connect(dialog.accept)

        def on_key(event) -> None:
            key = event.key()
            if key in (Qt.Key.Key_Right, Qt.Key.Key_Down):
                load(state["idx"] + 1)
            elif key in (Qt.Key.Key_Left, Qt.Key.Key_Up):
                load(state["idx"] - 1)
            elif key == Qt.Key.Key_Escape:
                dialog.accept()
            else:
                QDialog.keyPressEvent(dialog, event)

        dialog.keyPressEvent = on_key
        load(start)
        return dialog

    def _show_still_on_stills_tab(self, scene_id: int, beat: int) -> None:
        """Leave the Lightbox viewer on this still's prompt in the Stills tab."""
        for index in range(self.inner_tabs.count()):
            if self.inner_tabs.tabText(index) == "Stills":
                self.inner_tabs.setCurrentIndex(index)
                break
        target = None
        for index, row in enumerate(self._stills):
            if int(row["scene_id"]) == int(scene_id) and int(row["beat"]) == int(beat):
                target = index
                break
        if target is None:
            return
        if self._still_list.currentRow() == target:
            self._show_still(target)
        else:
            self._still_list.setCurrentRow(target)
        self._still_list.scrollToItem(self._still_list.item(target))
        self._prompt.setFocus()

    def _gpu_is_free(self) -> bool:
        if not (self.controller.gpu_owner() or self.controller.is_busy()):
            return True
        self._fail(
            "The GPU is busy. Wait for the current run to finish. "
            "HiDream and the cloned voice do not fit on the card together."
        )
        return False

    def _write_prompts_for_paint(self) -> bool:
        prompts = build_model_prompts(self._scenes, self._stills)
        if not prompts:
            self._fail("Write an English prompt for the still you want to paint.")
            return False
        ProjectLayout(self._project).ensure_dirs()
        write_model_prompts(self._project, prompts)
        return True

    def _generate_current(self) -> None:
        if not self._require_project() or self._busy or not self._gpu_is_free():
            return
        self._store_prompt()
        if not self._scenes:
            self._fail("Split the script into scenes first.")
            return
        index = self._editing_index
        if index is None or not (0 <= index < len(self._stills)):
            self._fail("Select a still, then write its English prompt.")
            return
        prompt = ensure_rome_softly_prompt(str(self._stills[index].get("prompt") or ""))
        if not prompt:
            self._fail("Write the English prompt for this still first.")
            return
        self._stills[index]["prompt"] = prompt
        self._prompt.blockSignals(True)
        self._prompt.setPlainText(prompt)
        self._prompt.blockSignals(False)
        save_stills(self._project, self._stills)
        if not self._write_prompts_for_paint():
            return
        still = self._stills[index]
        scene_id = int(still["scene_id"])
        beat = int(still["beat"])
        self._log(f"Painting scene {scene_id:03d} still {beat}.")
        self._start_pipeline(
            "final_images",
            self._pipeline_config(replace=True, scene_id=scene_id, beat=beat),
        )

    def _generate(self) -> None:
        if not self._require_project() or self._busy or not self._gpu_is_free():
            return
        self._store_prompt()
        if not self._scenes:
            self._fail("Split the script into scenes first.")
            return
        ready = 0
        for row in self._stills:
            text = str(row.get("prompt") or "").strip()
            if not text:
                continue
            row["prompt"] = ensure_rome_softly_prompt(text)
            ready += 1
        if not ready:
            self._fail("Write an English prompt for the still you want to paint.")
            return
        missing = prompts_missing(self._stills)
        save_stills(self._project, self._stills)
        self._rebuild_still_list()
        if not self._write_prompts_for_paint():
            return
        if missing:
            self._log("Left for later: " + ", ".join(missing))
        self._log(f"Painting {ready} still(s).")
        self._start_pipeline(
            "final_images",
            self._pipeline_config(self._replace_stills.isChecked()),
        )

    def _browse_ref(self) -> None:
        path, _selected = QFileDialog.getOpenFileName(
            self,
            "Reference clip",
            "",
            "Audio (*.wav *.mp3 *.flac *.m4a);;All files (*.*)",
        )
        if path:
            self._ref_path.setText(path)
            self._save_voice_prefs()

    def _browse_checkpoint(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Voice checkpoint folder")
        if folder:
            self._checkpoint.setText(folder)
            self._save_voice_prefs()

    def _speak(self) -> None:
        if not self._require_project() or self._busy:
            return
        self._save_script_file()
        language = self._language_value()
        owner = self._picture_language()
        if owner and owner != language and self._scenes:
            try:
                voice_scenes = align_narration_to_scenes(
                    self._script.toPlainText(),
                    self._scenes,
                    language,
                )
            except ValueError as exc:
                self._update_counts()
                self._fail(str(exc))
                return
        else:
            if not self._split():
                return
            voice_scenes = self._scenes
        self._save_voice_prefs()
        checkpoint = self._checkpoint.text().strip()
        try:
            validate_request(
                self._language_value(),
                self._ref_path.text().strip(),
                self._ref_text.toPlainText().strip(),
                checkpoint or None,
            )
        except Exception as exc:
            self._fail(str(exc))
            return
        if not self.controller.reserve_gpu(_GPU_OWNER):
            owner = self.controller.gpu_owner() or "a pipeline run"
            self._fail(
                f"The GPU is busy ({owner}). Wait until it is free. "
                "HiDream and the cloned voice do not run together."
            )
            return
        layout = ProjectLayout(self._project)
        layout.ensure_dirs()
        self._voice_run = VoiceRun()
        worker = _VoiceWorker({
            "scenes": voice_scenes,
            "output_dir": layout.audio,
            "timings_path": os.path.join(layout.audio, "timings.yaml"),
            "language": self._language_value(),
            "ref_audio": self._ref_path.text().strip(),
            "ref_text": self._ref_text.toPlainText().strip(),
            "model_dir": checkpoint or None,
            "seed": int(self._seed.value()),
            "replace_existing": self._replace_voice.isChecked(),
        }, self._voice_run)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_voice_progress)
        worker.finished.connect(self._on_voice_finished)
        worker.finished.connect(thread.quit)
        thread.finished.connect(self._clear_voice)
        self._voice_worker = worker
        self._voice_thread = thread
        self._set_busy(True)
        self._status.setText("Loading the cloned voice…")
        self._log(f"Speaking {self._language_value()} with the cloned voice.")
        thread.start()

    def _on_voice_progress(self, message: str) -> None:
        self._status.setText(message)
        self._log(message)

    def _on_voice_finished(self, ok: bool, message: str) -> None:
        self.controller.release_gpu(_GPU_OWNER)
        self._set_busy(False)
        self._log(message)
        if ok:
            self._status.setText("Voice finished")
            self._progress.setValue(100)
            return
        if "cancel" in message.lower():
            self._status.setText("Voice cancelled")
            return
        self._status.setText("Voice failed")
        QMessageBox.critical(self, "Voice failed", message)

    def _clear_voice(self) -> None:
        self._voice_worker = None
        self._voice_thread = None
        self._voice_run = None

    def _stop_voice(self) -> None:
        run = self._voice_run
        if run is not None:
            run.stop()
        self.controller.release_gpu(_GPU_OWNER)

    def _write_selection_files(self) -> tuple:
        layout = ProjectLayout(self._project)
        layout.ensure_dirs()
        selections, missing = selections_for_stills(self._stills, layout.lightbox)
        write_selections(self._project, selections)
        return selections, missing

    def _make_video(self) -> None:
        if not self._require_project() or self._busy:
            return
        if self.controller.gpu_owner():
            self._fail("The cloned voice is using the GPU. Wait until it finishes.")
            return
        if not self._scenes:
            self._fail("Split the script into scenes first.")
            return
        _selections, missing = self._write_selection_files()
        if missing or not _selections:
            self._fail(
                "Generate the final stills first. Missing:\n" + "\n".join(missing or ["no stills"])
            )
            return
        layout = ProjectLayout(self._project)
        spoken = []
        if os.path.isdir(layout.audio):
            spoken = [
                name for name in os.listdir(layout.audio)
                if name.startswith("scene_") and name.endswith(".mp3")
            ]
        if not spoken:
            self._fail("Speak the chapter first. The final video needs one audio file per scene.")
            return
        self._log(f"Editing {sum(len(names) for names in _selections.values())} still(s) into the final video.")
        self._start_pipeline("final_clips", self._pipeline_config(), then=["final_video"])

    def _open_final(self) -> None:
        if not self._require_project():
            return
        path = ProjectLayout(self._project).final_with_audio
        if not os.path.isfile(path):
            self._fail(f"No final video yet.\n{path}")
            return
        os.startfile(path)

    def _start_pipeline(self, stage: str, config: dict, then=None) -> None:
        self._then = list(then or [])
        self._sleepy_stage = stage
        self._set_busy(True)
        self._progress.setValue(0)
        was_busy = self.controller.is_busy()
        self._status.setText(stage)
        self.controller.run_pipeline(stage, config, project_path=self._project)
        if was_busy and self._sleepy_stage:
            self._status.setText("Queued behind the running pipeline.")

    def _on_pipeline_started(self) -> None:
        if self._ours_running():
            self._progress.setValue(0)

    def _on_pipeline_progress(self, value: int, message: str) -> None:
        if not self._ours_running():
            return
        self._progress.setValue(value)
        self._status.setText(message)

    def _on_pipeline_log(self, message: str) -> None:
        if self._ours_running():
            self._log(message)

    def _ours_running(self) -> bool:
        worker = self.controller._worker
        if not self._sleepy_stage or worker is None or not self._project:
            return False
        return os.path.abspath(worker.project_path) == os.path.abspath(self._project)

    def _on_pipeline_finished(self, ok: bool, payload: str) -> None:
        if not self._sleepy_stage:
            return
        worker = self.controller._worker
        ours = (
            worker is not None
            and self._project
            and os.path.abspath(worker.project_path) == os.path.abspath(self._project)
        )
        if not ours:
            if worker is None and not ok:
                self._sleepy_stage = ""
                self._then = []
                self._set_busy(False)
                self._log(payload)
                self._status.setText("Failed")
            return
        stage = self._sleepy_stage
        if stage == "final_images":
            self._show_still_image(self._editing_index)
            self._refresh_lightbox()
        if not ok:
            self._sleepy_stage = ""
            self._then = []
            self._set_busy(False)
            self._log(payload)
            self._status.setText("Cancelled" if "cancel" in str(payload).lower() else "Failed")
            return
        if stage == "final_images":
            _selections, missing = self._write_selection_files()
            count = sum(len(names) for names in _selections.values())
            self._log(f"Final selections: {count} still(s).")
            if missing:
                self._log("Missing stills: " + ", ".join(missing))
        if self._then:
            next_stage = self._then.pop(0)
            self._sleepy_stage = next_stage
            self._status.setText(next_stage)
            self.controller.run_pipeline(
                next_stage,
                self._pipeline_config(),
                project_path=self._project,
            )
            return
        self._sleepy_stage = ""
        self._set_busy(False)
        self._progress.setValue(100)
        self._status.setText("Done")
        if payload:
            self._log(f"Finished: {payload}")

    def _cancel_work(self) -> None:
        self._then = []
        self._stop_voice()
        if self._project and self._sleepy_stage:
            self.controller.cancel_owned(self._project)
            self._status.setText("Cancelling…")
            self._log("Cancel requested.")
