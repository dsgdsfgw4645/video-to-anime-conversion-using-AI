"""Phase 4: add face and upper-body crops next to the full photos of an actor (nothing is replaced).

For each source photo the YuNet face detector finds the face, and two extra images are cut from the
ORIGINAL full-resolution photo: <photo>_face.jpg (head and shoulders) and <photo>_upper.jpg (head to waist).
Skipped when: no face, a second person of similar size (ambiguous), the crop would hold fewer than
`min_side` real pixels (upscaling a tiny face adds nothing), or the crop is nearly the whole photo.
"""
import urllib.request
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

from pipeline.captioning import list_images

YUNET_URL = ("https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/"
             "face_detection_yunet_2023mar.onnx")
# crop side as a multiple of the face width, and the face center's position from the top of the crop
CROPS = {"face": (2.6, 0.45), "upper": (5.5, 0.22)}


def yunet_detector(model_dir: Path, max_side: int = 1600):
    """Return detect(rgb_array) -> [(x, y, w, h, score)] in that array's pixel coordinates."""
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)  # YuNet prints a harmless warning per photo
    model = model_dir / "face_detection_yunet_2023mar.onnx"
    if not model.exists():
        model_dir.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(YUNET_URL, model)

    def detect(rgb: np.ndarray):
        h, w = rgb.shape[:2]
        k = min(1.0, max_side / max(h, w))
        small = cv2.cvtColor(cv2.resize(rgb, (round(w * k), round(h * k)), interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2BGR)
        det = cv2.FaceDetectorYN.create(str(model), "", (small.shape[1], small.shape[0]), 0.6, 0.3, 5000)
        _, faces = det.detect(small)
        return [] if faces is None else [(f[0] / k, f[1] / k, f[2] / k, f[3] / k, float(f[-1])) for f in faces]
    return detect


def crop_box(face: tuple, kind: str, w: int, h: int) -> tuple[int, int, int, int]:
    """Square crop (x0, y0, x1, y1) around the face, slid back inside the photo where it overhangs."""
    mult, top = CROPS[kind]
    fx, fy, fw, fh = face[:4]
    side = fw * mult
    x0 = fx + fw / 2 - side / 2
    y0 = fy + fh / 2 - side * top
    side = min(side, w, h)
    x0, y0 = min(max(x0, 0), w - side), min(max(y0, 0), h - side)
    return round(x0), round(y0), round(x0 + side), round(y0 + side)


def make_crops(src: Path, dst: Path, detect, min_side: int = 384, out_side: int = 768, log=print) -> dict:
    """Write photo_NNN_face.jpg / photo_NNN_upper.jpg into dst for photos in src (numbering matches prepare_photos)."""
    import pillow_heif
    pillow_heif.register_heif_opener()
    made = {"face": 0, "upper": 0, "no_face": 0, "skipped": 0}
    for n, p in enumerate(list_images(src), 1):
        outs = {k: dst / f"photo_{n:03d}_{k}.jpg" for k in CROPS}
        if all(o.exists() for o in outs.values()):
            continue
        im = ImageOps.exif_transpose(Image.open(p)).convert("RGB")
        faces = sorted(detect(np.asarray(im)), key=lambda f: -f[2] * f[3])
        if not faces:
            made["no_face"] += 1
            continue
        if len(faces) > 1 and faces[1][2] * faces[1][3] > 0.4 * faces[0][2] * faces[0][3]:
            made["skipped"] += 1
            continue
        for kind, out in outs.items():
            if out.exists():
                continue
            x0, y0, x1, y1 = crop_box(faces[0], kind, *im.size)
            side = x1 - x0
            if side < min_side or side > 0.9 * min(im.size):
                made["skipped"] += 1
                continue
            c = im.crop((x0, y0, x1, y1))
            if side > out_side:
                c = c.resize((out_side, out_side), Image.LANCZOS)
            c.save(out, quality=95)
            made[kind] += 1
    log(f"{src.name}: {made['face']} face crops, {made['upper']} upper-body crops "
        f"({made['no_face']} photos without a detected face, {made['skipped']} crops skipped)")
    return made
