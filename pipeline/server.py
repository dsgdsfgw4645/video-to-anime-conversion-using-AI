"""Start ComfyUI on demand, so every entry point runs from an IDE with no manual server step.

comfy_server() does nothing if a server already answers (for example one you started yourself).
Otherwise it launches scripts/start_comfyui.ps1 in the background, waits until the API answers, and,
if it was the one that started it, stops it again afterwards. Both can be switched off in the
config under comfyui: (autostart, autostop). Windows only, like the rest of the project.
"""
import contextlib
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
START_SCRIPT = ROOT / "scripts" / "start_comfyui.ps1"
LOG = ROOT / "work" / "comfyui.log"


@contextlib.contextmanager
def comfy_server(client, cfg: dict, timeout: float = 240):
    """Make sure ComfyUI answers while the block runs. `client` needs is_up() and a .url."""
    if client.is_up():
        yield
        return
    opts = cfg.get("comfyui", {})
    if not opts.get("autostart", True):
        raise RuntimeError("ComfyUI is not reachable. Start it with scripts\\start_comfyui.ps1 "
                           "or set comfyui.autostart: true in the config.")
    proc = _start(urlparse(client.url).port or 8188)
    try:
        _wait(client, proc, timeout)
        yield
    finally:
        if opts.get("autostop", True):
            _stop(proc)


def _start(port: int) -> subprocess.Popen:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    print(f"Starting ComfyUI on port {port} (log: {LOG}) ...", flush=True)
    with open(LOG, "ab") as log:
        return subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(START_SCRIPT),
             "--port", str(port)],  # the later --port wins over the script's default 8188
            stdout=log, stderr=log, stdin=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW,
        )


def _wait(client, proc: subprocess.Popen, timeout: float) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if client.is_up():
            print("ComfyUI is up.", flush=True)
            return
        if proc.poll() is not None:
            raise RuntimeError(f"ComfyUI exited while starting (code {proc.returncode}). See {LOG}")
        time.sleep(2)
    _stop(proc)
    raise TimeoutError(f"ComfyUI did not answer within {timeout:.0f}s. See {LOG}")


def _stop(proc: subprocess.Popen) -> None:
    """Kill the launcher and the python server under it."""
    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    print("ComfyUI stopped.", flush=True)
