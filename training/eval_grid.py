"""Phase 4: make a comparison grid for a trained LoRA (every saved epoch + the final file, same prompts and seed).

    python training/eval_grid.py                  # the actor LoRA Adwait (default)
    python training/eval_grid.py --target style   # the style LoRA
Output: training/output/eval/<lora name>/grid.jpg (+ the single images). Close any training run first (GPU).
ComfyUI is started and stopped by the script if it is not already running.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.lora_eval import run_grid  # noqa: E402
from pipeline.stylize import load_config  # noqa: E402

PERSON = [
    {"label": "portrait", "positive": "{t}, 1boy, solo, portrait, looking at viewer, upper body, simple background"},
    {"label": "full body", "positive": "{t}, 1boy, solo, full body, standing, street, daytime"},
    {"label": "no headwear", "positive": "{t}, 1boy, solo, upper body, short black hair, bare head, smiling, outdoors",
     "negative": "beanie, headband, hat, headwear, bandana, glasses"},
    {"label": "other outfit", "positive": "{t}, 1boy, solo, red jacket, city street at night, neon lights, cowboy shot"},
]
STYLE = [
    {"label": "hunter", "positive": "{t}, 1boy, solo, long black coat, wide-brimmed hat, standing in a ruined gothic city at night, moonlight"},
    {"label": "woman", "positive": "{t}, 1girl, solo, blonde hair, red jacket, portrait, forest, looking at viewer"},
    {"label": "castle", "positive": "{t}, no humans, scenery, vampire castle on a cliff, full moon, storm clouds"},
    {"label": "desert", "positive": "{t}, 1boy, solo, walking in a desert wasteland, sunset, cloak, wind"},
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", default="Adwait", help='"style", or an actor name (default Adwait)')
    a = ap.parse_args()
    cfg = load_config()
    t = cfg.get("training", {})
    if a.target == "style":
        c = t.get("style", {})
        name = c.get("lora_name", "bloodlust_style") + (f"_{c['run']}" if c.get("run") else "")
        trigger, prompts, weights = c.get("trigger", "bloodlust_style"), STYLE, [0.8, 0.5, 1.0]
    else:
        c = t.get("actors", {}).get(a.target, {})
        name = c.get("lora_name", f"{a.target.lower()}_person") + (f"_{c['run']}" if c.get("run") else "")
        trigger, prompts, weights = c.get("trigger", f"{a.target.lower()}_person"), PERSON, [0.8, 0.6, 1.0]
    folder = ROOT / "training" / "output" / name
    files = sorted(folder.glob(f"{name}-*.safetensors")) + [folder / f"{name}.safetensors"]
    files = [f for f in files if f.exists()]
    if not files or not (folder / f"{name}.safetensors").exists():
        print(f"No finished LoRA in {folder}. Run training/train.py --target {a.target} first.")
        return 1
    prompts = [{**p, "positive": p["positive"].format(t=trigger)} for p in prompts]
    run_grid(cfg, name, files, weights, prompts, ROOT / "training" / "output" / "eval" / name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
