"""Phase-1 smoke test: restyle one image into anime via ComfyUI (img2img + anime-lineart ControlNet).

ComfyUI must be running (scripts\\start_comfyui.ps1).
Usage:  .venv\\Scripts\\python.exe scripts\\test_single_frame.py [image] [--denoise 0.55] [--seed 12345]
"""
import argparse
import sys
import time
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.comfy_client import ComfyClient  # noqa: E402
from pipeline.stylize import build_workflow, load_config  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("image", nargs="?", default=str(ROOT / "third_party/ComfyUI/input/example.png"))
    ap.add_argument("--denoise", type=float)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--out", default=str(ROOT / "work" / "phase1"))
    args = ap.parse_args()

    cfg = load_config()
    client = ComfyClient(cfg["comfyui"]["url"])
    if not client.is_up():
        sys.exit("ComfyUI is not reachable. Start it with scripts\\start_comfyui.ps1")

    with Image.open(args.image) as im:
        size = im.size
    wf = build_workflow(
        cfg,
        client.upload_image(Path(args.image)),
        size,
        seed=args.seed,
        denoise=args.denoise,
    )

    t0 = time.time()
    saved = client.run(wf, Path(args.out))
    print(f"done in {time.time() - t0:.1f}s")
    for paths in saved.values():
        for p in paths:
            print(" ", p)


if __name__ == "__main__":
    main()
