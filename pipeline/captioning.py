"""Phase 4: prepare actor photos (HEIC -> JPG) and write a caption .txt next to every training image.

Captions are "<trigger word>, tag, tag, ..." with tags from the WD14 tagger (SmilingWolf, ONNX, CPU).
For actors, tags that describe the person themselves (hair, eyes, beard, skin ...) are dropped, so those
traits get learned by the trigger word instead of being explained away by tags. An existing .txt is never
overwritten, so hand-edited captions survive re-runs; delete a .txt to have it written again.
"""
import csv
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".heic", ".heif"}
WD14_REPO = "SmilingWolf/wd-v1-4-convnextv2-tagger-v2"

STYLE_DROP = {"lowres", "jpeg artifacts", "watermark", "signature", "artist name", "username", "web address"}
PERSON_DROP = ("hair", "eyes", "beard", "mustache", "stubble", "skin", "lips", "eyebrows", "realistic",
               "photorealistic", "photo", "lowres", "blurry", "watermark", "signature", "artist name",
               "looking at viewer")


def list_images(folder: Path) -> list[Path]:
    return sorted(p for p in folder.glob("*") if p.suffix.lower() in IMAGE_EXT and p.stem != "contact_sheet")


def prepare_photos(src: Path, dst: Path, max_side: int = 1024, log=print) -> int:
    """Convert every photo in src (HEIC included) to an upright JPG with long side <= max_side. Skips finished ones."""
    import pillow_heif
    pillow_heif.register_heif_opener()
    dst.mkdir(parents=True, exist_ok=True)
    done = 0
    for n, p in enumerate(list_images(src), 1):
        out = dst / f"photo_{n:03d}.jpg"
        if out.exists():
            done += 1
            continue
        im = ImageOps.exif_transpose(Image.open(p)).convert("RGB")
        if max(im.size) > max_side:
            s = max_side / max(im.size)
            im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
        im.save(out, quality=95)
        done += 1
    log(f"{src.name}: {done} photos ready in {dst}")
    return done


class Tagger:
    """WD14 tagger on the CPU. Downloads the model (about 380 MB) into model_dir on first use."""

    def __init__(self, model_dir: Path, threshold: float = 0.35):
        import onnxruntime as ort
        from huggingface_hub import hf_hub_download
        self.threshold = threshold
        model = hf_hub_download(WD14_REPO, "model.onnx", local_dir=model_dir)
        tags = hf_hub_download(WD14_REPO, "selected_tags.csv", local_dir=model_dir)
        self.sess = ort.InferenceSession(model, providers=["CPUExecutionProvider"])
        self.input = self.sess.get_inputs()[0]
        self.size = self.input.shape[1]
        with open(tags, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.names = [r["name"] for r in rows]
        self.general = [i for i, r in enumerate(rows) if r["category"] == "0"]   # 4 = character names, 9 = ratings

    def __call__(self, path: Path) -> list[str]:
        im = Image.open(path).convert("RGB")
        side = max(im.size)
        sq = Image.new("RGB", (side, side), (255, 255, 255))                    # pad to a white square
        sq.paste(im, ((side - im.width) // 2, (side - im.height) // 2))
        arr = np.asarray(sq.resize((self.size, self.size), Image.BICUBIC), dtype=np.float32)[:, :, ::-1]  # RGB -> BGR
        probs = self.sess.run(None, {self.input.name: arr[None]})[0][0]
        picked = sorted((i for i in self.general if probs[i] >= self.threshold), key=lambda i: -probs[i])
        return [self.names[i].replace("_", " ") if len(self.names[i]) > 3 else self.names[i] for i in picked]


def filter_tags(tags: list[str], kind: str) -> list[str]:
    if kind == "style":
        return [t for t in tags if t not in STYLE_DROP]
    return [t for t in tags if not any(w in t for w in PERSON_DROP)]


def caption_folder(images: Path, trigger: str, kind: str, tagger, log=print) -> int:
    """Write <image>.txt for every image without one. Returns how many were written."""
    written = 0
    for p in list_images(images):
        txt = p.with_suffix(".txt")
        if txt.exists():
            continue
        txt.write_text(", ".join([trigger] + filter_tags(tagger(p), kind)), encoding="utf-8")
        written += 1
    log(f"{images}: wrote {written} captions ({len(list_images(images))} images)")
    return written
