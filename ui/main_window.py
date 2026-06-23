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
)
from ui.pipeline_controller import PipelineController


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
        self.tabs.addTab(self._build_settings_tab(), "Settings")
        layout.addWidget(self.tabs)

        self.setCentralWidget(central)
        self._wire_signals()

        self._refresh_recent_projects(self.controller.get_recent_projects())
        self._load_settings_to_form(self.controller.load_settings())

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
        self.btn_run_pipeline = QPushButton("Run Full Pipeline")
        self.btn_run_pipeline.clicked.connect(self.run_pipeline)
        self.btn_run_stage = QPushButton("Run Selected Stage")
        self.btn_run_stage.clicked.connect(self.run_selected_stage)
        self.btn_cancel_pipeline = QPushButton("Cancel")
        self.btn_cancel_pipeline.setEnabled(False)
        self.btn_cancel_pipeline.clicked.connect(self.cancel_pipeline)
        controls_row.addWidget(QLabel("Stage:"))
        controls_row.addWidget(self.stage_selector)
        controls_row.addWidget(self.btn_run_pipeline)
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
        page = QWidget()
        root = QVBoxLayout(page)

        form = QFormLayout()

        self.style_preset_input = QComboBox()
        self.style_preset_input.addItems(["cinematic", "realistic", "anime", "watercolor", "illustration"])

        self.aspect_ratio_input = QComboBox()
        self.aspect_ratio_input.addItems(["16:9", "9:16", "1:1", "4:3", "21:9"])

        self.seed_input = QSpinBox()
        self.seed_input.setRange(0, 2147483647)

        self.fps_input = QSpinBox()
        self.fps_input.setRange(1, 120)

        self.scene_split_method_input = QComboBox()
        self.scene_split_method_input.addItems(["sentence", "semantic", "timed"])

        self.min_sentence_length_input = QSpinBox()
        self.min_sentence_length_input.setRange(1, 500)

        self.sdxl_model_input = QLineEdit()
        self.svd_model_input = QLineEdit()

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
        form.addRow("SVD model path", self.svd_model_input)
        form.addRow("Guidance scale", self.guidance_scale_input)
        form.addRow("Inference steps", self.num_inference_steps_input)
        form.addRow("Video frames", self.num_frames_input)
        form.addRow("Motion bucket id", self.motion_bucket_id_input)
        form.addRow("Audio volume", self.audio_volume_input)
        form.addRow("Audio fade in", self.fade_in_input)
        form.addRow("Audio fade out", self.fade_out_input)

        buttons = QHBoxLayout()
        btn_reload = QPushButton("Reload Settings")
        btn_reload.clicked.connect(lambda: self._load_settings_to_form(self.controller.load_settings()))
        btn_save = QPushButton("Save Settings")
        btn_save.clicked.connect(self.save_settings)
        buttons.addWidget(btn_reload)
        buttons.addWidget(btn_save)

        root.addLayout(form)
        root.addLayout(buttons)
        return page

    def _wire_signals(self) -> None:
        self.controller.project_changed.connect(self._on_project_changed)
        self.controller.recent_projects_changed.connect(self._refresh_recent_projects)
        self.controller.pipeline_started.connect(self._on_pipeline_started)
        self.controller.pipeline_progress.connect(self._on_pipeline_progress)
        self.controller.pipeline_log.connect(self._append_log)
        self.controller.pipeline_finished.connect(self._on_pipeline_finished)
        self.controller.settings_saved.connect(self._on_settings_saved)

    def _on_project_changed(self, path: str) -> None:
        self.project_path_input.setText(path)

    def _refresh_recent_projects(self, projects) -> None:
        self.recent_projects_combo.blockSignals(True)
        self.recent_projects_combo.clear()
        self.recent_projects_combo.addItems(projects)
        self.recent_projects_combo.blockSignals(False)

    def _on_pipeline_started(self) -> None:
        self.btn_run_pipeline.setEnabled(False)
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
        self.btn_run_pipeline.setEnabled(True)
        self.btn_run_stage.setEnabled(True)
        self.btn_cancel_pipeline.setEnabled(False)
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
        self.scene_split_method_input.setCurrentText(str(settings.get("scene_split_method", "sentence")))
        self.min_sentence_length_input.setValue(int(settings.get("min_sentence_length", 20)))
        self.sdxl_model_input.setText(str(settings.get("sdxl_base", "models/sd3")))
        self.svd_model_input.setText(str(settings.get("svd", "models/svd")))
        self.guidance_scale_input.setValue(float(settings.get("guidance_scale", 7.5)))
        self.num_inference_steps_input.setValue(int(settings.get("num_inference_steps", 30)))
        self.num_frames_input.setValue(int(settings.get("num_frames", 14)))
        self.motion_bucket_id_input.setValue(int(settings.get("motion_bucket_id", 127)))
        self.audio_volume_input.setValue(float(settings.get("audio_volume", 1.0)))
        self.fade_in_input.setValue(float(settings.get("fade_in", 0.5)))
        self.fade_out_input.setValue(float(settings.get("fade_out", 0.5)))

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
            "guidance_scale": self.guidance_scale_input.value(),
            "num_inference_steps": self.num_inference_steps_input.value(),
            "num_frames": self.num_frames_input.value(),
            "motion_bucket_id": self.motion_bucket_id_input.value(),
            "audio_volume": self.audio_volume_input.value(),
            "fade_in": self.fade_in_input.value(),
            "fade_out": self.fade_out_input.value(),
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

    def run_pipeline(self):
        path = self.project_path_input.text().strip()
        if path:
            self.controller.set_project_path(path)
        self.controller.run_full_pipeline()

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
