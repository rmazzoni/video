import os
from narration.scene_splitter import SceneSplitter
from prompts.prompt_builder import PromptBuilder
from images.image_generator import ImageGenerator
from video.video_generator import VideoGenerator
from video.clip_assembler import ClipAssembler
from video.audio_sync import AudioSync


def run_pipeline(project_path: str):
    """
    Full end-to-end pipeline:
    narration → scenes → prompts → images → clips → final video → audio sync
    """

    # ---------------------------------------------------------
    # PATHS
    # ---------------------------------------------------------
    input_text = os.path.join(project_path, "input", "narration.txt")
    input_audio = os.path.join(project_path, "input", "audio.wav")

    images_dir = os.path.join(project_path, "output", "images")
    clips_dir = os.path.join(project_path, "output", "clips")
    final_video_path = os.path.join(project_path, "output", "final", "final_video.mp4")
    final_with_audio_path = os.path.join(project_path, "output", "final", "final_with_audio.mp4")

    # Ensure output folders exist
    os.makedirs(images_dir, exist_ok=True)
    os.makedirs(clips_dir, exist_ok=True)
    os.makedirs(os.path.join(project_path, "output", "final"), exist_ok=True)

    # ---------------------------------------------------------
    # 1. LOAD NARRATION
    # ---------------------------------------------------------
    print("Loading narration...")
    with open(input_text, "r", encoding="utf-8") as f:
        narration_text = f.read()

    # ---------------------------------------------------------
    # 2. SPLIT INTO SCENES
    # ---------------------------------------------------------
    print("Splitting into scenes...")
    splitter = SceneSplitter()
    scenes = splitter.split_into_scenes(narration_text)
    print(f"Found {len(scenes)} scenes.")

    # ---------------------------------------------------------
    # 3. BUILD PROMPTS
    # ---------------------------------------------------------
    print("Building prompts...")
    prompt_builder = PromptBuilder(style_preset="cinematic")

    # ---------------------------------------------------------
    # 4. GENERATE IMAGES
    # ---------------------------------------------------------
    print("Generating images...")
    image_gen = ImageGenerator(
        model_path="models/sd3",
        output_dir=images_dir,
        seed=42,
    )
    image_gen.generate_batch(scenes, prompt_builder)

    # ---------------------------------------------------------
    # 5. GENERATE VIDEO CLIPS
    # ---------------------------------------------------------
    print("Generating video clips...")
    video_gen = VideoGenerator(
        model_path="models/svd",
        output_dir=clips_dir,
        seed=42,
    )
    video_gen.generate_batch(images_dir)

    # ---------------------------------------------------------
    # 6. ASSEMBLE FINAL VIDEO
    # ---------------------------------------------------------
    print("Assembling final video...")
    assembler = ClipAssembler(final_video_path, fps=8)
    assembler.assemble(clips_dir)

    # ---------------------------------------------------------
    # 7. ADD NARRATION AUDIO
    # ---------------------------------------------------------
    print("Adding narration audio...")
    sync = AudioSync(
        output_path=final_with_audio_path,
        audio_volume=1.0,
        fade_in=0.5,
        fade_out=0.5,
    )
    sync.merge(final_video_path, input_audio)

    print("\n🎉 Pipeline complete!")
    print(f"Final video saved at:\n{final_with_audio_path}")


if __name__ == "__main__":
    # CHANGE THIS TO YOUR PROJECT FOLDER
    project_path = r"D:\AI-Projects\project_001"
    run_pipeline(project_path)
