import os
import sys
from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QFileDialog,
    QLineEdit,
    QComboBox,
    QProgressBar,
    QPlainTextEdit,
    QTabWidget,
    QFormLayout,
    QSpinBox,
    QDoubleSpinBox,
    QMessageBox,
    QInputDialog,
    QScrollArea,
    QSizePolicy,
    QStatusBar,
    QCheckBox,
)
from PyQt6.QtGui import QPixmap, QCursor, QKeySequence, QShortcut
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QObject
from ui.pipeline_controller import PipelineController


class _ClickableImageLabel(QLabel):
    clicked = pyqtSignal(str)  # emits the image file path

    def __init__(self, image_path: str, parent=None):
        super().__init__(parent)
        self._image_path = image_path
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setToolTip("Click to enlarge")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._image_path)
        super().mousePressEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("AI Cinematic Video Pipeline")
        self.resize(980, 680)
        self.controller = PipelineController()

        central = QWidget()
        layout = QVBoxLayout(central)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_pipeline_tab(), "Pipeline")
        self.tabs.addTab(self._build_script_tab(), "Script")
        self.tabs.addTab(self._build_draft_tab(), "Draft Preview")
        self.tabs.addTab(self._build_settings_tab(), "Settings")
        layout.addWidget(self.tabs)

        self.setCentralWidget(central)

        # Status bar with Relaunch button
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)
        btn_relaunch = QPushButton("⟳ Relaunch")
        btn_relaunch.setToolTip("Restart the application")
        btn_relaunch.clicked.connect(self._relaunch)
        status_bar.addPermanentWidget(btn_relaunch)

        self._apply_theme()
        self._wire_signals()

        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(self._save_script)

        self._refresh_recent_projects(self.controller.get_recent_projects())
        self._load_settings_to_form(self.controller.load_settings())

        recent = self.controller.get_recent_projects()
        if recent:
            self.controller.set_project_path(recent[0])

    def _build_pipeline_tab(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)

        project_row = QHBoxLayout()
        self.project_path_input = QLineEdit()
        self.project_path_input.setPlaceholderText("Select or create a project folder")
        btn_select_project = QPushButton("Browse")
        btn_select_project.clicked.connect(self.select_project)
        btn_create_project = QPushButton("Create New Project")
        btn_create_project.clicked.connect(self.create_project)
        project_row.addWidget(QLabel("Project:"))
        project_row.addWidget(self.project_path_input, 1)
        project_row.addWidget(btn_select_project)
        project_row.addWidget(btn_create_project)

        recent_row = QHBoxLayout()
        self.recent_projects_combo = QComboBox()
        self.recent_projects_combo.setPlaceholderText("Recent projects")
        btn_use_recent = QPushButton("Use Selected")
        btn_use_recent.clicked.connect(self.use_recent_project)
        recent_row.addWidget(QLabel("Recent:"))
        recent_row.addWidget(self.recent_projects_combo, 1)
        recent_row.addWidget(btn_use_recent)

        self.pipeline_status_label = QLabel("Ready")
        self.pipeline_progress = QProgressBar()
        self.pipeline_progress.setRange(0, 100)
        self.pipeline_progress.setValue(0)

        controls_row = QHBoxLayout()
        self.stage_selector = QComboBox()
        for label, value in self.controller.get_stage_options():
            self.stage_selector.addItem(label, value)
        self.btn_run_stage = QPushButton("Run Stage")
        self.btn_run_stage.clicked.connect(self.run_selected_stage)
        self.btn_cancel_pipeline = QPushButton("Cancel")
        self.btn_cancel_pipeline.setEnabled(False)
        self.btn_cancel_pipeline.clicked.connect(self.cancel_pipeline)
        controls_row.addWidget(QLabel("Stage:"))
        controls_row.addWidget(self.stage_selector)
        controls_row.addWidget(self.btn_run_stage)
        controls_row.addWidget(self.btn_cancel_pipeline)

        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setPlaceholderText("Pipeline logs will appear here")

        root.addLayout(project_row)
        root.addLayout(recent_row)
        root.addWidget(self.pipeline_status_label)
        root.addWidget(self.pipeline_progress)
        root.addLayout(controls_row)
        root.addWidget(self.log_output, 1)
        return page

    def _build_settings_tab(self) -> QWidget:
        outer = QWidget()
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        page = QWidget()
        root = QVBoxLayout(page)
        scroll.setWidget(page)
        outer_layout.addWidget(scroll, 1)

        form = QFormLayout()

        self.style_preset_input = QComboBox()
        self.style_preset_input.addItems([
            "cinematic", "realistic", "anime", "watercolor", "illustration",
            "noir", "baroque", "concept art", "oil painting", "impressionist",
            "ghibli", "golden hour", "ethereal",
        ])

        self.aspect_ratio_input = QComboBox()
        self.aspect_ratio_input.addItems(["16:9", "9:16", "1:1", "4:3", "21:9"])

        self.seed_input = QSpinBox()
        self.seed_input.setRange(0, 2147483647)

        self.fps_input = QSpinBox()
        self.fps_input.setRange(1, 120)

        self.scene_split_method_input = QComboBox()
        self.scene_split_method_input.addItems(["paragraph", "sentence", "semantic", "timed"])

        self.min_sentence_length_input = QSpinBox()
        self.min_sentence_length_input.setRange(1, 500)

        self.sdxl_model_input = QLineEdit()
        self.svd_model_input = QLineEdit()

        self.clip_engine_input = QComboBox()
        self.clip_engine_input.addItems(["ken_burns", "svd"])
        self.clip_engine_input.setToolTip(
            "ken_burns: CPU-only pan/zoom effect (fast, no VRAM)\n"
            "svd: Stable Video Diffusion (GPU, slow, more realistic motion)"
        )

        self.ken_burns_duration_input = QDoubleSpinBox()
        self.ken_burns_duration_input.setRange(1.0, 30.0)
        self.ken_burns_duration_input.setDecimals(1)
        self.ken_burns_duration_input.setSingleStep(0.5)
        self.ken_burns_duration_input.setValue(4.0)

        self.guidance_scale_input = QDoubleSpinBox()
        self.guidance_scale_input.setRange(1.0, 30.0)
        self.guidance_scale_input.setDecimals(2)
        self.guidance_scale_input.setSingleStep(0.5)

        self.num_inference_steps_input = QSpinBox()
        self.num_inference_steps_input.setRange(1, 200)

        self.num_frames_input = QSpinBox()
        self.num_frames_input.setRange(1, 120)

        self.motion_bucket_id_input = QSpinBox()
        self.motion_bucket_id_input.setRange(0, 255)

        self.audio_volume_input = QDoubleSpinBox()
        self.audio_volume_input.setRange(0.0, 3.0)
        self.audio_volume_input.setDecimals(2)
        self.audio_volume_input.setSingleStep(0.1)

        self.fade_in_input = QDoubleSpinBox()
        self.fade_in_input.setRange(0.0, 10.0)
        self.fade_in_input.setDecimals(2)
        self.fade_in_input.setSingleStep(0.1)

        self.fade_out_input = QDoubleSpinBox()
        self.fade_out_input.setRange(0.0, 10.0)
        self.fade_out_input.setDecimals(2)
        self.fade_out_input.setSingleStep(0.1)

        form.addRow("Style preset", self.style_preset_input)
        form.addRow("Aspect ratio", self.aspect_ratio_input)
        form.addRow("Seed", self.seed_input)
        form.addRow("FPS", self.fps_input)
        form.addRow("Scene split method", self.scene_split_method_input)
        form.addRow("Min sentence length", self.min_sentence_length_input)
        form.addRow("SD model path", self.sdxl_model_input)
        form.addRow("Clip engine", self.clip_engine_input)
        form.addRow("Ken Burns duration (s)", self.ken_burns_duration_input)
        form.addRow("SVD model path", self.svd_model_input)
        form.addRow("Guidance scale", self.guidance_scale_input)
        form.addRow("Inference steps", self.num_inference_steps_input)
        form.addRow("Video frames", self.num_frames_input)
        form.addRow("Motion bucket id", self.motion_bucket_id_input)
        form.addRow("Audio volume", self.audio_volume_input)
        form.addRow("Audio fade in", self.fade_in_input)
        form.addRow("Audio fade out", self.fade_out_input)

        form.addRow(QLabel(""))  # spacer
        form.addRow(QLabel("── Narration TTS (Edge TTS) ──"))

        from narration.tts_engine import EDGE_TTS_VOICES
        self.tts_voice_input = QComboBox()
        for label, short_name, _gender in EDGE_TTS_VOICES:
            self.tts_voice_input.addItem(label, short_name)
        self.tts_voice_input.setToolTip("Voice used for narration synthesis")

        self._tts_preview_btn = QPushButton("▶ Preview")
        self._tts_preview_btn.setToolTip("Play a sample of the selected voice")
        self._tts_preview_btn.clicked.connect(self._preview_tts_voice)
        voice_row = QHBoxLayout()
        voice_row.setContentsMargins(0, 0, 0, 0)
        voice_row.setSpacing(6)
        voice_row.addWidget(self.tts_voice_input, 1)
        voice_row.addWidget(self._tts_preview_btn)
        voice_widget = QWidget()
        voice_widget.setLayout(voice_row)
        voice_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        form.addRow("TTS voice", voice_widget)

        self.tts_rate_input = QSpinBox()
        self.tts_rate_input.setRange(-50, 100)
        self.tts_rate_input.setValue(0)
        self.tts_rate_input.setSuffix("%")
        self.tts_rate_input.setToolTip("Speaking rate offset (+10 = 10% faster, -10 = 10% slower)")
        form.addRow("TTS rate", self.tts_rate_input)

        self.tts_pitch_input = QSpinBox()
        self.tts_pitch_input.setRange(-20, 20)
        self.tts_pitch_input.setValue(0)
        self.tts_pitch_input.setSuffix(" Hz")
        self.tts_pitch_input.setToolTip("Pitch offset in Hz")
        form.addRow("TTS pitch", self.tts_pitch_input)

        self.tts_volume_input = QSpinBox()
        self.tts_volume_input.setRange(-50, 50)
        self.tts_volume_input.setValue(0)
        self.tts_volume_input.setSuffix("%")
        self.tts_volume_input.setToolTip("Volume offset")
        form.addRow("TTS volume", self.tts_volume_input)

        form.addRow(QLabel(""))  # spacer
        form.addRow(QLabel("── Prompt Enhancement (Ollama) ──"))

        self.use_ollama_input = QCheckBox("Enable Ollama prompt enhancement")
        form.addRow("", self.use_ollama_input)

        self.ollama_model_input = QLineEdit()
        self.ollama_model_input.setPlaceholderText("e.g. llama3, mistral")
        form.addRow("Ollama model", self.ollama_model_input)

        self.ollama_host_input = QLineEdit()
        self.ollama_host_input.setPlaceholderText("http://localhost:11434")
        form.addRow("Ollama host", self.ollama_host_input)

        buttons = QHBoxLayout()
        btn_reload = QPushButton("Reload Settings")
        btn_reload.clicked.connect(lambda: self._load_settings_to_form(self.controller.load_settings()))
        btn_save = QPushButton("Save Settings")
        btn_save.clicked.connect(self.save_settings)
        buttons.addWidget(btn_reload)
        buttons.addWidget(btn_save)

        root.addLayout(form)
        root.addLayout(buttons)
        return outer

    def _apply_theme(self) -> None:
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #0F0D13;
                color: #E6E1E5;
                font-family: 'Segoe UI', sans-serif;
                font-size: 12px;
            }
            QMenuBar {
                background-color: #1D1B20;
                color: #E6E1E5;
                border-bottom: 1px solid #211F26;
            }
            QMenuBar::item:selected { background-color: #2A282F; }
            QMenu {
                background-color: #1D1B20;
                color: #E6E1E5;
                border: 1px solid #211F26;
            }
            QMenu::item:selected { background-color: #96BDE2; color: #0F0D13; }
            QToolBar {
                background-color: #1D1B20;
                border-bottom: 1px solid #211F26;
                padding: 4px 6px;
                spacing: 4px;
            }
            QPushButton {
                background-color: #1D1B20;
                color: #E6E1E5;
                border: 1px solid #211F26;
                border-radius: 2px;
                padding: 4px 12px;
                min-height: 24px;
                font-weight: bold;
            }
            QPushButton:hover  { background-color: #2A282F; }
            QPushButton:pressed { background-color: #211F26; }
            QPushButton:disabled { color: #8E8B90; border-color: #211F26; }
            QComboBox {
                background-color: #1D1B20;
                color: #E6E1E5;
                border: 1px solid #211F26;
                border-radius: 2px;
                padding: 2px 6px;
                min-height: 22px;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #1D1B20;
                color: #E6E1E5;
                selection-background-color: #96BDE2;
                selection-color: #0F0D13;
            }
            QLineEdit {
                background-color: #1D1B20;
                color: #E6E1E5;
                border: 1px solid #211F26;
                border-radius: 2px;
                padding: 2px 6px;
                min-height: 22px;
            }
            QLineEdit:focus { border: 1px solid #96BDE2; }
            QSpinBox, QDoubleSpinBox {
                background-color: #1D1B20;
                color: #E6E1E5;
                border: 1px solid #211F26;
                border-radius: 2px;
                padding: 2px 6px;
            }
            QSpinBox::up-button, QDoubleSpinBox::up-button,
            QSpinBox::down-button, QDoubleSpinBox::down-button {
                background-color: #2A282F;
                border: 1px solid #36343B;
                width: 16px;
            }
            QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
            QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
                background-color: #96BDE2;
            }
            QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-bottom: 6px solid #E6E1E5;
                width: 0; height: 0;
            }
            QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid #E6E1E5;
                width: 0; height: 0;
            }
            QPlainTextEdit {
                background-color: #1D1B20;
                color: #E6E1E5;
                border: 1px solid #211F26;
                border-radius: 2px;
                padding: 4px;
                font-family: 'Consolas', monospace;
                font-size: 11px;
            }
            QPlainTextEdit:focus { border: 1px solid #96BDE2; }
            QTabWidget::pane {
                border: 1px solid #211F26;
                background-color: #0F0D13;
            }
            QTabBar::tab {
                background-color: #1D1B20;
                color: #8E8B90;
                border: 1px solid #211F26;
                padding: 6px 14px;
            }
            QTabBar::tab:selected {
                background-color: #0F0D13;
                color: #E6E1E5;
                border-bottom: 2px solid #96BDE2;
            }
            QTabBar::tab:hover { background-color: #2A282F; }
            QLabel { color: #8E8B90; }
            QProgressBar {
                border: 1px solid #211F26;
                border-radius: 2px;
                text-align: center;
                background: #0F0D13;
                color: #E6E1E5;
            }
            QProgressBar::chunk { background: #96BDE2; border-radius: 2px; }
            QScrollBar:vertical {
                background-color: #211F26; width: 22px; border: none;
            }
            QScrollBar::handle:vertical {
                background-color: #7d9ab9; border-radius: 5px; min-height: 20px;
            }
            QScrollBar::handle:vertical:hover { background-color: #96BDE2; }
            QScrollBar::sub-line:vertical, QScrollBar::add-line:vertical {
                border: none; background: none;
            }
        """)

    def _build_draft_tab(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setSpacing(6)

        header_row = QHBoxLayout()
        self._draft_status_label = QLabel("Click \"Run Draft Preview\" to generate a low-res storyboard.")
        self._draft_status_label.setStyleSheet("color:#8E8B90; font-size:11px;")
        header_row.addWidget(self._draft_status_label, 1)

        header_row.addWidget(QLabel("Max scenes:"))
        self._draft_max_scenes = QSpinBox()
        self._draft_max_scenes.setRange(1, 999)
        self._draft_max_scenes.setValue(5)
        self._draft_max_scenes.setToolTip("Limit how many scenes are rendered in Draft Preview (0 = all)")
        self._draft_max_scenes.setFixedWidth(60)
        header_row.addWidget(self._draft_max_scenes)

        btn_run_draft = QPushButton("Run Draft Preview")
        btn_run_draft.clicked.connect(self._run_draft_preview)
        btn_refresh_draft = QPushButton("Refresh")
        btn_refresh_draft.clicked.connect(self._refresh_draft_grid)
        btn_clear_cache = QPushButton("Clear Prompt Cache")
        btn_clear_cache.setToolTip("Delete prompts.yaml so Ollama regenerates all prompts on the next run")
        btn_clear_cache.clicked.connect(self._clear_prompt_cache)
        header_row.addWidget(btn_run_draft)
        header_row.addWidget(btn_refresh_draft)
        header_row.addWidget(btn_clear_cache)
        root.addLayout(header_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._draft_grid_widget = QWidget()
        self._draft_grid_layout = QVBoxLayout(self._draft_grid_widget)
        self._draft_grid_layout.setSpacing(12)
        self._draft_grid_layout.addStretch(1)
        scroll.setWidget(self._draft_grid_widget)
        root.addWidget(scroll, 1)

        return page

    def _delete_draft_image(self, image_path: str, card: QWidget) -> None:
        try:
            os.remove(image_path)
        except Exception as exc:
            QMessageBox.warning(self, "Delete failed", str(exc))
            return
        card.setParent(None)
        card.deleteLater()
        # update count label
        project = self.project_path_input.text().strip()
        draft_dir = os.path.join(project, "output", "draft") if project else ""
        remaining = len([f for f in os.listdir(draft_dir) if f.lower().endswith((".png", ".jpg", ".jpeg"))]) if os.path.isdir(draft_dir) else 0
        self._draft_status_label.setText(f"{remaining} draft image(s) — {draft_dir}")

    def _open_image_viewer(self, image_path: str) -> None:
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QScrollArea
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            return

        screen = self.screen().availableGeometry()
        max_w = int(screen.width() * 0.85)
        max_h = int(screen.height() * 0.85)
        scaled = pixmap.scaled(max_w, max_h, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)

        dlg = QDialog(self)
        dlg.setWindowTitle(os.path.basename(image_path))
        dlg.setModal(True)
        dlg.resize(scaled.width(), scaled.height())
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel()
        lbl.setPixmap(scaled)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.mousePressEvent = lambda _: dlg.accept()
        lbl.setToolTip("Click to close")
        lay.addWidget(lbl)
        dlg.exec()

    def _refresh_draft_grid(self) -> None:
        project = self.project_path_input.text().strip()
        draft_dir = os.path.join(project, "output", "draft") if project else ""

        # clear existing cards
        while self._draft_grid_layout.count() > 1:  # keep trailing stretch
            item = self._draft_grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not draft_dir or not os.path.isdir(draft_dir):
            self._draft_status_label.setText("No draft images found. Run \"Draft Preview\" first.")
            return

        images = sorted(
            [f for f in os.listdir(draft_dir) if f.lower().endswith((".png", ".jpg", ".jpeg"))]
        )

        if not images:
            self._draft_status_label.setText("Draft folder is empty. Run \"Draft Preview\" first.")
            return

        scenes_yaml = os.path.join(project, "output", "scenes.yaml")
        scene_texts: dict = {}
        if os.path.exists(scenes_yaml):
            try:
                import yaml
                data = yaml.safe_load(Path(scenes_yaml).read_text(encoding="utf-8"))
                for s in (data or {}).get("scenes", []):
                    scene_texts[s["id"]] = s["text"]
            except Exception:
                pass

        self._draft_status_label.setText(f"{len(images)} draft image(s) — {draft_dir}")

        for fname in images:
            try:
                scene_id = int(fname.split("_")[1].split(".")[0])
            except Exception:
                scene_id = 0

            card = QWidget()
            card.setStyleSheet("background:#1D1B20; border:1px solid #36343B; border-radius:4px;")
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(10, 8, 10, 8)
            card_layout.setSpacing(12)

            img_label = _ClickableImageLabel(os.path.join(draft_dir, fname))
            img_label.clicked.connect(self._open_image_viewer)
            img_label.setFixedSize(160, 90)
            img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pixmap = QPixmap(os.path.join(draft_dir, fname))
            if not pixmap.isNull():
                img_label.setPixmap(
                    pixmap.scaled(160, 90, Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation)
                )
            else:
                img_label.setText("(no image)")
            card_layout.addWidget(img_label)

            text_block = QVBoxLayout()
            id_lbl = QLabel(f"Scene {scene_id}")
            id_lbl.setStyleSheet("color:#96BDE2; font-weight:bold; font-size:11px; background:transparent; border:none;")
            text_lbl = QLabel(scene_texts.get(scene_id, ""))
            text_lbl.setWordWrap(True)
            text_lbl.setStyleSheet("color:#E6E1E5; font-size:12px; background:transparent; border:none;")
            text_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            text_block.addWidget(id_lbl)
            text_block.addWidget(text_lbl)
            text_block.addStretch(1)
            card_layout.addLayout(text_block, 1)

            image_file = os.path.join(draft_dir, fname)
            btn_delete = QPushButton("🗑")
            btn_delete.setToolTip("Delete this draft image")
            btn_delete.setFixedSize(28, 28)
            btn_delete.setStyleSheet(
                "QPushButton { color:#E73A4B; background:#1D1B20; border:1px solid #36343B; "
                "border-radius:3px; font-size:14px; padding:0; }"
                "QPushButton:hover { background:#2A282F; }"
            )
            btn_delete.clicked.connect(lambda checked, p=image_file, c=card: self._delete_draft_image(p, c))
            card_layout.addWidget(btn_delete)

            self._draft_grid_layout.insertWidget(self._draft_grid_layout.count() - 1, card)

    def _build_script_tab(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setSpacing(6)

        self._script_path_label = QLabel("No project loaded")
        self._script_path_label.setStyleSheet("color:#8E8B90; font-size:11px;")
        root.addWidget(self._script_path_label)

        self._script_editor = QPlainTextEdit()
        self._script_editor.setPlaceholderText("Open or create a project to edit the narration script.")
        self._script_editor.setStyleSheet(
            "QPlainTextEdit { font-family: 'Segoe UI', sans-serif; font-size: 15px; line-height: 1.5; }"
        )
        root.addWidget(self._script_editor, 1)

        btn_row = QHBoxLayout()
        btn_save_script = QPushButton("Save Script")
        btn_save_script.clicked.connect(self._save_script)
        btn_reload_script = QPushButton("Reload from Disk")
        btn_reload_script.clicked.connect(self._reload_script)
        btn_row.addStretch(1)
        btn_row.addWidget(btn_reload_script)
        btn_row.addWidget(btn_save_script)
        root.addLayout(btn_row)

        return page

    def _script_file_path(self) -> str:
        project = self.project_path_input.text().strip()
        if not project:
            return ""
        return os.path.join(project, "input", "narration.txt")

    def _reload_script(self) -> None:
        path = self._script_file_path()
        if not path:
            return
        if os.path.exists(path):
            self._script_editor.setPlainText(Path(path).read_text(encoding="utf-8"))
            self._script_path_label.setText(path)
        else:
            self._script_editor.clear()
            self._script_path_label.setText(f"{path}  (not found)")

    def _save_script(self) -> None:
        path = self._script_file_path()
        if not path:
            QMessageBox.warning(self, "No project", "Load a project before saving the script.")
            return
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            Path(path).write_text(self._script_editor.toPlainText(), encoding="utf-8")
            self._script_path_label.setText(f"Saved: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))

    def _wire_signals(self) -> None:
        self.controller.project_changed.connect(self._on_project_changed)
        self.controller.recent_projects_changed.connect(self._refresh_recent_projects)
        self.controller.pipeline_started.connect(self._on_pipeline_started)
        self.controller.pipeline_progress.connect(self._on_pipeline_progress)
        self.controller.pipeline_log.connect(self._append_log)
        self.controller.pipeline_finished.connect(self._on_pipeline_finished)
        self.controller.settings_saved.connect(self._on_settings_saved)

    def _on_project_changed(self, path: str) -> None:
        # Only reload script from disk if the editor is empty or project actually changed
        current_project = self.project_path_input.text().strip()
        project_changed = os.path.abspath(path) != os.path.abspath(current_project) if current_project else True
        self.project_path_input.setText(path)
        if project_changed:
            self._reload_script()
        self._refresh_draft_grid()

    def _refresh_recent_projects(self, projects) -> None:
        self.recent_projects_combo.blockSignals(True)
        self.recent_projects_combo.clear()
        self.recent_projects_combo.addItems(projects)
        self.recent_projects_combo.blockSignals(False)

    def _on_pipeline_started(self) -> None:
        self.btn_run_stage.setEnabled(False)
        self.btn_cancel_pipeline.setEnabled(True)
        self.pipeline_status_label.setText("Pipeline started")
        self.pipeline_progress.setValue(0)
        self._append_log("Pipeline started.")

    def _on_pipeline_progress(self, value: int, message: str) -> None:
        self.pipeline_progress.setValue(value)
        self.pipeline_status_label.setText(message)
        self._append_log(message)

    def _append_log(self, message: str) -> None:
        self.log_output.appendPlainText(message)

    def _on_pipeline_finished(self, success: bool, payload: str) -> None:
        self.btn_run_stage.setEnabled(True)
        self.btn_cancel_pipeline.setEnabled(False)

        # Auto-refresh the draft grid whenever the draft stage completes
        if success and payload and os.path.isdir(payload) and "draft" in payload:
            self._refresh_draft_grid()

        if success:
            self.pipeline_status_label.setText("Pipeline complete")
            self.pipeline_progress.setValue(100)
            self._append_log(f"Finished: {payload}")
            QMessageBox.information(self, "Pipeline complete", f"Final output:\n{payload}")
            return

        if "canceled" in payload.lower():
            self.pipeline_status_label.setText("Pipeline canceled")
            self._append_log(payload)
            QMessageBox.information(self, "Pipeline canceled", payload)
            return

        self.pipeline_status_label.setText("Pipeline failed")
        self._append_log(f"Error: {payload}")
        QMessageBox.critical(self, "Pipeline failed", payload)

    def _on_settings_saved(self, path: str) -> None:
        QMessageBox.information(self, "Settings saved", f"Settings saved to:\n{path}")

    def _load_settings_to_form(self, settings: dict) -> None:
        self.style_preset_input.setCurrentText(str(settings.get("style_preset", "cinematic")))
        self.aspect_ratio_input.setCurrentText(str(settings.get("aspect_ratio", "16:9")))
        self.seed_input.setValue(int(settings.get("seed", 42)))
        self.fps_input.setValue(int(settings.get("fps", 8)))
        self.scene_split_method_input.setCurrentText(str(settings.get("scene_split_method", "paragraph")))
        self.min_sentence_length_input.setValue(int(settings.get("min_sentence_length", 20)))
        self.sdxl_model_input.setText(str(settings.get("sdxl_base", "models/sd3")))
        self.svd_model_input.setText(str(settings.get("svd", "models/svd")))
        self.clip_engine_input.setCurrentText(str(settings.get("clip_engine", "ken_burns")))
        self.ken_burns_duration_input.setValue(float(settings.get("ken_burns_duration", 4.0)))
        self.guidance_scale_input.setValue(float(settings.get("guidance_scale", 7.5)))
        self.num_inference_steps_input.setValue(int(settings.get("num_inference_steps", 30)))
        self.num_frames_input.setValue(int(settings.get("num_frames", 14)))
        self.motion_bucket_id_input.setValue(int(settings.get("motion_bucket_id", 127)))
        self.audio_volume_input.setValue(float(settings.get("audio_volume", 1.0)))
        self.fade_in_input.setValue(float(settings.get("fade_in", 0.5)))
        self.fade_out_input.setValue(float(settings.get("fade_out", 0.5)))
        self.use_ollama_input.setChecked(bool(settings.get("use_ollama", False)))
        self.ollama_model_input.setText(str(settings.get("ollama_model", "llama3")))
        self.ollama_host_input.setText(str(settings.get("ollama_host", "http://localhost:11434")))

        # TTS
        tts_voice = str(settings.get("tts_voice", "it-IT-DiegoNeural"))
        idx = self.tts_voice_input.findData(tts_voice)
        if idx >= 0:
            self.tts_voice_input.setCurrentIndex(idx)
        tts_rate = str(settings.get("tts_rate", "+0%")).replace("+", "").replace("%", "")
        self.tts_rate_input.setValue(int(tts_rate) if tts_rate.lstrip("-").isdigit() else 0)
        tts_pitch = str(settings.get("tts_pitch", "+0Hz")).replace("+", "").replace("Hz", "")
        self.tts_pitch_input.setValue(int(tts_pitch) if tts_pitch.lstrip("-").isdigit() else 0)
        tts_volume = str(settings.get("tts_volume", "+0%")).replace("+", "").replace("%", "")
        self.tts_volume_input.setValue(int(tts_volume) if tts_volume.lstrip("-").isdigit() else 0)

    def _collect_settings_from_form(self) -> dict:
        return {
            "style_preset": self.style_preset_input.currentText(),
            "aspect_ratio": self.aspect_ratio_input.currentText(),
            "seed": self.seed_input.value(),
            "fps": self.fps_input.value(),
            "scene_split_method": self.scene_split_method_input.currentText(),
            "min_sentence_length": self.min_sentence_length_input.value(),
            "sdxl_base": self.sdxl_model_input.text().strip(),
            "svd": self.svd_model_input.text().strip(),
            "clip_engine": self.clip_engine_input.currentText(),
            "ken_burns_duration": self.ken_burns_duration_input.value(),
            "guidance_scale": self.guidance_scale_input.value(),
            "num_inference_steps": self.num_inference_steps_input.value(),
            "num_frames": self.num_frames_input.value(),
            "motion_bucket_id": self.motion_bucket_id_input.value(),
            "audio_volume": self.audio_volume_input.value(),
            "fade_in": self.fade_in_input.value(),
            "fade_out": self.fade_out_input.value(),
            "use_ollama": self.use_ollama_input.isChecked(),
            "ollama_model": self.ollama_model_input.text().strip() or "llama3",
            "ollama_host": self.ollama_host_input.text().strip() or "http://localhost:11434",
            "tts_voice": self.tts_voice_input.currentData() or "it-IT-DiegoNeural",
            "tts_rate": f"{self.tts_rate_input.value():+d}%",
            "tts_pitch": f"{self.tts_pitch_input.value():+d}Hz",
            "tts_volume": f"{self.tts_volume_input.value():+d}%",
        }

    def select_project(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Project Folder")
        if folder:
            self.controller.set_project_path(folder)

    def use_recent_project(self):
        selected = self.recent_projects_combo.currentText().strip()
        if selected:
            self.controller.set_project_path(selected)

    def create_project(self):
        parent = QFileDialog.getExistingDirectory(self, "Select Parent Folder")
        if not parent:
            return

        name, accepted = QInputDialog.getText(self, "Create Project", "Project name:")
        if not accepted or not name.strip():
            return

        try:
            created = self.controller.create_project(parent, name.strip())
            QMessageBox.information(self, "Project created", f"Created project:\n{created}")
        except Exception as exc:
            QMessageBox.critical(self, "Create project failed", str(exc))

    def _preview_tts_voice(self) -> None:
        voice  = self.tts_voice_input.currentData() or "it-IT-DiegoNeural"
        rate   = f"{self.tts_rate_input.value():+d}%"
        pitch  = f"{self.tts_pitch_input.value():+d}Hz"
        volume = f"{self.tts_volume_input.value():+d}%"

        self._tts_preview_btn.setEnabled(False)
        self._tts_preview_btn.setText("…")

        import tempfile, asyncio

        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp_path = tmp.name
        tmp.close()

        class _Worker(QObject):
            done  = pyqtSignal(str)
            error = pyqtSignal(str)

            def __init__(self, voice, rate, pitch, volume, path):
                super().__init__()
                self._voice  = voice
                self._rate   = rate
                self._pitch  = pitch
                self._volume = volume
                self._path   = path

            def run(self):
                try:
                    import sys, subprocess, tempfile as _tf, os as _os
                    kwargs_lines = ""
                    if self._rate.lstrip('+').rstrip('%') != '0':
                        kwargs_lines += f"    kwargs['rate'] = {self._rate!r}\n"
                    if self._pitch.lstrip('+').rstrip('Hz') != '0':
                        kwargs_lines += f"    kwargs['pitch'] = {self._pitch!r}\n"
                    if self._volume.lstrip('+').rstrip('%') != '0':
                        kwargs_lines += f"    kwargs['volume'] = {self._volume!r}\n"
                    script = (
                        "# -*- coding: utf-8 -*-\n"
                        "import asyncio, edge_tts\n"
                        "async def _go():\n"
                        "    kwargs = {}\n"
                        + kwargs_lines +
                        f"    c = edge_tts.Communicate('Ciao, questa e una anteprima della voce.', {self._voice!r}, **kwargs)\n"
                        f"    await c.save({self._path!r})\n"
                        "asyncio.run(_go())\n"
                    )
                    sf = _tf.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8')
                    sf.write(script)
                    sf.close()
                    try:
                        result = subprocess.run(
                            [sys.executable, sf.name],
                            capture_output=True, text=True, timeout=30,
                        )
                    finally:
                        _os.unlink(sf.name)
                    if result.returncode != 0:
                        raise RuntimeError(result.stderr.strip() or "Synthesis failed")
                    self.done.emit(self._path)
                except Exception as exc:
                    self.error.emit(str(exc))

        self._tts_preview_thread = QThread(self)
        self._tts_preview_worker = _Worker(voice, rate, pitch, volume, tmp_path)
        self._tts_preview_worker.moveToThread(self._tts_preview_thread)
        self._tts_preview_thread.started.connect(self._tts_preview_worker.run)

        def _on_done(path):
            self._tts_preview_btn.setEnabled(True)
            self._tts_preview_btn.setText("▶ Preview")
            from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
            from PyQt6.QtCore import QUrl
            self._tts_preview_player = QMediaPlayer(self)
            audio_out = QAudioOutput(self)
            self._tts_preview_player.setAudioOutput(audio_out)
            self._tts_preview_audio_out = audio_out
            audio_out.setVolume(1.0)
            self._tts_preview_player.setSource(QUrl.fromLocalFile(path))
            self._tts_preview_player.play()
            self._tts_preview_thread.quit()

        def _on_error(msg):
            self._tts_preview_btn.setEnabled(True)
            self._tts_preview_btn.setText("▶ Preview")
            QMessageBox.warning(self, "TTS Preview failed", msg)
            self._tts_preview_thread.quit()

        self._tts_preview_worker.done.connect(_on_done)
        self._tts_preview_worker.error.connect(_on_error)
        self._tts_preview_thread.start()

    def _relaunch(self) -> None:
        os.execv(sys.executable, [sys.executable] + sys.argv)

    def _clear_prompt_cache(self) -> None:
        project = self.project_path_input.text().strip()
        if not project:
            QMessageBox.warning(self, "No project", "Load a project first.")
            return
        path = os.path.join(project, "output", "prompts.yaml")
        if not os.path.exists(path):
            QMessageBox.information(self, "No cache", "No prompts.yaml found — nothing to clear.")
            return
        try:
            os.remove(path)
            self._draft_status_label.setText("Prompt cache cleared — next run will regenerate all prompts.")
        except Exception as exc:
            QMessageBox.critical(self, "Delete failed", str(exc))

    def _run_draft_preview(self):
        path = self.project_path_input.text().strip()
        if not path:
            QMessageBox.warning(self, "No project", "Load or create a project first.")
            return
        self._save_script()  # always flush editor to disk before running
        self.controller.set_project_path(path)
        max_scenes = self._draft_max_scenes.value()
        self.controller.run_pipeline("draft", extra_config={"draft_max_scenes": max_scenes})
        self.tabs.setCurrentIndex(self.tabs.indexOf(self._draft_grid_widget.parent().parent()))

    def run_selected_stage(self):
        path = self.project_path_input.text().strip()
        if path:
            self.controller.set_project_path(path)
        stage = self.stage_selector.currentData()
        self.controller.run_pipeline(stage)

    def cancel_pipeline(self):
        self.controller.cancel_pipeline()

    def save_settings(self):
        try:
            self.controller.save_settings(self._collect_settings_from_form())
        except Exception as exc:
            QMessageBox.critical(self, "Save settings failed", str(exc))
