import os
from typing import Tuple
from PIL import Image


class ImageUtils:
    """
    Utility functions for image loading, validation, resizing,
    aspect ratio correction, and saving.
    """

    # ---------------------------------------------------------
    # BASIC LOAD / SAVE
    # ---------------------------------------------------------

    @staticmethod
    def load_image(path: str) -> Image.Image:
        """
        Loads an image safely and converts it to RGB.
        """
        if not os.path.exists(path):
            raise FileNotFoundError(f"Image not found: {path}")

        img = Image.open(path).convert("RGB")
        return img

    @staticmethod
    def save_image(image: Image.Image, path: str) -> None:
        """
        Saves an image to disk, creating directories if needed.
        """
        os.makedirs(os.path.dirname(path), exist_ok=True)
        image.save(path)

    # ---------------------------------------------------------
    # ASPECT RATIO HELPERS
    # ---------------------------------------------------------

    @staticmethod
    def get_aspect_ratio(image: Image.Image) -> float:
        """
        Returns width/height ratio.
        """
        w, h = image.size
        return w / h

    @staticmethod
    def resize_to_aspect_ratio(
        image: Image.Image,
        target_ratio: float,
        method=Image.LANCZOS
    ) -> Image.Image:
        """
        Resizes an image to match a target aspect ratio by cropping
        the least important dimension.
        """

        w, h = image.size
        current_ratio = w / h

        # If already close enough, skip
        if abs(current_ratio - target_ratio) < 0.01:
            return image

        if current_ratio > target_ratio:
            # Too wide → crop width
            new_width = int(h * target_ratio)
            offset = (w - new_width) // 2
            crop_box = (offset, 0, offset + new_width, h)
        else:
            # Too tall → crop height
            new_height = int(w / target_ratio)
            offset = (h - new_height) // 2
            crop_box = (0, offset, w, offset + new_height)

        cropped = image.crop(crop_box)
        return cropped.resize((w, h), method)

    # ---------------------------------------------------------
    # RESIZING
    # ---------------------------------------------------------

    @staticmethod
    def resize_max(image: Image.Image, max_size: int) -> Image.Image:
        """
        Resizes an image so its longest side = max_size.
        """
        w, h = image.size
        scale = max_size / max(w, h)
        new_size = (int(w * scale), int(h * scale))
        return image.resize(new_size, Image.LANCZOS)

    # ---------------------------------------------------------
    # VALIDATION
    # ---------------------------------------------------------

    @staticmethod
    def validate_image(image: Image.Image, min_size: int = 256) -> bool:
        """
        Ensures the image is large enough and not corrupted.
        """
        w, h = image.size
        if w < min_size or h < min_size:
            return False
        return True

    # ---------------------------------------------------------
    # DEBUG HELPERS
    # ---------------------------------------------------------

    @staticmethod
    def add_debug_border(image: Image.Image, color: Tuple[int, int, int] = (255, 0, 0), thickness: int = 4) -> Image.Image:
        """
        Adds a colored border around the image for debugging.
        """
        w, h = image.size
        bordered = Image.new("RGB", (w + thickness * 2, h + thickness * 2), color)
        bordered.paste(image, (thickness, thickness))
        return bordered
