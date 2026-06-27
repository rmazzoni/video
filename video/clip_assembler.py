import os
from typing import List
from moviepy import VideoFileClip, concatenate_videoclips


class ClipAssembler:
    """
    Concatenates individual scene clips into a single final video.
    """

    def __init__(self, output_path: str, fps: int = 8):
        """
        :param output_path: path to save the final assembled video
        :param fps: frames per second for the final output
        """
        self.output_path = output_path
        self.fps = fps

    # ---------------------------------------------------------
    # PUBLIC API
    # ---------------------------------------------------------

    def assemble(self, clips_dir: str, on_progress=None) -> str:
        """
        Concatenates all MP4 clips in a directory into a single video.
        :param on_progress: optional callback(loaded, total) called as each clip is loaded
        Returns the output file path.
        """
        clip_files = self._get_sorted_clips(clips_dir)

        if not clip_files:
            raise ValueError(f"No clips found in {clips_dir}")

        total = len(clip_files)
        print(f"Assembling {total} clips...")

        video_clips = []
        for i, path in enumerate(clip_files, start=1):
            video_clips.append(VideoFileClip(path))
            if on_progress:
                on_progress(i, total)

        final_video = concatenate_videoclips(video_clips, method="compose")

        final_video.write_videofile(
            self.output_path,
            fps=self.fps,
            codec="libx264",
            audio=False,
        )

        return self.output_path

    # ---------------------------------------------------------
    # INTERNAL HELPERS
    # ---------------------------------------------------------

    def _get_sorted_clips(self, clips_dir: str) -> List[str]:
        """
        Returns a sorted list of clip file paths based on scene number.
        Expected filename format: scene_001.mp4
        """
        files = [
            f for f in os.listdir(clips_dir)
            if f.lower().endswith(".mp4") and f.startswith("scene_")
        ]

        # Sort by scene number
        files.sort(key=lambda x: int(x.split("_")[1].split(".")[0]))

        return [os.path.join(clips_dir, f) for f in files]
