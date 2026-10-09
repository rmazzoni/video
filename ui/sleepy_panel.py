"""Sleepy episode environment.

One HiDream model, one seed, no drafts, straight to the final stills.
Italian and English narration use the cloned voice in the voice venv.
Nothing here is written into Main's settings.yaml.
"""

from __future__ import annotations

import os

from PyQt6.QtCore import QObject, QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
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
    align_stills,
    build_model_prompts,
    create_episode,
    ensure_rome_softly_prompt,
    filenames_for_offsets,
    is_sleepy_project,
    load_app_prefs,
    load_episode_settings,
    load_scenes,
    load_stills,
    narration_path,
    normalize_language,
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
    source_config_dir,
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


class SleepyPanel(QWidget):
    """Top-level Sleepy environment. It does not switch the Main project."""

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self._config_dir = controller.config_dir
        self._project = ""
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
        self.inner_tabs.addTab(self._build_voice_tab(), "Voice")
        self.inner_tabs.addTab(self._build_final_tab(), "Final")
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
        self._refresh_recent()

        seed_row = QHBoxLayout()
        seed_row.addWidget(QLabel("Seed"))
        self._seed = QSpinBox()
        self._seed.setRange(0, 2_147_483_647)
        self._seed.setValue(42)
        self._seed.setToolTip("One seed. Final stills use this seed with no neighbours.")
        self._seed.valueChanged.connect(self._on_seed_changed)
        seed_row.addWidget(self._seed)
        seed_row.addWidget(QLabel("Chapter profile"))
        self._profile = QComboBox()
        self._profile.setMinimumWidth(240)
        for key in rome_softly_profile_keys(self._profiles):
            self._profile.addItem(key, key)
        self._profile.setToolTip(
            "Saved with this episode. It reminds you of the period lock. "
            "It is not painted into a prompt you have already written."
        )
        self._profile.currentIndexChanged.connect(self._on_profile_changed)
        seed_row.addWidget(self._profile, 1)
        layout.addLayout(seed_row)

        layout.addWidget(self._heading("Chapter lock"))
        self._profile_view = QPlainTextEdit()
        self._profile_view.setReadOnly(True)
        self._profile_view.setMaximumHeight(110)
        layout.addWidget(self._profile_view)
        self._refresh_profile_preview()

        layout.addWidget(self._heading("What this tab does not do"))
        limits = QLabel(
            "No preview stills, no extra seeds, no other image models, and no Edge TTS. "
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
            "One scene per paragraph. Leave a blank line between scenes. "
            "Italian and English are stored apart. Split the language selected above."
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
        split = QPushButton("Split into scenes")
        split.clicked.connect(self._split)
        self._action_buttons.extend([save, split])
        row.addWidget(save)
        row.addWidget(split)
        row.addStretch(1)
        layout.addLayout(row)
        return page

    def _build_stills_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._heading("Final stills"))
        hint = QLabel(
            "One English HiDream prompt per still. The Rome Softly sentence is added "
            "if you leave it out. Generate paints the final file only: "
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
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)

        row = QHBoxLayout()
        add = QPushButton("Add still")
        add.setToolTip("Another final still for this scene. The scene's narration is shared across its stills.")
        add.clicked.connect(self._add_still)
        remove = QPushButton("Remove still")
        remove.clicked.connect(self._remove_still)
        generate = QPushButton("Generate final stills")
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
            "Ken Burns moves across the one chosen still per beat, then the spoken scenes "
            "are muxed. The finished mix is −20 LUFS with true peak −3 dBTP. "
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
        return str(self._profile.currentData() or DEFAULT_PROFILE_KEY)

    def _set_language(self, language: str) -> None:
        target = normalize_language(language)
        index = self._language.findData(target)
        if index >= 0:
            self._language.setCurrentIndex(index)

    def _set_profile(self, key: str) -> None:
        index = self._profile.findData(key)
        if index < 0:
            self._profile.addItem(key, key)
            index = self._profile.findData(key)
        self._profile.setCurrentIndex(index)

    def _refresh_recent(self) -> None:
        self._recent.blockSignals(True)
        self._recent.clear()
        self._recent.addItem("Recent episodes", "")
        for path in self._prefs.get("recent") or []:
            if is_sleepy_project(path):
                self._recent.addItem(path, path)
        self._recent.blockSignals(False)

    def _refresh_profile_preview(self) -> None:
        self._profile_view.setPlainText(profile_text(self._profiles, self._profile_key()))

    def _on_seed_changed(self, _value: int) -> None:
        if not self._loading:
            self._save_episode_from_form()

    def _on_profile_changed(self, _index: int) -> None:
        self._refresh_profile_preview()
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
        self._counts.setText(
            f"Italian scenes: {italian_count}    English scenes: {english_count}    "
            f"Split language: {scenes_language}    Scenes on disk: {len(self._scenes)}"
        )
        if italian_count and english_count and italian_count != english_count:
            self._counts.setStyleSheet("color:#E7C07A;")
        else:
            self._counts.setStyleSheet("color:#8E8B90;")

    def _create_episode(self) -> None:
        parent = QFileDialog.getExistingDirectory(self, "Folder for the new episode")
        if not parent:
            return
        name, accepted = QInputDialog.getText(self, "Create Sleepy episode", "Episode name:")
        if not accepted or not str(name).strip():
            return
        try:
            project = create_episode(parent, str(name).strip())
        except Exception as exc:
            self._fail(str(exc))
            return
        self._open_path(project)

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
        if self._project and os.path.abspath(self._project) != path:
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
        self._set_profile(str(settings["profile_key"]))
        self._set_language(str(settings["language"]))
        self._loading = False
        self._shown_language = normalize_language(str(settings["language"]))
        self._load_script()
        self._scenes = load_scenes(path)
        stored = load_stills(path)
        self._stills = align_stills(self._scenes, stored) if self._scenes else stored
        self._path_label.setText(path)
        self._final_path.setText(ProjectLayout(path).final_with_audio)
        self._refresh_profile_preview()
        self._update_counts()
        self._rebuild_still_list()
        if announce:
            self._log(f"Episode: {path}")
            self._status.setText("Episode open")

    def _split(self) -> bool:
        if not self._require_project():
            return False
        self._save_script_file()
        self._save_episode_from_form()
        language = self._language_value()
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
        try:
            self._scenes = publish_scenes(self._project, language, self._script.toPlainText())
        except ValueError as exc:
            self._fail(str(exc))
            return False
        self._stills = align_stills(self._scenes, self._stills)
        save_stills(self._project, self._stills)
        self._update_counts()
        self._rebuild_still_list()
        self._log(f"Split {language} into {len(self._scenes)} scenes.")
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
            del self._stills[self._editing_index]
            self._editing_index = None
        if self._project:
            save_stills(self._project, self._stills)
        self._rebuild_still_list()

    def _pipeline_config(self, replace: bool = False) -> dict:
        return sleepy_pipeline_config(int(self._seed.value()), self._profile_key(), replace=replace)

    def _generate(self) -> None:
        if not self._require_project() or self._busy:
            return
        if self.controller.gpu_owner() or self.controller.is_busy():
            self._fail(
                "The GPU is busy. Wait for the current run to finish. "
                "HiDream and the cloned voice do not fit on the card together."
            )
            return
        self._store_prompt()
        if not self._scenes:
            self._fail("Split the script into scenes first.")
            return
        missing = prompts_missing(self._stills)
        if missing:
            self._fail("Write an English prompt for every still first:\n" + "\n".join(missing))
            return
        for row in self._stills:
            row["prompt"] = ensure_rome_softly_prompt(row["prompt"])
        save_stills(self._project, self._stills)
        self._rebuild_still_list()
        prompts = build_model_prompts(self._scenes, self._stills)
        if not prompts:
            self._fail("No stills to paint.")
            return
        ProjectLayout(self._project).ensure_dirs()
        write_model_prompts(self._project, prompts)
        self._log("Wrote HiDream prompts. Generating one final still per beat.")
        self._start_pipeline("final_images", self._pipeline_config(self._replace_stills.isChecked()))

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
        if not self._split():
            return
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
            "scenes": self._scenes,
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
        os.startfile(path)  # noqa: on Windows this opens the file with its app

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
