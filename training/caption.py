"""Phase 4: convert the actor photos (full photos plus face and upper-body crops) and caption the style frames and the actor photos.

Reads training/data/style/images/ and training/data/actors/<name>/, writes the converted actor photos to
training/data/actors_ready/<name>/ and a .txt caption next to every image. No arguments needed.
Existing captions are kept (hand edits survive); delete a .txt to regenerate it.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.captioning import Tagger, caption_folder, list_images, prepare_photos  # noqa: E402
from pipeline.photo_crops import make_crops, yunet_detector  # noqa: E402
from pipeline.style_frames import contact_sheet  # noqa: E402
from pipeline.stylize import load_config  # noqa: E402


def main() -> int:
    cfg = load_config().get("training", {})
    data = ROOT / "training" / "data"
    actors = [d for d in sorted((data / "actors").glob("*")) if d.is_dir() and list_images(d)]
    style_dir = data / cfg.get("style", {}).get("out_dir", "training/data/style/images").replace("training/data/", "")
    if not actors and not list_images(style_dir):
        print("Nothing to caption: no actor photos in training/data/actors/<name>/ and no style frames.")
        return 1

    ready, detector = {}, None
    for d in actors:
        ready[d.name] = data / "actors_ready" / d.name
        prepare_photos(d, ready[d.name])
        if cfg.get("actors", {}).get("crops", True):
            detector = detector or yunet_detector(ROOT / "training" / "models" / "yunet")
            make_crops(d, ready[d.name], detector)
        contact_sheet(list_images(ready[d.name]), ready[d.name] / "contact_sheet.jpg", cols=8)

    print("Loading the WD14 tagger (first run downloads about 380 MB) ...")
    tagger = Tagger(ROOT / "training" / "models" / "wd14", cfg.get("caption_threshold", 0.35))
    if list_images(style_dir):
        trigger = cfg.get("style", {}).get("trigger", "bloodlust_style")
        caption_folder(style_dir, trigger, "style", tagger)
    for name, folder in ready.items():
        trigger = cfg.get("actors", {}).get(name, {}).get("trigger", f"{name.lower()}_person")
        caption_folder(folder, trigger, "person", tagger)
    print("Done. Spot-check a few .txt files next to the images before training.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
