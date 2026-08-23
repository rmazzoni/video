import os
import sys

# Must be set before PyTorch is imported anywhere
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

# Avoid Chromium GPU-compositor corruption in the embedded ComfyUI view.
webengine_flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
if "--disable-gpu-compositing" not in webengine_flags.split():
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
        f"{webengine_flags} --disable-gpu-compositing".strip()
    )

from PyQt6.QtWidgets import QApplication
from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
