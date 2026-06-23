import os
from typing import List, Optional


class FileUtils:
    """
    Utility functions for safe file and directory operations.
    """

    # ---------------------------------------------------------
    # PATH HELPERS
    # ---------------------------------------------------------

    @staticmethod
    def ensure_dir(path: str) -> None:
        """
        Creates a directory if it doesn't exist.
        """
        os.makedirs(path, exist_ok=True)

    @staticmethod
    def join(*parts: str) -> str:
        """
        Safe wrapper around os.path.join.
        """
        return os.path.join(*parts)

    @staticmethod
    def exists(path: str) -> bool:
        """
        Checks if a file or directory exists.
        """
        return os.path.exists(path)

    # ---------------------------------------------------------
    # FILE LISTING
    # ---------------------------------------------------------

    @staticmethod
    def list_images_sorted(directory: str) -> List[str]:
        """
        Returns a sorted list of image file paths.
        Expected format: scene_001.png
        """
        files = [
            f for f in os.listdir(directory)
            if f.lower().endswith((".png", ".jpg", ".jpeg"))
        ]

        files.sort(key=lambda x: FileUtils._extract_scene_number(x))
        return [os.path.join(directory, f) for f in files]

    @staticmethod
    def list_clips_sorted(directory: str) -> List[str]:
        """
        Returns a sorted list of MP4 clip paths.
        Expected format: scene_001.mp4
        """
        files = [
            f for f in os.listdir(directory)
            if f.lower().endswith(".mp4") and f.startswith("scene_")
        ]

        files.sort(key=lambda x: FileUtils._extract_scene_number(x))
        return [os.path.join(directory, f) for f in files]

    @staticmethod
    def _extract_scene_number(filename: str) -> int:
        """
        Extracts the scene number from filenames like:
        scene_001.png → 1
        scene_014.mp4 → 14
        """
        try:
            return int(filename.split("_")[1].split(".")[0])
        except Exception:
            return 999999  # fallback to push unknown files to the end

    # ---------------------------------------------------------
    # TEXT FILES
    # ---------------------------------------------------------

    @staticmethod
    def read_text(path: str, encoding: str = "utf-8") -> str:
        """
        Reads a text file safely.
        """
        with open(path, "r", encoding=encoding) as f:
            return f.read()

    @staticmethod
    def write_text(path: str, content: str, encoding: str = "utf-8") -> None:
        """
        Writes text to a file, creating directories if needed.
        """
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding=encoding) as f:
            f.write(content)

    # ---------------------------------------------------------
    # FILE MOVEMENT
    # ---------------------------------------------------------

    @staticmethod
    def move(src: str, dst: str) -> None:
        """
        Moves a file to a new location.
        """
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        os.replace(src, dst)

    @staticmethod
    def copy(src: str, dst: str) -> None:
        """
        Copies a file to a new location.
        """
        import shutil
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
