"""Launches ComfyUI as a background server, then starts this app's main.py.

Reads connection/install settings from config/comfy.yaml (host, port,
install_dir, python_executable). ComfyUI is started as a subprocess; once
its HTTP port responds, the Qt app is launched in the foreground. When the
Qt app exits, the ComfyUI subprocess is terminated.
"""
import os
import socket
import subprocess
import sys
import time

import yaml

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "comfy.yaml")

STARTUP_TIMEOUT_SECS = 60
POLL_INTERVAL_SECS = 1.0
RELAUNCH_EXIT_CODE = 75


def ensure_vid_custom_nodes(install_dir: str) -> None:
    source = os.path.join(BASE_DIR, "comfy_nodes", "vid_pipeline")
    custom_nodes_dir = os.path.join(install_dir, "custom_nodes")
    target = os.path.join(custom_nodes_dir, "vid_pipeline")
    os.makedirs(custom_nodes_dir, exist_ok=True)

    if os.path.isdir(target):
        if os.path.samefile(source, target):
            return
        raise FileExistsError(
            f"ComfyUI custom node path already exists and is not linked to this app: {target}"
        )

    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", target, source],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Could not register VID ComfyUI nodes: {result.stderr.strip()}")
    print(f"[launcher] Registered VID custom nodes: {target} -> {source}")


def load_comfy_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        return sock.connect_ex((host, port)) == 0


def start_comfyui(install_dir: str, python_executable: str, host: str, port: int) -> subprocess.Popen:
    entry_script = os.path.join(install_dir, "main.py")
    if not os.path.isfile(entry_script):
        raise FileNotFoundError(f"ComfyUI entry script not found: {entry_script}")
    if not os.path.isfile(python_executable):
        raise FileNotFoundError(f"ComfyUI python executable not found: {python_executable}")

    print(f"[launcher] Starting ComfyUI from {install_dir} on {host}:{port} ...")
    return subprocess.Popen(
        [python_executable, entry_script, "--listen", host, "--port", str(port)],
        cwd=install_dir,
    )


def wait_for_comfyui(host: str, port: int, timeout_secs: float) -> bool:
    deadline = time.monotonic() + timeout_secs
    while time.monotonic() < deadline:
        if is_port_open(host, port):
            return True
        time.sleep(POLL_INTERVAL_SECS)
    return False


def main() -> None:
    config = load_comfy_config()
    host = config.get("host", "127.0.0.1")
    port = int(config.get("port", 8188))
    install_dir = config.get("install_dir")
    python_executable = config.get("python_executable")

    if not install_dir or not python_executable:
        print("[launcher] install_dir/python_executable missing from config/comfy.yaml", file=sys.stderr)
        sys.exit(1)

    ensure_vid_custom_nodes(install_dir)

    comfy_proc = None
    if is_port_open(host, port):
        print(f"[launcher] ComfyUI already running on {host}:{port}, skipping launch.")
    else:
        comfy_proc = start_comfyui(install_dir, python_executable, host, port)
        print("[launcher] Waiting for ComfyUI to come online...")
        if not wait_for_comfyui(host, port, STARTUP_TIMEOUT_SECS):
            print("[launcher] Timed out waiting for ComfyUI to start.", file=sys.stderr)
            comfy_proc.terminate()
            sys.exit(1)
        print("[launcher] ComfyUI is up.")

    try:
        app_env = os.environ.copy()
        app_env["VID_COMFY_LAUNCHER"] = "1"
        while True:
            print("[launcher] Starting Qt application...")
            app_proc = subprocess.Popen(
                [sys.executable, os.path.join(BASE_DIR, "main.py")],
                cwd=BASE_DIR,
                env=app_env,
            )
            if app_proc.wait() != RELAUNCH_EXIT_CODE:
                break
            print("[launcher] Relaunch requested; keeping ComfyUI running.")
    finally:
        if comfy_proc is not None and comfy_proc.poll() is None:
            print("[launcher] Shutting down ComfyUI...")
            comfy_proc.terminate()
            try:
                comfy_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                comfy_proc.kill()


if __name__ == "__main__":
    main()
