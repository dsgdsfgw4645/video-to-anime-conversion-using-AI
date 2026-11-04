"""Phase 4: train a LoRA locally (6 GB settings). Close ComfyUI first; it must not hold the GPU.

    python training/train.py                  # trains the style LoRA (default)
    python training/train.py --target Adwait  # trains the actor LoRA for training/data/actors_ready/Adwait
    python training/train.py --smoke          # 20-step test run to check memory and speed
Output: training/output/<name>/<name>.safetensors. Settings come from `training:` in the config.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.lora_train import LORA, TrainingError, train  # noqa: E402
from pipeline.stylize import load_config  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", default="style", help='"style", or an actor folder name in training/data/actors_ready/')
    ap.add_argument("--smoke", action="store_true", help="20 steps only, into <name>_smoketest")
    a = ap.parse_args()

    cfg = load_config()
    t = cfg.get("training", {})
    lora = {k: v for k, v in t.get("lora", {}).items() if k in LORA}
    if a.target == "style":
        c = t.get("style", {})
        name = c.get("lora_name", "bloodlust_style") + (f"_{c['run']}" if c.get("run") else "")
        images, steps = ROOT / "training" / "data" / "style" / "images", c.get("steps", 2500)
    else:
        c = t.get("actors", {}).get(a.target, {})
        name = c.get("lora_name", f"{a.target.lower()}_person") + (f"_{c['run']}" if c.get("run") else "")
        images, steps = ROOT / "training" / "data" / "actors_ready" / a.target, c.get("steps", 2400)
    checkpoint = ROOT / "third_party" / "ComfyUI" / "models" / "checkpoints" / cfg["models"]["checkpoint"]
    try:
        train(name, images, checkpoint, ROOT / "training" / "output", steps, lora, False, a.smoke)
    except TrainingError as e:
        print(e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
