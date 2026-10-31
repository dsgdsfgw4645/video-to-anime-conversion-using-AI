"""Measure the GPU's peak memory use while a block runs (polls nvidia-smi in a background thread).

The figure is the whole GPU's used memory, so it includes the desktop and any other program on the
GPU, which is the number that decides whether a run fits in 6 GB. If nvidia-smi isn't available the
monitor does nothing and summary() returns None.
"""
import subprocess
import threading


def _query() -> tuple[int, int] | None:
    """Return (used MiB, total MiB) of the first GPU, or None if nvidia-smi can't be read."""
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),  # Windows only; 0 elsewhere (Linux cloud GPUs)
        )
        used, total = r.stdout.splitlines()[0].split(",")
        return int(used), int(total)
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


class VramMonitor:
    def __init__(self, interval: float = 0.5) -> None:
        self.interval = interval
        self.start_mib: int | None = None   # used when the block began (desktop, idle server)
        self.peak_mib: int | None = None
        self.total_mib: int | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._poll, daemon=True)

    def _sample(self) -> None:
        s = _query()
        if s is None:
            return
        used, self.total_mib = s
        if self.start_mib is None:
            self.start_mib = used
        self.peak_mib = used if self.peak_mib is None else max(self.peak_mib, used)

    def _poll(self) -> None:
        while not self._stop.is_set():
            self._sample()
            self._stop.wait(self.interval)

    def __enter__(self) -> "VramMonitor":
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        self._thread.join()
        self._sample()  # one last reading, in case the peak came right at the end

    def summary(self) -> str | None:
        if self.peak_mib is None or self.total_mib is None:
            return None
        return (f"GPU memory: peak {self.peak_mib} MiB of {self.total_mib} MiB used "
                f"(headroom {self.total_mib - self.peak_mib} MiB; {self.start_mib} MiB was in use at the start)")
