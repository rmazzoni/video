import os
from moviepy import VideoFileClip, AudioFileClip


class AudioSync:
    """
    Syncs narration audio with the final assembled video.
    """

    def __init__(
        self,
        output_path: str,
        audio_volume: float = 1.0,
        fade_in: float = 0.0,
        fade_out: float = 0.0,
    ):
        """
        :param output_path: path to save the final video with audio
        :param audio_volume: volume multiplier for narration (1.0 = normal)
        :param fade_in: audio fade-in duration (seconds)
        :param fade_out: audio fade-out duration (seconds)
        """
        self.output_path = output_path
        self.audio_volume = audio_volume
        self.fade_in = fade_in
        self.fade_out = fade_out

    # ---------------------------------------------------------
    # PUBLIC API
    # ---------------------------------------------------------

    def merge(self, video_path: str, audio_path: str) -> str:
        """
        Merges the narration audio with the final video.
        Returns the output file path.
        """

        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video not found: {video_path}")

        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio not found: {audio_path}")

        print("Loading video...")
        video = VideoFileClip(video_path)

        print("Loading audio...")
        audio = AudioFileClip(audio_path).volumex(self.audio_volume)

        # Apply fades if needed
        if self.fade_in > 0:
            audio = audio.audio_fadein(self.fade_in)
        if self.fade_out > 0:
            audio = audio.audio_fadeout(self.fade_out)

        # Trim or loop audio to match video duration
        audio = self._match_audio_to_video(audio, video.duration)

        print("Merging audio with video...")
        final = video.set_audio(audio)

        final.write_videofile(
            self.output_path,
            codec="libx264",
            audio_codec="aac",
            fps=video.fps,
        )

        return self.output_path

    # ---------------------------------------------------------
    # INTERNAL HELPERS
    # ---------------------------------------------------------

    def _match_audio_to_video(self, audio, video_duration: float):
        """
        Ensures audio matches the video duration.
        - If audio is longer → cut it
        - If audio is shorter → pad with silence
        """

        if audio.duration > video_duration:
            return audio.subclip(0, video_duration)

        if audio.duration < video_duration:
            silence_duration = video_duration - audio.duration
            silence = AudioFileClip(self._generate_silence(silence_duration))
            return audio.set_duration(video_duration)

        return audio

    def _generate_silence(self, duration: float):
        """
        Generates a temporary silent audio file.
        MoviePy doesn't have built-in silence, so we create one.
        """
        import numpy as np
        import soundfile as sf
        import tempfile

        samplerate = 44100
        samples = int(duration * samplerate)
        silence = np.zeros(samples)

        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        sf.write(temp_file.name, silence, samplerate)

        return temp_file.name
