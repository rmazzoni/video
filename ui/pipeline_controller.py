import glob
import os
import shutil
from typing import Dict, List, Optional, Tuple

import yaml
from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot

from narration.transcript_loader import TranscriptLoader
from narration.scene_splitter import SceneSplitter
from prompts.prompt_builder import PromptBuilder, structure_prompt_for_model
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
            if stage not in {"narration", "scenes", "prompts", "tts",
                             "preview_images", "preview_clips", "preview_video",
                             "final_images", "final_clips", "final_video"}:                raise ValueError(f"Unknown stage: {stage}")

            # Force-release any GPU memory left over from a previous pipeline run
            # before loading new models.  This handles the case where unload() in
            # a prior run failed to free everything (e.g. lingering Python refs).
            import gc as _gc
            _gc.collect()
            try:
                import torch as _t
                if _t.cuda.is_available():
                    _t.cuda.empty_cache()
                    _t.cuda.synchronize()
                    _gc.collect()
                    alloc = _t.cuda.memory_allocated() / 1024**3
                    if alloc > 0.5:
                        self.log.emit(f"âš  VRAM start: {alloc:.2f} GiB still allocated from previous run â€” forcing further cleanup")
                        # Walk all live Python objects and delete any torch modules
                        import sys
                        for obj in list(_gc.get_objects()):
                            try:
                                if isinstance(obj, _t.nn.Module):
                                    for p in list(obj.parameters()):
                                        if p.is_cuda:
                                            p.data = p.data.cpu()
                            except Exception:
                                pass
                        _gc.collect()
                        _t.cuda.empty_cache()
                    alloc2 = _t.cuda.memory_allocated() / 1024**3
                    self.log.emit(f"VRAM at stage start: {alloc2:.2f} GiB allocated")
            except Exception:
                pass

            def _log_vram(label: str = "") -> None:
                try:
                    import torch as _t
                    if _t.cuda.is_available():
                        alloc = _t.cuda.memory_allocated() / 1024**3
                        reserved = _t.cuda.memory_reserved() / 1024**3
                        self.log.emit(f"VRAM {label}: {alloc:.2f} GiB allocated, {reserved:.2f} GiB reserved")
                except Exception:
                    pass

            input_text = os.path.join(self.project_path, "input", "narration.txt")
            input_audio = os.path.join(self.project_path, "input", "audio.wav")
            tts_dir = os.path.join(self.project_path, "output", "audio")
            timings_path = os.path.join(tts_dir, "timings.yaml")
            draft_dir = os.path.join(self.project_path, "output", "draft")
            draft_clips_dir = os.path.join(self.project_path, "output", "draft_clips")
            preview_dir = os.path.join(self.project_path, "output", "preview")
            images_dir = os.path.join(self.project_path, "output", "images")
            lightbox_dir = os.path.join(self.project_path, "output", "lightbox")
            clips_dir = os.path.join(self.project_path, "output", "clips")
            final_dir = os.path.join(self.project_path, "output", "final")
            scenes_path = os.path.join(self.project_path, "output", "scenes.yaml")
            preview_video_path = os.path.join(preview_dir, "preview_video.mp4")
            preview_with_audio_path = os.path.join(preview_dir, "preview_with_audio.mp4")
            final_video_path = os.path.join(final_dir, "final_video.mp4")
            final_with_audio_path = os.path.join(final_dir, "final_with_audio.mp4")

            os.makedirs(draft_dir, exist_ok=True)
            os.makedirs(draft_clips_dir, exist_ok=True)
            os.makedirs(preview_dir, exist_ok=True)
            os.makedirs(images_dir, exist_ok=True)
            os.makedirs(lightbox_dir, exist_ok=True)
            os.makedirs(clips_dir, exist_ok=True)
            os.makedirs(final_dir, exist_ok=True)

            narration_text = ""
            scenes = []

            if stage in {"narration", "scenes", "prompts", "tts"}:
                self._check_cancel()
                self._emit_progress(5, "Loading narration")
                narration_text = TranscriptLoader().load(input_text)
                self.log.emit("Narration loaded.")

                if stage == "narration":
                    self._emit_progress(100, "Narration loaded")
                    self.finished.emit(True, input_text)
                    return

            if stage in {"scenes", "prompts", "tts"}:
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

            if stage == "prompts":
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
                        self.log.emit("Ollama not available â€” using rule-based prompts.")
                prompts_path = os.path.join(self.project_path, "output", "prompts.yaml")
                cached_prompts: dict = {}
                if os.path.exists(prompts_path):
                    with open(prompts_path, "r", encoding="utf-8") as fh:
                        cached_prompts = yaml.safe_load(fh) or {}
                    self.log.emit(f"Loaded {len(cached_prompts)} cached prompt(s).")
                total_scenes = len(scenes)
                new_count = 0
                for index, scene in enumerate(scenes, start=1):
                    self._check_cancel()
                    scene_id = int(scene["id"])
                    if scene_id in cached_prompts:
                        self.log.emit(f"Scene {scene_id}: using cached prompt.")
                    else:
                        prompt = prompt_builder.build_prompt(scene)
                        cached_prompts[scene_id] = prompt
                        new_count += 1
                        self.log.emit(f"Scene {scene_id}: generated prompt.")
                        with open(prompts_path, "w", encoding="utf-8") as fh:
                            yaml.safe_dump(cached_prompts, fh, allow_unicode=True, sort_keys=False)
                    self._emit_progress(30 + int((index / total_scenes) * 70),
                                        f"Prompts {index}/{total_scenes}")
                self.log.emit(f"Prompts done. {new_count} new, {total_scenes - new_count} cached.")
                self._emit_progress(100, "Prompts ready")
                self.finished.emit(True, prompts_path)
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

            # â”€â”€ Helper: build image generator for a given model type â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            def _make_image_gen(model_type: str, output_dir: str):
                if model_type == "flux-schnell":
                    model_path = self.config.get("flux_schnell", "models/flux/FLUX.1-schnell")
                    steps = int(self.config.get("schnell_steps", 4))
                    guidance = float(self.config.get("schnell_guidance", 0.0))
                elif model_type == "flux-dev":
                    model_path = self.config.get("flux_dev", "models/flux/FLUX.1-dev")
                    steps = int(self.config.get("dev_steps", 20))
                    guidance = float(self.config.get("dev_guidance", 3.5))
                elif model_type == "flux2":
                    model_path = self.config.get("flux2", "models/flux/FLUX.2-klein-4B")
                    steps = int(self.config.get("flux2_steps", 4))
                    guidance = float(self.config.get("flux2_guidance", 1.0))
                else:
                    model_path = self.config.get("sdxl_base", "models/sd3")
                    steps = int(self.config.get("num_inference_steps", 30))
                    guidance = float(self.config.get("guidance_scale", 7.5))
                self.log.emit(f"Image model: {model_type}  steps={steps}  guidance={guidance}")
                from images.image_generator import ImageGenerator
                return ImageGenerator(
                    model_path=self._resolve_path(model_path),
                    model_type=model_type,
                    output_dir=output_dir,
                    guidance_scale=guidance,
                    num_inference_steps=steps,
                    seed=int(self.config.get("seed", 42)),
                    width=int(self.config.get("image_width", 1024)),
                    height=int(self.config.get("image_height", 576)),
                )

            # â”€â”€ Helper: load scene_timings from timings.yaml or measure MP3s â”€â”€
            def _load_scene_timings() -> dict:
                scene_timings: dict = {}
                if os.path.exists(timings_path):
                    with open(timings_path, "r", encoding="utf-8") as fh:
                        scene_timings = yaml.safe_load(fh) or {}
                    scene_timings = {int(k): float(v) for k, v in scene_timings.items()}
                if not scene_timings and os.path.isdir(tts_dir):
                    for f in os.listdir(tts_dir):
                        if f.startswith("scene_") and f.endswith(".mp3"):
                            try:
                                sid = int(f.split("_")[1].split(".")[0])
                            except ValueError:
                                continue
                            mp3_path = os.path.join(tts_dir, f)
                            try:
                                import mutagen.mp3
                                audio = mutagen.mp3.MP3(mp3_path)
                                scene_timings[sid] = audio.info.length
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
                return scene_timings

            # â”€â”€ Helper: generate clips from an image dir into a clip dir â”€â”€â”€â”€â”€â”€
            def _run_clips(src_images_dir: str, out_clips_dir: str, timings: dict):
                os.makedirs(out_clips_dir, exist_ok=True)
                image_paths = self._scene_image_candidates(src_images_dir)
                if not image_paths:
                    raise FileNotFoundError(f"No scene images found in {src_images_dir}.")

                clip_engine = str(self.config.get("clip_engine", "ken_burns")).strip().lower()

                if clip_engine == "ken_burns":
                    from video.ken_burns_generator import KenBurnsGenerator
                    default_dur = float(self.config.get("ken_burns_duration", 5.0))
                    current_motion = str(self.config.get("ken_burns_motion", "static"))
                    current_fps    = 24  # Ken Burns always renders at 24fps for smooth motion

                    # ── Parameter sidecar ────────────────────────────────────
                    # Store the generation params used last time so that a
                    # settings change (e.g. auto→static) forces a full re-render
                    # even when source images haven't been touched.
                    sidecar_path = os.path.join(out_clips_dir, ".kb_params.yaml")
                    prev_params: dict = {}
                    if os.path.exists(sidecar_path):
                        try:
                            with open(sidecar_path, "r", encoding="utf-8") as _f:
                                prev_params = yaml.safe_load(_f) or {}
                        except Exception:
                            pass
                    cur_params = {"motion_style": current_motion, "fps": current_fps,
                                  "engine": "ken_burns"}
                    params_changed = (prev_params != cur_params)
                    self.log.emit(
                        f"Ken Burns clip engine — motion_style={current_motion!r}  fps={current_fps}"
                        + ("  ⚠ params changed, all clips will be regenerated" if params_changed else "")
                    )

                    gen_kb = KenBurnsGenerator(
                        output_dir=out_clips_dir,
                        fps=current_fps,
                        duration=default_dur,
                        seed=int(self.config.get("seed", 42)),
                        motion_style=current_motion,
                    )
                    total = len(image_paths)
                    failed_kb: list = []
                    for idx, img_path in enumerate(image_paths, 1):
                        self._check_cancel()
                        sid = self._extract_scene_id(img_path)
                        existing = os.path.join(out_clips_dir, f"scene_{sid:03d}.mp4")
                        up_to_date = (
                            os.path.exists(existing)
                            and os.path.getmtime(existing) >= os.path.getmtime(img_path)
                            and not params_changed
                        )
                        if up_to_date:
                            self.log.emit(f"Skipping clip {sid} (already exists and up to date).")
                        else:
                            target_dur = float(timings[sid]) if sid in timings else default_dur
                            gen_kb.duration = target_dur
                            self.log.emit(f"Scene {sid}: Ken Burns clip [{current_motion}], duration={target_dur:.1f}s")
                            try:
                                gen_kb.generate_clip(img_path, sid)
                            except Exception as _clip_err:
                                self.log.emit(f"WARNING: clip {sid} failed — {_clip_err}")
                                failed_kb.append(sid)
                        step = 10 + int((idx / total) * 80)
                        self._emit_progress(step, f"Clip {idx}/{total}")
                    if failed_kb:
                        self.log.emit(f"Ken Burns: {len(failed_kb)} clip(s) failed and were skipped: {failed_kb}")
                    # Persist current params so the next run can detect changes
                    try:
                        os.makedirs(out_clips_dir, exist_ok=True)
                        with open(sidecar_path, "w", encoding="utf-8") as _f:
                            yaml.safe_dump(cur_params, _f)
                    except Exception:
                        pass
                else:
                    from video.video_generator import VideoGenerator
                    gen = VideoGenerator(
                        model_path=self._resolve_path(self.config.get("svd", "models/svd")),
                        output_dir=out_clips_dir,
                        num_frames=int(self.config.get("num_frames", 25)),
                        motion_bucket_id=int(self.config.get("motion_bucket_id", 40)),
                        fps=int(self.config.get("fps", 8)),
                        decode_chunk_size=int(self.config.get("decode_chunk_size", 4)),
                        noise_aug_strength=float(self.config.get("noise_aug_strength", 0.0)),
                        seed=int(self.config.get("seed", 42)),
                    )
                    overrides_path = os.path.join(self.project_path, "output", "scene_overrides.yaml")
                    scene_overrides: dict = {}
                    if os.path.exists(overrides_path):
                        with open(overrides_path, "r", encoding="utf-8") as fh:
                            scene_overrides = yaml.safe_load(fh) or {}

                    total = len(image_paths)
                    failed: list = []
                    for idx, img_path in enumerate(image_paths, 1):
                        self._check_cancel()
                        sid = self._extract_scene_id(img_path)
                        existing = os.path.join(out_clips_dir, f"scene_{sid:03d}.mp4")
                        if os.path.exists(existing) and os.path.getmtime(existing) >= os.path.getmtime(img_path):
                            self.log.emit(f"Skipping clip {sid} (already exists and up to date.).")
                        else:
                            target_dur = float(timings[sid]) if sid in timings else None
                            if target_dur:
                                self.log.emit(f"Scene {sid}: target duration = {target_dur:.1f}s")
                            ov = scene_overrides.get(sid, scene_overrides.get(str(sid), {}))
                            try:
                                gen.generate_clip(
                                    img_path, sid,
                                    motion_bucket_id=ov.get("motion_bucket_id") if ov else None,
                                    noise_aug_strength=ov.get("noise_aug_strength") if ov else None,
                                    target_duration=target_dur,
                                )
                            except Exception as _clip_err:
                                self.log.emit(f"WARNING: clip {sid} failed — {_clip_err}")
                                failed.append(sid)
                        step = 10 + int((idx / total) * 80)
                        self._emit_progress(step, f"Clip {idx}/{total}")
                    if failed:
                        self.log.emit(f"SVD: {len(failed)} clip(s) failed and were skipped: {failed}")
                    _log_vram("before clip gen unload")
                    gen.unload()
                    _log_vram("after clip gen unload")

            # ── Helper: pad audio/video edges so words aren't clipped ────────
            # -shortest muxing (or an over-eager silence trim) can shave a hair
            # off the first/last word if audio and video start/end at exactly
            # the same instant. Add a small fixed silence/freeze margin instead.
            AUDIO_LEAD_IN_S = 0.5
            AUDIO_TRAIL_OUT_S = 0.5

            def _probe_duration(path: str) -> float:
                import subprocess
                try:
                    p = subprocess.run(
                        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                         "-of", "default=noprint_wrappers=1:nokey=1", path],
                        capture_output=True, text=True,
                    )
                    return float(p.stdout.strip())
                except Exception:
                    return -1.0

            def _pad_audio_edges(path: str, lead_s: float, trail_s: float) -> None:
                import subprocess
                tmp = path + ".padded" + os.path.splitext(path)[1]
                filt = f"adelay={int(lead_s * 1000)}:all=1,apad=pad_dur={trail_s}"
                result = subprocess.run(
                    ["ffmpeg", "-y", "-i", path, "-af", filt, tmp],
                    capture_output=True, text=True,
                )
                if result.returncode != 0 or not os.path.exists(tmp) or os.path.getsize(tmp) == 0:
                    raise RuntimeError(f"FFmpeg audio edge padding failed:\n{result.stderr[-1000:]}")
                os.replace(tmp, path)

            def _pad_video_edges(path: str, lead_s: float, trail_s: float) -> None:
                import subprocess
                tmp = path + ".padded.mp4"
                # Must be ONE tpad filter instance, not two chained tpad filters —
                # chaining two separate tpad calls drops frames at the boundary
                # between them and silently loses most of the intended padding.
                vf = f"tpad=start_duration={lead_s}:start_mode=clone:stop_duration={trail_s}:stop_mode=clone"
                result = subprocess.run(
                    ["ffmpeg", "-y", "-i", path, "-vf", vf,
                     "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-an", tmp],
                    capture_output=True, text=True,
                )
                if result.returncode != 0 or not os.path.exists(tmp) or os.path.getsize(tmp) == 0:
                    raise RuntimeError(f"FFmpeg video edge padding failed:\n{result.stderr[-1000:]}")
                os.replace(tmp, path)

            # ── Helper: assemble clips + audio into a video ───────────────
            def _run_assemble(clips_d: str, video_out: str, audio_out: str,
                              resolution: tuple, normalize_audio: bool = False):
                from video.clip_assembler import ClipAssembler
                from video.audio_sync import AudioSync

                # This helper is the entire body of work for the preview_video /
                # final_video stages, so its own progress spans the full 0-100%
                # range: assembling clips takes the bulk (0-85%), then audio
                # merge/equalization get the remaining allowance up to 100%.
                self._emit_progress(0, "Assembling clips...")
                assembler = ClipAssembler(video_out, fps=int(self.config.get("fps", 24)),
                                          target_resolution=resolution)

                def _assemble_progress(pct: float, _total: int) -> None:
                    self._emit_progress(int(pct * 0.85), f"Assembling clips... {int(pct)}%")

                assembler.assemble(clips_d, on_progress=_assemble_progress)
                _before_v = _probe_duration(video_out)
                _pad_video_edges(video_out, AUDIO_LEAD_IN_S, AUDIO_TRAIL_OUT_S)
                _after_v = _probe_duration(video_out)
                self.log.emit(f"Video edge padding: {_before_v:.3f}s -> {_after_v:.3f}s")
                self._emit_progress(85, "Merging audio...")

                tts_files = sorted([
                    os.path.join(tts_dir, f)
                    for f in os.listdir(tts_dir)
                    if f.startswith("scene_") and f.endswith(".mp3")
                ]) if os.path.isdir(tts_dir) else []

                if tts_files:
                    # Use ffmpeg concat demuxer directly to avoid MoviePy's
                    # frame-iterator over-read bug on long audio files.
                    import subprocess, tempfile
                    audio_name = "final_audio.mp3" if normalize_audio else "narration_combined.mp3"
                    combined_path = os.path.join(os.path.dirname(audio_out), audio_name)
                    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                                    delete=False, encoding="utf-8") as flist:
                        for p in tts_files:
                            flist.write(f"file '{p.replace(chr(39), chr(39)+chr(92)+chr(39)+chr(39))}'\n")
                        flist_path = flist.name
                    try:
                        subprocess.run(
                            ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                             "-i", flist_path, "-c", "copy", combined_path],
                            check=True, capture_output=True,
                        )
                    finally:
                        os.unlink(flist_path)
                    audio_src = combined_path
                elif os.path.exists(input_audio):
                    if normalize_audio:
                        extension = os.path.splitext(input_audio)[1]
                        audio_src = os.path.join(os.path.dirname(audio_out), f"final_audio{extension}")
                        shutil.copy2(input_audio, audio_src)
                    else:
                        audio_src = input_audio
                else:
                    raise FileNotFoundError("No TTS audio found. Run Synthesise Audio first.")

                if normalize_audio:
                    from audio_loudness import normalize_loudness_in_place

                    self._emit_progress(90, "Equalizing final audio loudness...")
                    result = normalize_loudness_in_place(audio_src, target_lufs=-17.0, trim_silence=False)
                    if not result.success:
                        raise RuntimeError(f"Audio normalization failed: {result.error}")
                    self.log.emit(f"Normalized final audio to -17 LUFS: {audio_src}")

                _before_a = _probe_duration(audio_src)
                _pad_audio_edges(audio_src, AUDIO_LEAD_IN_S, AUDIO_TRAIL_OUT_S)
                _after_a = _probe_duration(audio_src)
                self.log.emit(f"Audio edge padding: {_before_a:.3f}s -> {_after_a:.3f}s")
                self._emit_progress(97, "Muxing final video...")
                sync = AudioSync(
                    output_path=audio_out,
                    audio_volume=float(self.config.get("audio_volume", 1.0)),
                    fade_in=float(self.config.get("fade_in", 0.0)),
                    fade_out=float(self.config.get("fade_out", 0.0)),
                )
                sync.merge(video_out, audio_src)
                self.log.emit(
                    f"Final mux inputs: video={_probe_duration(video_out):.3f}s "
                    f"audio={_probe_duration(audio_src):.3f}s "
                    f"output={_probe_duration(audio_out):.3f}s"
                )

            # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            # STAGE: preview_images  â€” FLUX schnell â†’ output/draft/
            # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            if stage == "preview_images":
                self._check_cancel()
                self._emit_progress(10, "Generating preview images (FLUX schnell)")

                # Load scenes from scenes.yaml
                if os.path.exists(scenes_path):
                    with open(scenes_path, "r", encoding="utf-8") as fh:
                        scenes = (yaml.safe_load(fh) or {}).get("scenes", scenes)

                prompts_path = os.path.join(self.project_path, "output", "prompts.yaml")
                cached_prompts: dict = {}
                if os.path.exists(prompts_path):
                    with open(prompts_path, "r", encoding="utf-8") as fh:
                        cached_prompts = yaml.safe_load(fh) or {}

                # Scan existing draft images
                existing_drafts: set = set()
                if os.path.isdir(draft_dir):
                    for f in os.listdir(draft_dir):
                        if f.startswith("scene_") and f.lower().endswith((".png", ".jpg", ".jpeg")):
                            try:
                                existing_drafts.add(int(f.split("_")[1].split(".")[0]))
                            except (IndexError, ValueError):
                                pass

                scenes_needed = [s for s in scenes if int(s["id"]) not in existing_drafts]
                if not scenes_needed:
                    self.log.emit("All preview images already exist â€” skipping.")
                    self._emit_progress(100, "Preview images up to date")
                    self.finished.emit(True, draft_dir)
                    return

                # Generate missing prompts
                scenes_no_prompt = [s for s in scenes_needed
                                    if int(s["id"]) not in cached_prompts]
                if scenes_no_prompt:
                    prompt_builder = PromptBuilder(
                        style_preset=self.config.get("style_preset", "cinematic"),
                        default_aspect_ratio=self.config.get("aspect_ratio", "16:9"),
                        use_ollama=bool(self.config.get("use_ollama", False)),
                        ollama_model=str(self.config.get("ollama_model", "llama3")),
                        ollama_host=str(self.config.get("ollama_host", "http://localhost:11434")),
                    )
                    for s in scenes_no_prompt:
                        cached_prompts[int(s["id"])] = prompt_builder.build_prompt(s)
                    with open(prompts_path, "w", encoding="utf-8") as fh:
                        yaml.safe_dump(cached_prompts, fh, allow_unicode=True, sort_keys=False)
                    # Unload Ollama
                    try:
                        import urllib.request, json as _json
                        _host = str(self.config.get("ollama_host", "http://localhost:11434"))
                        _payload = _json.dumps({"model": str(self.config.get("ollama_model", "llama3")), "keep_alive": 0}).encode()
                        req = urllib.request.Request(f"{_host}/api/generate", data=_payload,
                                                     headers={"Content-Type": "application/json"}, method="POST")
                        urllib.request.urlopen(req, timeout=10)
                    except Exception as _e:
                        self.log.emit(f"Ollama unload skipped ({_e})")

                image_gen = _make_image_gen("flux-schnell", draft_dir)
                total = len(scenes_needed)
                for idx, scene in enumerate(scenes_needed, 1):
                    self._check_cancel()
                    sid = int(scene["id"])
                    prompt = cached_prompts.get(sid) or scene.get("text", "")
                    self.log.emit(f"Scene {sid}: generating preview imageâ€¦")
                    image_gen.generate_image(prompt, sid)
                    self._emit_progress(10 + int((idx / total) * 85), f"Preview image {idx}/{total}")

                _log_vram("before preview_images unload")
                image_gen.unload()
                _log_vram("after preview_images unload")
                self._emit_progress(100, "Preview images complete")
                self.finished.emit(True, draft_dir)
                return

            # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            # STAGE: preview_clips  â€” SVD from draft images â†’ output/draft_clips/
            # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            if stage == "preview_clips":
                self._check_cancel()
                self._emit_progress(5, "Generating preview clips")
                scene_timings = _load_scene_timings()
                _run_clips(draft_dir, draft_clips_dir, scene_timings)
                self._emit_progress(100, "Preview clips complete")
                self.finished.emit(True, draft_clips_dir)
                return

            # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            # STAGE: preview_video  â€” assemble draft clips at 1024Ã—576
            # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            if stage == "preview_video":
                self._check_cancel()
                _run_assemble(draft_clips_dir, preview_video_path, preview_with_audio_path,
                              resolution=(1024, 576))
                self._emit_progress(100, "Preview video complete")
                self.finished.emit(True, preview_with_audio_path)
                return

            # ─────────────────────────────────────────────────────────────────
            # STAGE: final_images  – 3 variants per model → output/lightbox/
            # ─────────────────────────────────────────────────────────────────
            if stage == "final_images":
                self._check_cancel()
                self._emit_progress(5, "Generating lightbox images (Schnell + Dev + FLUX.2)")

                if os.path.exists(scenes_path):
                    with open(scenes_path, "r", encoding="utf-8") as fh:
                        scenes = (yaml.safe_load(fh) or {}).get("scenes", scenes)

                prompts_path = os.path.join(self.project_path, "output", "prompts.yaml")
                cached_prompts = {}
                if os.path.exists(prompts_path):
                    with open(prompts_path, "r", encoding="utf-8") as fh:
                        cached_prompts = yaml.safe_load(fh) or {}

                base_seed = int(self.config.get("seed", 42))
                seed_offsets = [-1, 0, 1]
                model_variants = [
                    ("flux-schnell", "schnell"),
                    ("flux-dev",     "dev"),
                    ("flux2",        "flux2"),
                ]

                def _variant_path(sid, model_key, v_idx):
                    return os.path.join(lightbox_dir, f"scene_{sid:03d}_{model_key}_v{v_idx}.png")

                scenes_all = [int(s["id"]) for s in scenes]
                total_ops = len(scenes_all) * len(model_variants) * len(seed_offsets)
                done_ops = 0

                # ── Reuse existing draft images as schnell_v2 (base seed) ──────
                # Draft images (output/draft/scene_NNN.png) were already generated
                # by stage 5 using flux-schnell at the base seed.  Copy them to the
                # lightbox as schnell_v2 instead of regenerating.
                import shutil as _shutil
                copied_drafts = 0
                for scene in scenes:
                    sid = int(scene["id"])
                    dst = _variant_path(sid, "schnell", 2)   # v2 = base seed
                    if os.path.exists(dst):
                        continue
                    # Try each supported extension
                    for ext in ("png", "jpg", "jpeg"):
                        src = os.path.join(draft_dir, f"scene_{sid:03d}.{ext}")
                        if os.path.exists(src):
                            _shutil.copy2(src, dst)
                            self.log.emit(f"Scene {sid}: copied draft -> lightbox schnell_v2")
                            copied_drafts += 1
                            break
                if copied_drafts:
                    self.log.emit(f"Reused {copied_drafts} draft image(s) as schnell_v2.")

                for model_type, model_key in model_variants:
                    self._check_cancel()
                    work = []
                    for scene in scenes:
                        sid = int(scene["id"])
                        for v_idx, offset in enumerate(seed_offsets, 1):
                            out = _variant_path(sid, model_key, v_idx)
                            if not os.path.exists(out):
                                work.append((sid, v_idx, base_seed + offset, scene))
                    if not work:
                        done_ops += len(scenes_all) * len(seed_offsets)
                        self.log.emit(f"{model_key}: all variants already exist — skipping.")
                        self._emit_progress(10 + int((done_ops / total_ops) * 85),
                                            f"{model_key}: skipped (all exist)")
                        continue

                    image_gen = _make_image_gen(model_type, lightbox_dir)
                    for sid, v_idx, seed_val, scene in work:
                        self._check_cancel()
                        prompt = cached_prompts.get(sid) or cached_prompts.get(str(sid)) or scene.get("text", "")
                        prompt = structure_prompt_for_model(
                            prompt, model_type, str(self.config.get("style_preset", "cinematic")))
                        suffix = f"_{model_key}_v{v_idx}"
                        self.log.emit(f"Scene {sid} [{model_key} v{v_idx} seed={seed_val}]: generating...")
                        image_gen.generate_image(prompt, sid, seed_override=seed_val, filename_suffix=suffix)
                        done_ops += 1
                        self._emit_progress(10 + int((done_ops / total_ops) * 85),
                                            f"Lightbox {done_ops}/{total_ops}")

                    _log_vram(f"before {model_key} unload")
                    image_gen.unload()
                    _log_vram(f"after {model_key} unload")

                self._emit_progress(100, "Lightbox images complete")
                self.finished.emit(True, lightbox_dir)
                return

            # ─────────────────────────────────────────────────────────────────
            # STAGE: final_clips  – SVD from lightbox selections → output/clips/
            # ─────────────────────────────────────────────────────────────────
            if stage == "final_clips":
                self._check_cancel()
                self._emit_progress(5, "Generating final clips from lightbox selections")
                scene_timings = _load_scene_timings()

                selections_path = os.path.join(self.project_path, "output", "lightbox_selections.yaml")
                selections = {}
                if os.path.exists(selections_path):
                    with open(selections_path, "r", encoding="utf-8") as fh:
                        raw = yaml.safe_load(fh) or {}
                    selections = {int(k): v for k, v in raw.items() if isinstance(v, list) and v}

                if not selections:
                    self.log.emit("No lightbox selections found — using all available lightbox images.")
                    for fname in sorted(os.listdir(lightbox_dir)):
                        if not fname.lower().endswith(".png"):
                            continue
                        parts = fname.split("_")
                        try:
                            sid = int(parts[1])
                        except (IndexError, ValueError):
                            continue
                        selections.setdefault(sid, []).append(fname)

                if not selections:
                    raise FileNotFoundError(
                        "No lightbox images found. Run step 8 (Final Images) first.")

                clip_engine = str(self.config.get("clip_engine", "ken_burns")).strip().lower()

                all_work = []
                for sid in sorted(selections.keys()):
                    selected_fnames = selections[sid]
                    n = len(selected_fnames)
                    total_dur = float(scene_timings.get(sid, 0)) if scene_timings else 0
                    per_clip_dur = (total_dur / n) if total_dur > 0 else None
                    for v_idx, fname in enumerate(selected_fnames):
                        img_path = os.path.join(lightbox_dir, fname)
                        all_work.append((sid, v_idx, img_path, per_clip_dur))

                total = len(all_work)
                failed_fc: list = []

                if clip_engine == "ken_burns":
                    from video.ken_burns_generator import KenBurnsGenerator
                    default_dur = float(self.config.get("ken_burns_duration", 5.0))
                    gen_kb = KenBurnsGenerator(
                        output_dir=clips_dir,
                        fps=24,   # Ken Burns always renders at 24 fps; config "fps" is the SVD model rate
                        duration=default_dur,
                        seed=int(self.config.get("seed", 42)),
                        motion_style=str(self.config.get("ken_burns_motion", "auto")),
                    )
                    for idx, (sid, v_idx, img_path, per_clip_dur) in enumerate(all_work, 1):
                        self._check_cancel()
                        clip_suffix = f"_v{v_idx:02d}"
                        existing = os.path.join(clips_dir, f"scene_{sid:03d}{clip_suffix}.mp4")
                        if os.path.exists(existing) and os.path.getmtime(existing) >= os.path.getmtime(img_path):
                            self.log.emit(f"Skipping clip scene_{sid:03d}{clip_suffix} (up to date).")
                        else:
                            dur = per_clip_dur if per_clip_dur else default_dur
                            gen_kb.duration = dur
                            self.log.emit(f"Scene {sid} v{v_idx}: Ken Burns clip, duration={dur:.1f}s")
                            try:
                                gen_kb.generate_clip(img_path, sid,
                                                     filename_suffix=clip_suffix)
                            except Exception as _e:
                                self.log.emit(f"WARNING: clip scene_{sid:03d}{clip_suffix} failed — {_e}")
                                failed_fc.append(f"{sid}{clip_suffix}")
                        step = 10 + int((idx / total) * 80)
                        self._emit_progress(step, f"Clip {idx}/{total}")
                    if failed_fc:
                        self.log.emit(f"Ken Burns final: {len(failed_fc)} clip(s) failed: {failed_fc}")
                else:
                    from video.video_generator import VideoGenerator
                    gen = VideoGenerator(
                        model_path=self._resolve_path(self.config.get("svd", "models/svd")),
                        output_dir=clips_dir,
                        num_frames=int(self.config.get("num_frames", 25)),
                        motion_bucket_id=int(self.config.get("motion_bucket_id", 40)),
                        fps=int(self.config.get("fps", 8)),
                        decode_chunk_size=int(self.config.get("decode_chunk_size", 4)),
                        noise_aug_strength=float(self.config.get("noise_aug_strength", 0.0)),
                        seed=int(self.config.get("seed", 42)),
                    )
                    overrides_path = os.path.join(self.project_path, "output", "scene_overrides.yaml")
                    scene_overrides = {}
                    if os.path.exists(overrides_path):
                        with open(overrides_path, "r", encoding="utf-8") as fh:
                            scene_overrides = yaml.safe_load(fh) or {}

                    for idx, (sid, v_idx, img_path, per_clip_dur) in enumerate(all_work, 1):
                        self._check_cancel()
                        clip_suffix = f"_v{v_idx:02d}"
                        existing = os.path.join(clips_dir, f"scene_{sid:03d}{clip_suffix}.mp4")
                        if os.path.exists(existing) and os.path.getmtime(existing) >= os.path.getmtime(img_path):
                            self.log.emit(f"Skipping clip scene_{sid:03d}{clip_suffix} (up to date).")
                        else:
                            ov = scene_overrides.get(sid, scene_overrides.get(str(sid), {}))
                            if per_clip_dur:
                                self.log.emit(f"Scene {sid} v{v_idx}: target duration = {per_clip_dur:.1f}s")
                            try:
                                gen.generate_clip(
                                    img_path, sid,
                                    motion_bucket_id=ov.get("motion_bucket_id") if ov else None,
                                    noise_aug_strength=ov.get("noise_aug_strength") if ov else None,
                                    target_duration=per_clip_dur,
                                    filename_suffix=clip_suffix,
                                )
                            except Exception as _e:
                                self.log.emit(f"WARNING: clip scene_{sid:03d}{clip_suffix} failed — {_e}")
                                failed_fc.append(f"{sid}{clip_suffix}")
                        step = 10 + int((idx / total) * 80)
                        self._emit_progress(step, f"Clip {idx}/{total}")
                    if failed_fc:
                        self.log.emit(f"SVD final: {len(failed_fc)} clip(s) failed: {failed_fc}")
                    _log_vram("before final clips unload")
                    gen.unload()
                    try:
                        import time as _time
                        _time.sleep(1)
                        import torch as _t
                        if _t.cuda.is_available():
                            _t.cuda.empty_cache()
                    except Exception:
                        pass
                    _log_vram("after final clips unload")
                self._emit_progress(100, "Final clips complete")
                self.finished.emit(True, clips_dir)
                return

            # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            # STAGE: final_video  â€” assemble final clips at 1920Ã—1080
            # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            if stage == "final_video":
                self._check_cancel()
                out_w = int(self.config.get("output_width", 1920))
                out_h = int(self.config.get("output_height", 1080))
                _run_assemble(clips_dir, final_video_path, final_with_audio_path,
                              resolution=(out_w, out_h), normalize_audio=True)
                self._emit_progress(100, "Final video complete")
                self.finished.emit(True, final_with_audio_path)
                return

            self._emit_progress(100, "Stage complete")
            self.finished.emit(True, "")
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
        ("1. Load Narration",          "narration"),
        ("2. Split Scenes",            "scenes"),
        ("3. Build Prompts",           "prompts"),
        ("4. Synthesise Audio (TTS)",  "tts"),
        ("5. Preview Images (Schnell)", "preview_images"),
        ("6. Preview Clips",           "preview_clips"),
        ("7. Preview Video",           "preview_video"),
        ("8. Final Images (Dev + FLUX.2)", "final_images"),
        ("9. Final Clips",             "final_clips"),
        ("10. Final Video",            "final_video"),
    ]

    DEFAULT_SETTINGS = {
        "style_preset": "cinematic",
        "aspect_ratio": "16:9",
        "seed": 42,
        "fps": 8,
        "output_width": 1920,
        "output_height": 1080,
        "scene_split_method": "paragraph",
        "min_sentence_length": 20,
        "sdxl_base": "models/sd3",
        "svd": "models/svd",
        "flux_dev": "models/flux/FLUX.1-dev",
        "flux_schnell": "models/flux/FLUX.1-schnell",
        "flux2": "models/flux/FLUX.2-klein-4B",
        "guidance_scale": 7.5,
        "num_inference_steps": 30,
        "schnell_steps": 4,
        "schnell_guidance": 0.0,
        "dev_steps": 20,
        "dev_guidance": 3.5,
        "flux2_steps": 4,
        "flux2_guidance": 1.0,
        "image_width": 1344,
        "image_height": 768,
        "image_model": "sdxl",
        "num_frames": 14,
        "motion_bucket_id": 127,
        "audio_volume": 1.0,
        "fade_in": 0.0,
        "fade_out": 0.0,
        "clip_engine": "ken_burns",
        "ken_burns_motion": "static",
        "decode_chunk_size": 4,
        "noise_aug_strength": 0.0,
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
        # Clear Python references only after the thread event loop has fully
        # stopped.  Clearing them earlier (on worker.finished) drops the
        # refcount to zero and lets Python destroy the C++ QThread while the
        # OS thread is still alive — producing the
        # "QThread: Destroyed while thread is still running" crash.
        self._thread.finished.connect(self._clear_pipeline_refs)
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
        # Do NOT null self._thread / self._worker here — the OS thread is still
        # winding down.  Reference cleanup happens in _clear_pipeline_refs which
        # is connected to thread.finished (fires after the thread has stopped).

    @pyqtSlot()
    def _clear_pipeline_refs(self) -> None:
        """Release thread/worker references once the thread has fully stopped."""
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
