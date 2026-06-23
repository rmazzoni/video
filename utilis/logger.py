import os
import datetime


class Logger:
    """
    Lightweight timestamped logger with optional file output.
    """

    def __init__(self, log_to_file: bool = False, log_path: str = "pipeline.log"):
        """
        :param log_to_file: whether to write logs to a file
        :param log_path: path to the log file
        """
        self.log_to_file = log_to_file
        self.log_path = log_path

        if self.log_to_file:
            os.makedirs(os.path.dirname(log_path), exist_ok=True)

    # ---------------------------------------------------------
    # INTERNAL HELPERS
    # ---------------------------------------------------------

    def _timestamp(self) -> str:
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _write(self, message: str) -> None:
        if self.log_to_file:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(message + "\n")

    # ---------------------------------------------------------
    # LOG LEVELS
    # ---------------------------------------------------------

    def info(self, msg: str) -> None:
        line = f"[{self._timestamp()}] [INFO] {msg}"
        print(f"\033[94m{line}\033[0m")  # blue
        self._write(line)

    def warning(self, msg: str) -> None:
        line = f"[{self._timestamp()}] [WARNING] {msg}"
        print(f"\033[93m{line}\033[0m")  # yellow
        self._write(line)

    def error(self, msg: str) -> None:
        line = f"[{self._timestamp()}] [ERROR] {msg}"
        print(f"\033[91m{line}\033[0m")  # red
        self._write(line)
