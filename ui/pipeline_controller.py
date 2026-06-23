import glob
import os
from typing import Dict, List, Optional, Tuple

import yaml
from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot

from narration.transcript_loader import TranscriptLoader
from narration.scene_splitter import SceneSplitter
from prompts.prompt_builder import PromptBuilder
from utilis.config_loader import ConfigLoader
from utilis.logger import Logger


class PipelineWorker(QObject):
    progress = pyqtSignal(int, str)
    log = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, project_path: str, config: Dict, root_dir: str, stage: str = "full"):
        super().__init__()
        self.project_path = project_path
        self.config = config
        self.root_dir = root_dir
        self.stage = stage
        self._cancel_requested = False

    def _emit_progress(self, value: int, message: str) -> None:
        self.progress.emit(max(0, min(100, value)), message)

    @pyqtSlot()
    def cancel(self) -> None:
        self._cancel_requested = True
        self.log.emit("Cancellation requested. Waiting for current step to finish...")

    def _check_cancel(self) -> None:
        if self._cancel_requested:
            raise RuntimeError("Pipeline canceled by user.")

    def _resolve_path(self, path_value: str) -> str:
        if os.path.isabs(path_value):
            return path_value
        return os.path.abspath(os.path.join(self.root_dir, path_value))

    @staticmethod
    def _extract_scene_id(path: str) -> int:
        name = os.path.basename(path)
        try:
            return int(name.split("_")[1].split(".")[0])
        except Exception:
            return 0

    @staticmethod
    def _scene_image_candidates(images_dir: str) -> List[str]:
        candidates: List[str] = []
        for ext in ("png", "jpg", "jpeg"):
            candidates.extend(glob.glob(os.path.join(images_dir, f"scene_*.{ext}")))
        return sorted(candidates, key=PipelineWorker._extract_scene_id)

    @pyqtSlot()
    def run(self):
        try:
            stage = (self.stage or "full").strip().lower()
            if stage not in {"full", "narration", "scenes", "images", "clips", "assemble", "audio"}:
                raise ValueError(f"Unknown stage: {stage}")

            input_text = os.path.join(self.project_path, "input", "narration.txt")
            input_audio = os.path.join(self.project_path, "input", "audio.wav")
            images_dir = os.path.join(self.project_path, "output", "images")
            clips_dir = os.path.join(self.project_path, "output", "clips")
            final_dir = os.path.join(self.project_path, "output", "final")
            scenes_path = os.path.join(self.project_path, "output", "scenes.yaml")
            final_video_path = os.path.join(final_dir, "final_video.mp4")
            final_with_audio_path = os.path.join(final_dir, "final_with_audio.mp4")

            os.makedirs(images_dir, exist_ok=True)
            os.makedirs(clips_dir, exist_ok=True)
            os.makedirs(final_dir, exist_ok=True)

            narration_text = ""
            scenes = []

            if stage in {"full", "narration", "scenes", "images"}:
                self._check_cancel()
                self._emit_progress(5, "Loading narration")
                narration_text = TranscriptLoader().load(input_text)
                self.log.emit("Narration loaded.")

                if stage == "narration":
                    self._emit_progress(100, "Narration loaded")
                    self.finished.emit(True, input_text)
                    return

            if stage in {"full", "scenes", "images"}:
                self._check_cancel()
                self._emit_progress(15, "Splitting narration into scenes")
                splitter = SceneSplitter(min_sentence_length=int(self.config.get("min_sentence_length", 20)))
                scenes = splitter.split_into_scenes(
                    narration_text,
                    method=self.config.get("scene_split_method", "sentence"),
                )
                if not scenes:
                    raise ValueError("No scenes were produced from narration text.")
                with open(scenes_path, "w", encoding="utf-8") as handle:
                    yaml.safe_dump({"scenes": scenes}, handle, sort_keys=False)
                self.log.emit(f"Generated {len(scenes)} scenes.")

                if stage == "scenes":
                    self._emit_progress(100, "Scenes generated")
                    self.finished.emit(True, scenes_path)
                    return

            if stage in {"full", "images"}:
                from images.image_generator import ImageGenerator

                self._check_cancel()
                self._emit_progress(25, "Building prompts")
                prompt_builder = PromptBuilder(
                    style_preset=self.config.get("style_preset", "cinematic"),
                    default_aspect_ratio=self.config.get("aspect_ratio", "16:9"),
                )

                self._check_cancel()
                self._emit_progress(30, "Generating scene images")
                image_gen = ImageGenerator(
                    model_path=self._resolve_path(self.config.get("sdxl_base", "models/sd3")),
                    output_dir=images_dir,
                    guidance_scale=float(self.config.get("guidance_scale", 7.5)),
                    num_inference_steps=int(self.config.get("num_inference_steps", 30)),
                    seed=int(self.config.get("seed", 42)),
                )
                total_scenes = len(scenes)
                for index, scene in enumerate(scenes, start=1):
                    self._check_cancel()
                    prompt = prompt_builder.build_prompt(scene)
                    image_gen.generate_image(prompt, int(scene["id"]))
                    if stage == "full":
                        step = 30 + int((index / total_scenes) * 25)
                    else:
                        step = 30 + int((index / total_scenes) * 70)
                    self._emit_progress(step, f"Generated image {index}/{total_scenes}")

                if stage == "images":
                    self._emit_progress(100, "Image generation complete")
                    self.finished.emit(True, images_dir)
                    return

            if stage in {"full", "clips"}:
                from video.video_generator import VideoGenerator

                self._check_cancel()
                self._emit_progress(55 if stage == "full" else 10, "Generating video clips")
                image_paths = self._scene_image_candidates(images_dir)
                if not image_paths:
                    raise FileNotFoundError(
                        f"No scene images found in {images_dir}. Run image generation first."
                    )

                video_gen = VideoGenerator(
                    model_path=self._resolve_path(self.config.get("svd", "models/svd")),
                    output_dir=clips_dir,
                    num_frames=int(self.config.get("num_frames", 14)),
                    motion_bucket_id=int(self.config.get("motion_bucket_id", 127)),
                    fps=int(self.config.get("fps", 8)),
                    seed=int(self.config.get("seed", 42)),
                )
                total_images = len(image_paths)
                for index, image_path in enumerate(image_paths, start=1):
                    self._check_cancel()
                    scene_id = self._extract_scene_id(image_path)
                    video_gen.generate_clip(image_path, scene_id)
                    if stage == "full":
                        step = 55 + int((index / total_images) * 25)
                    else:
                        step = 10 + int((index / total_images) * 80)
                    self._emit_progress(step, f"Generated clip {index}/{total_images}")

                if stage == "clips":
                    self._emit_progress(100, "Clip generation complete")
                    self.finished.emit(True, clips_dir)
                    return

            if stage in {"full", "assemble"}:
                from video.clip_assembler import ClipAssembler

                self._check_cancel()
                self._emit_progress(82 if stage == "full" else 20, "Assembling final video")
                assembler = ClipAssembler(final_video_path, fps=int(self.config.get("fps", 8)))
                assembler.assemble(clips_dir)

                if stage == "assemble":
                    self._emit_progress(100, "Assemble complete")
                    self.finished.emit(True, final_video_path)
                    return

            if stage in {"full", "audio"}:
                from video.audio_sync import AudioSync

                self._check_cancel()
                self._emit_progress(92 if stage == "full" else 20, "Syncing narration audio")
                if not os.path.exists(final_video_path):
                    raise FileNotFoundError(
                        f"Final video not found at {final_video_path}. Run assemble stage first."
                    )

                sync = AudioSync(
                    output_path=final_with_audio_path,
                    audio_volume=float(self.config.get("audio_volume", 1.0)),
                    fade_in=float(self.config.get("fade_in", 0.5)),
                    fade_out=float(self.config.get("fade_out", 0.5)),
                )
                sync.merge(final_video_path, input_audio)

                self._emit_progress(100, "Audio sync complete")
                self.finished.emit(True, final_with_audio_path)
                return

            self._emit_progress(100, "Pipeline complete")
            self.finished.emit(True, final_with_audio_path)
        except Exception as exc:
            self.finished.emit(False, str(exc))


class PipelineController(QObject):
    project_changed = pyqtSignal(str)
    recent_projects_changed = pyqtSignal(list)
    settings_loaded = pyqtSignal(dict)
    settings_saved = pyqtSignal(str)

    pipeline_started = pyqtSignal()
    pipeline_progress = pyqtSignal(int, str)
    pipeline_log = pyqtSignal(str)
    pipeline_finished = pyqtSignal(bool, str)

    PIPELINE_STAGES: List[Tuple[str, str]] = [
        ("Full Pipeline", "full"),
        ("Load Narration", "narration"),
        ("Split Scenes", "scenes"),
        ("Generate Images", "images"),
        ("Generate Clips", "clips"),
        ("Assemble Video", "assemble"),
        ("Sync Audio", "audio"),
    ]

    DEFAULT_SETTINGS = {
        "style_preset": "cinematic",
        "aspect_ratio": "16:9",
        "seed": 42,
        "fps": 8,
        "scene_split_method": "sentence",
        "min_sentence_length": 20,
        "sdxl_base": "models/sd3",
        "svd": "models/svd",
        "guidance_scale": 7.5,
        "num_inference_steps": 30,
        "num_frames": 14,
        "motion_bucket_id": 127,
        "audio_volume": 1.0,
        "fade_in": 0.5,
        "fade_out": 0.5,
    }

    def __init__(self):
        super().__init__()
        self.project_path: Optional[str] = None
        self.log = Logger()

        self.root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        self.config_dir = os.path.join(self.root_dir, "config")
        os.makedirs(self.config_dir, exist_ok=True)
        self.config_loader = ConfigLoader(self.config_dir)

        self.recent_projects_path = os.path.join(self.config_dir, "recent_projects.yaml")
        self.recent_projects: List[str] = self._load_recent_projects()
        self.config = self.load_settings()

        self._thread: Optional[QThread] = None
        self._worker: Optional[PipelineWorker] = None

    def set_project_path(self, path: str) -> None:
        normalized = os.path.abspath(path)
        self.project_path = normalized
        self._add_recent_project(normalized)
        self.log.info(f"Project path set to: {normalized}")
        self.project_changed.emit(normalized)

    def get_recent_projects(self) -> List[str]:
        return list(self.recent_projects)

    def get_stage_options(self) -> List[Tuple[str, str]]:
        return list(self.PIPELINE_STAGES)

    def create_project(self, parent_dir: str, project_name: str) -> str:
        project_path = os.path.join(parent_dir, project_name)
        if os.path.exists(project_path):
            raise FileExistsError(f"Project already exists: {project_path}")

        os.makedirs(os.path.join(project_path, "input"), exist_ok=True)
        os.makedirs(os.path.join(project_path, "output", "images"), exist_ok=True)
        os.makedirs(os.path.join(project_path, "output", "clips"), exist_ok=True)
        os.makedirs(os.path.join(project_path, "output", "final"), exist_ok=True)

        narration_path = os.path.join(project_path, "input", "narration.txt")
        with open(narration_path, "w", encoding="utf-8") as handle:
            handle.write("Paste narration text here.\n")

        self.set_project_path(project_path)
        return project_path

    def load_settings(self) -> Dict:
        loaded = self.config_loader.load_settings(default=self.DEFAULT_SETTINGS, create_if_missing=True)
        merged = dict(self.DEFAULT_SETTINGS)
        merged.update(loaded or {})
        self.config = merged
        self.settings_loaded.emit(dict(self.config))
        return self.config

    def save_settings(self, settings: Dict) -> None:
        merged = dict(self.DEFAULT_SETTINGS)
        merged.update(settings)
        self.config_loader.save_settings(merged)
        self.config = merged
        settings_path = os.path.join(self.config_dir, "settings.yaml")
        self.settings_saved.emit(settings_path)
        self.log.info(f"Saved settings: {settings_path}")

    def run_full_pipeline(self) -> None:
        self.run_pipeline("full")

    def run_pipeline(self, stage: str = "full") -> None:
        if self._thread is not None:
            self.log.warning("Pipeline is already running.")
            return

        if not self.project_path:
            error = "No project path set."
            self.log.error(error)
            self.pipeline_finished.emit(False, error)
            return

        self._thread = QThread()
        self._worker = PipelineWorker(self.project_path, dict(self.config), self.root_dir, stage=stage)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self.pipeline_progress.emit)
        self._worker.log.connect(self.pipeline_log.emit)
        self._worker.finished.connect(self._handle_pipeline_finished)

        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)

        self.pipeline_started.emit()
        self._thread.start()

    def cancel_pipeline(self) -> None:
        if self._worker is None:
            self.pipeline_log.emit("No active pipeline run.")
            return
        self._worker.cancel()

    @pyqtSlot(bool, str)
    def _handle_pipeline_finished(self, success: bool, payload: str) -> None:
        self.pipeline_finished.emit(success, payload)
        self._worker = None
        self._thread = None

    def _load_recent_projects(self) -> List[str]:
        if not os.path.exists(self.recent_projects_path):
            return []

        with open(self.recent_projects_path, "r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}

        projects = data.get("projects", [])
        return [path for path in projects if isinstance(path, str) and os.path.isdir(path)]

    def _save_recent_projects(self) -> None:
        with open(self.recent_projects_path, "w", encoding="utf-8") as handle:
            yaml.safe_dump({"projects": self.recent_projects[:10]}, handle, sort_keys=False)

    def _add_recent_project(self, path: str) -> None:
        if path in self.recent_projects:
            self.recent_projects.remove(path)
        self.recent_projects.insert(0, path)
        self.recent_projects = [item for item in self.recent_projects if os.path.isdir(item)][:10]
        self._save_recent_projects()
        self.recent_projects_changed.emit(list(self.recent_projects))
