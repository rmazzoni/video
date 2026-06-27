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
            if stage not in {"full", "narration", "scenes", "tts", "images", "clips", "assemble", "audio", "draft"}:
                raise ValueError(f"Unknown stage: {stage}")

            input_text = os.path.join(self.project_path, "input", "narration.txt")
            input_audio = os.path.join(self.project_path, "input", "audio.wav")
            tts_dir = os.path.join(self.project_path, "output", "audio")
            timings_path = os.path.join(tts_dir, "timings.yaml")
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

            if stage in {"full", "narration", "scenes", "tts", "images", "draft"}:
                self._check_cancel()
                self._emit_progress(5, "Loading narration")
                narration_text = TranscriptLoader().load(input_text)
                self.log.emit("Narration loaded.")

                if stage == "narration":
                    self._emit_progress(100, "Narration loaded")
                    self.finished.emit(True, input_text)
                    return

            if stage in {"full", "scenes", "tts", "images", "draft"}:
                self._check_cancel()
                self._emit_progress(15, "Splitting narration into scenes")
                splitter = SceneSplitter(min_sentence_length=int(self.config.get("min_sentence_length", 20)))
                scenes = splitter.split_into_scenes(
                    narration_text,
                    method=self.config.get("scene_split_method", "paragraph"),
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

            if stage in {"full", "tts"}:
                from narration.tts_engine import TTSEngine

                os.makedirs(tts_dir, exist_ok=True)
                self._check_cancel()
                self._emit_progress(20, "Synthesising narration audio (TTS)")
                voice = self.config.get("tts_voice", "it-IT-DiegoNeural")
                self.log.emit(f"TTS voice: {voice}")

                # Use dubbed text from dubbing.yaml if it exists, else scene text
                dubbing_path = os.path.join(self.project_path, "output", "dubbing.yaml")
                dubbed_texts: dict = {}
                if os.path.exists(dubbing_path):
                    with open(dubbing_path, "r", encoding="utf-8") as fh:
                        raw = yaml.safe_load(fh) or {}
                    dubbed_texts = {
                        int(k): (v.get("dubbed") or v.get("original") or "")
                        for k, v in raw.items()
                    }
                    self.log.emit(f"Loaded dubbed text for {len(dubbed_texts)} scene(s) from dubbing.yaml")

                # Merge dubbed text into scenes
                tts_scenes = []
                for s in scenes:
                    sid = int(s["id"])
                    tts_scenes.append({
                        "id": sid,
                        "text": dubbed_texts.get(sid, s["text"]) or s["text"],
                    })

                def _on_tts_progress(scene_id, index, total, skipped=False):
                    action = "Skipped" if skipped else "Synthesised"
                    step = 20 + int((index / total) * 75)
                    self._emit_progress(step, f"{action} audio {index}/{total} (scene {scene_id})")
                    self.log.emit(f"{action} TTS scene {scene_id}")

                engine = TTSEngine(
                    output_dir=tts_dir,
                    voice=voice,
                    rate=self.config.get("tts_rate", "+0%"),
                    pitch=self.config.get("tts_pitch", "+0Hz"),
                    volume=self.config.get("tts_volume", "+0%"),
                )
                engine.synthesise_scenes(
                    tts_scenes,
                    timings_path=timings_path,
                    on_progress=_on_tts_progress,
                    skip_existing=True,
                )
                self._emit_progress(100, "TTS synthesis complete")
                self.finished.emit(True, tts_dir)
                if stage == "tts":
                    return

            if stage == "draft":
                from images.image_generator import ImageGenerator

                draft_dir = os.path.join(self.project_path, "output", "draft")
                os.makedirs(draft_dir, exist_ok=True)

                self._check_cancel()
                self._emit_progress(25, "Building prompts for draft")
                prompt_builder = PromptBuilder(
                    style_preset=self.config.get("style_preset", "cinematic"),
                    default_aspect_ratio=self.config.get("aspect_ratio", "16:9"),
                    use_ollama=bool(self.config.get("use_ollama", False)),
                    ollama_model=str(self.config.get("ollama_model", "llama3")),
                    ollama_host=str(self.config.get("ollama_host", "http://localhost:11434")),
                )
                if prompt_builder._enhancer:
                    if prompt_builder._enhancer.is_available():
                        self.log.emit("Ollama prompt enhancement: ACTIVE")
                    else:
                        self.log.emit("Ollama not available — using rule-based prompts.")
                image_gen = ImageGenerator(
                    model_path=self._resolve_path(self.config.get("sdxl_base", "models/sd3")),
                    output_dir=draft_dir,
                    guidance_scale=6.0,
                    num_inference_steps=15,
                    seed=int(self.config.get("seed", 42)),
                    width=512,
                    height=512,
                )
                total_scenes = len(scenes)
                max_draft = int(self.config.get("draft_max_scenes", 0))
                if max_draft and max_draft < total_scenes:
                    scenes = scenes[:max_draft]
                    total_scenes = max_draft

                prompts_path = os.path.join(self.project_path, "output", "prompts.yaml")
                cached_prompts: dict = {}
                if os.path.exists(prompts_path):
                    with open(prompts_path, "r", encoding="utf-8") as fh:
                        cached_prompts = yaml.safe_load(fh) or {}

                for index, scene in enumerate(scenes, start=1):
                    self._check_cancel()
                    scene_id = int(scene["id"])
                    existing = next(
                        (os.path.join(draft_dir, f) for f in os.listdir(draft_dir)
                         if f.startswith(f"scene_{scene_id:03d}") and f.lower().endswith((".png", ".jpg", ".jpeg"))),
                        None,
                    )
                    if existing:
                        self.log.emit(f"Skipping scene {scene_id} (draft already exists).")
                    else:
                        if scene_id in cached_prompts:
                            prompt = cached_prompts[scene_id]
                            self.log.emit(f"Scene {scene_id}: using cached prompt.")
                        else:
                            prompt = prompt_builder.build_prompt(scene)
                            cached_prompts[scene_id] = prompt
                            with open(prompts_path, "w", encoding="utf-8") as fh:
                                yaml.safe_dump(cached_prompts, fh, allow_unicode=True, sort_keys=False)
                        image_gen.generate_image(prompt, scene_id)
                    step = 30 + int((index / total_scenes) * 70)
                    self._emit_progress(step, f"Draft image {index}/{total_scenes}")

                self._emit_progress(100, "Draft preview ready")
                self.finished.emit(True, draft_dir)
                return

            if stage in {"full", "images"}:
                from images.image_generator import ImageGenerator

                self._check_cancel()
                self._emit_progress(25, "Building prompts")
                prompt_builder = PromptBuilder(
                    style_preset=self.config.get("style_preset", "cinematic"),
                    default_aspect_ratio=self.config.get("aspect_ratio", "16:9"),
                    use_ollama=bool(self.config.get("use_ollama", False)),
                    ollama_model=str(self.config.get("ollama_model", "llama3")),
                    ollama_host=str(self.config.get("ollama_host", "http://localhost:11434")),
                )
                if prompt_builder._enhancer:
                    if prompt_builder._enhancer.is_available():
                        self.log.emit("Ollama prompt enhancement: ACTIVE")
                    else:
                        self.log.emit("Ollama not available — using rule-based prompts.")

                self._check_cancel()
                self._emit_progress(30, "Generating scene images")

                self._check_cancel()
                self._emit_progress(30, "Generating scene images")
                image_gen = ImageGenerator(
                    model_path=self._resolve_path(self.config.get("sdxl_base", "models/sd3")),
                    output_dir=images_dir,
                    guidance_scale=float(self.config.get("guidance_scale", 7.5)),
                    num_inference_steps=int(self.config.get("num_inference_steps", 30)),
                    seed=int(self.config.get("seed", 42)),
                )

                prompts_path = os.path.join(self.project_path, "output", "prompts.yaml")
                cached_prompts: dict = {}
                if os.path.exists(prompts_path):
                    with open(prompts_path, "r", encoding="utf-8") as fh:
                        cached_prompts = yaml.safe_load(fh) or {}
                    self.log.emit(f"Loaded {len(cached_prompts)} cached prompt(s) from prompts.yaml")

                total_scenes = len(scenes)
                for index, scene in enumerate(scenes, start=1):
                    self._check_cancel()
                    scene_id = int(scene["id"])
                    if scene_id in cached_prompts:
                        prompt = cached_prompts[scene_id]
                        self.log.emit(f"Scene {scene_id}: using cached prompt.")
                    else:
                        prompt = prompt_builder.build_prompt(scene)
                        cached_prompts[scene_id] = prompt
                        with open(prompts_path, "w", encoding="utf-8") as fh:
                            yaml.safe_dump(cached_prompts, fh, allow_unicode=True, sort_keys=False)
                    image_gen.generate_image(prompt, scene_id)
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
                self._check_cancel()
                self._emit_progress(55 if stage == "full" else 10, "Generating video clips")
                image_paths = self._scene_image_candidates(images_dir)
                if not image_paths:
                    raise FileNotFoundError(
                        f"No scene images found in {images_dir}. Run image generation first."
                    )

                clip_engine = self.config.get("clip_engine", "ken_burns")
                self.log.emit(f"Clip engine: {clip_engine}")

                # Load per-scene audio timings — from timings.yaml if present,
                # otherwise measure MP3 durations directly from the audio folder.
                scene_timings: dict = {}
                if os.path.exists(timings_path):
                    with open(timings_path, "r", encoding="utf-8") as fh:
                        scene_timings = yaml.safe_load(fh) or {}
                    self.log.emit(f"Loaded audio timings for {len(scene_timings)} scene(s).")
                elif os.path.isdir(tts_dir):
                    self.log.emit("timings.yaml not found — measuring MP3 durations directly.")
                    for mp3 in os.listdir(tts_dir):
                        if not mp3.startswith("scene_") or not mp3.endswith(".mp3"):
                            continue
                        try:
                            sid = int(mp3[6:9])
                        except ValueError:
                            continue
                        mp3_path = os.path.join(tts_dir, mp3)
                        try:
                            from mutagen.mp3 import MP3
                            scene_timings[sid] = MP3(mp3_path).info.length
                        except Exception:
                            try:
                                from moviepy import AudioFileClip as _AFC
                                c = _AFC(mp3_path); scene_timings[sid] = c.duration; c.close()
                            except Exception:
                                pass
                    if scene_timings:
                        with open(timings_path, "w", encoding="utf-8") as fh:
                            yaml.safe_dump(scene_timings, fh, sort_keys=True)
                        self.log.emit(f"Measured and saved timings for {len(scene_timings)} scene(s).")

                if clip_engine == "ken_burns":
                    from video.ken_burns_generator import KenBurnsGenerator
                    default_duration = float(self.config.get("ken_burns_duration", 4.0))
                    generator = KenBurnsGenerator(
                        output_dir=clips_dir,
                        fps=int(self.config.get("ken_burns_fps", 24)),
                        duration=default_duration,
                        seed=int(self.config.get("seed", 42)),
                    )
                else:
                    from video.video_generator import VideoGenerator
                    generator = VideoGenerator(
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
                    existing_clip = os.path.join(clips_dir, f"scene_{scene_id:03d}.mp4")
                    if os.path.exists(existing_clip):
                        self.log.emit(f"Skipping clip {scene_id} (already exists).")
                        action = f"Skipped clip {index}/{total_images}"
                    else:
                        # Use audio duration for this scene if available (Ken Burns only)
                        if clip_engine == "ken_burns" and scene_id in scene_timings:
                            generator.duration = float(scene_timings[scene_id])
                            self.log.emit(f"Scene {scene_id}: clip duration = {generator.duration:.1f}s (from TTS)")
                        generator.generate_clip(image_path, scene_id)
                        action = f"Generated clip {index}/{total_images}"
                    if stage == "full":
                        step = 55 + int((index / total_images) * 25)
                    else:
                        step = 10 + int((index / total_images) * 80)
                    self._emit_progress(step, action)

                if stage == "clips":
                    self._emit_progress(100, "Clip generation complete")
                    self.finished.emit(True, clips_dir)
                    return

            if stage in {"full", "assemble"}:
                from video.clip_assembler import ClipAssembler

                self._check_cancel()
                base = 82 if stage == "full" else 20
                self._emit_progress(base, "Loading clips…")
                assembler = ClipAssembler(final_video_path, fps=int(self.config.get("ken_burns_fps", 24)))

                def _on_clip_loaded(loaded, total):
                    step = base + int((loaded / total) * 15)
                    self._emit_progress(step, f"Loading clip {loaded}/{total}…")

                assembler.assemble(clips_dir, on_progress=_on_clip_loaded)
                self._emit_progress(base + 15, "Writing final video…")

                if stage == "assemble":
                    self._emit_progress(100, "Assemble complete")
                    self.finished.emit(True, final_video_path)
                    return

            if stage in {"full", "audio"}:
                from video.audio_sync import AudioSync
                from moviepy import AudioFileClip, concatenate_audioclips

                self._check_cancel()
                self._emit_progress(92 if stage == "full" else 10, "Baking narration audio")
                if not os.path.exists(final_video_path):
                    raise FileNotFoundError(
                        f"Final video not found at {final_video_path}. Run assemble stage first."
                    )

                # Build concatenated audio from per-scene TTS files
                tts_files = sorted([
                    os.path.join(tts_dir, f)
                    for f in os.listdir(tts_dir)
                    if f.startswith("scene_") and f.endswith(".mp3")
                ]) if os.path.isdir(tts_dir) else []

                if tts_files:
                    self.log.emit(f"Concatenating {len(tts_files)} TTS audio file(s)…")
                    clips = [AudioFileClip(p) for p in tts_files]
                    combined = concatenate_audioclips(clips)
                    combined_path = os.path.join(final_dir, "narration_combined.mp3")
                    combined.write_audiofile(combined_path, logger=None)
                    for c in clips:
                        c.close()
                    combined.close()
                    audio_source = combined_path
                    self.log.emit(f"Combined audio: {combined_path}")
                elif os.path.exists(input_audio):
                    audio_source = input_audio
                    self.log.emit("No TTS audio found — using input/audio.wav")
                else:
                    raise FileNotFoundError(
                        "No TTS audio files found in output/audio/ and no input/audio.wav. "
                        "Run 'Synthesise Audio (TTS)' first."
                    )

                self._emit_progress(96 if stage == "full" else 60, "Merging audio with video")
                sync = AudioSync(
                    output_path=final_with_audio_path,
                    audio_volume=float(self.config.get("audio_volume", 1.0)),
                    fade_in=float(self.config.get("fade_in", 0.0)),
                    fade_out=float(self.config.get("fade_out", 0.5)),
                )
                sync.merge(final_video_path, audio_source)

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
        ("Full Pipeline",          "full"),
        ("Draft Preview",          "draft"),
        ("Load Narration",         "narration"),
        ("Split Scenes",           "scenes"),
        ("Synthesise Audio (TTS)", "tts"),
        ("Generate Images",        "images"),
        ("Generate Clips",         "clips"),
        ("Assemble Video",         "assemble"),
        ("Sync Audio",             "audio"),
    ]

    DEFAULT_SETTINGS = {
        "style_preset": "cinematic",
        "aspect_ratio": "16:9",
        "seed": 42,
        "fps": 8,
        "scene_split_method": "paragraph",
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
        "clip_engine": "ken_burns",
        "ken_burns_duration": 4.0,
        "ken_burns_fps": 24,
        "tts_voice": "it-IT-DiegoNeural",
        "tts_rate": "+0%",
        "tts_pitch": "+0Hz",
        "tts_volume": "+0%",
        "use_ollama": False,
        "ollama_model": "llama3",
        "ollama_host": "http://localhost:11434",
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

    def run_pipeline(self, stage: str = "full", extra_config: dict = None) -> None:
        if self._thread is not None:
            self.log.warning("Pipeline is already running.")
            return

        if not self.project_path:
            error = "No project path set."
            self.log.error(error)
            self.pipeline_finished.emit(False, error)
            return

        merged_config = dict(self.config)
        if extra_config:
            merged_config.update(extra_config)

        self._thread = QThread()
        self._worker = PipelineWorker(self.project_path, merged_config, self.root_dir, stage=stage)
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
