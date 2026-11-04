"""Phase 4: set up local LoRA training: kohya sd-scripts in third_party/ and its own venv (.venv-train).

A separate venv keeps training's pinned packages (transformers, diffusers, accelerate, bitsandbytes)
away from the ComfyUI/torch stack in .venv. Idempotent: run again any time. No arguments.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KOHYA = ROOT / "third_party" / "sd-scripts"
VENV = ROOT / ".venv-train"
PY = VENV / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
TORCH_INDEX = "https://download.pytorch.org/whl/cu126"


def run(*cmd, cwd=None) -> None:
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, cwd=cwd)


def main() -> None:
    if not KOHYA.exists():
        run("git", "clone", "--depth", "1", "https://github.com/kohya-ss/sd-scripts.git", KOHYA)
    if not PY.exists():
        base = ["py", "-3.11"] if sys.platform == "win32" else ["python3.11"]
        run(*base, "-m", "venv", VENV)
    run(PY, "-m", "pip", "install", "-q", "--upgrade", "pip")
    run(PY, "-m", "pip", "install", "-q", "torch", "torchvision", "--index-url", TORCH_INDEX)
    run(PY, "-m", "pip", "install", "-q", "-r", "requirements.txt", cwd=KOHYA)   # its last line is "-e .", relative to the repo
    run(PY, "-c", "import torch, bitsandbytes, accelerate, diffusers; "
        "print('torch', torch.__version__, 'cuda', torch.cuda.is_available(), "
        "'bitsandbytes', bitsandbytes.__version__)")
    print("Training environment ready.")


if __name__ == "__main__":
    main()
