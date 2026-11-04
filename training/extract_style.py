"""Phase 4: extract the style-LoRA training frames from a film.

Put the film in training/input/ (or set training.style.video in the config) and run this with no arguments.
Frames land in training/data/style/images/ with a contact_sheet.jpg to review.
Optional: python training/extract_style.py [film] [--max-images 250]
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.shot_state import SettingsChanged  # noqa: E402
from pipeline.style_frames import DEFAULTS, extract_style_frames, find_video  # noqa: E402
from pipeline.stylize import load_config  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", nargs="?", help="the film (default: config training.style.video, else the largest video in training/input/)")
    ap.add_argument("--max-images", type=int, help="cap on saved frames")
    a = ap.parse_args()

    cfg = load_config().get("training", {}).get("style", {})
    params = {k: cfg[k] for k in DEFAULTS if k in cfg}
    if a.max_images:
        params["max_images"] = a.max_images
    chosen = a.video or cfg.get("video")
    video = (ROOT / chosen) if chosen else find_video(ROOT / "training" / "input")
    if not video or not Path(video).exists():
        print("No film found. Copy it into training/input/ (any .mkv/.mp4/.avi ...) or set training.style.video "
              "in config/project.yaml, then run again.")
        return 1
    out = ROOT / cfg.get("out_dir", "training/data/style/images")
    try:
        extract_style_frames(Path(video), out, params)
    except SettingsChanged as e:
        print(e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
