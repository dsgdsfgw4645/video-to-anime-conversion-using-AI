"""Flicker metric: mean SSIM between consecutive frames (plan.md "Verification").

Compare the stylized shot against its source: the source's value is the natural amount of motion,
so a stylized shot far below it is flickering. Phase 3+ must improve on the phase 2 baseline.
"""
from pathlib import Path

import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity


def _gray(path: Path, size: tuple[int, int]) -> np.ndarray:
    with Image.open(path) as im:
        return np.asarray(im.convert("L").resize(size), dtype=np.uint8)


def mean_consecutive_ssim(frames_dir: Path, size: tuple[int, int] = (256, 256)) -> float:
    frames = sorted(frames_dir.glob("frame_*.png"))
    if len(frames) < 2:
        raise ValueError(f"need at least 2 frames in {frames_dir}")
    grays = [_gray(f, size) for f in frames]
    return float(np.mean([structural_similarity(a, b) for a, b in zip(grays, grays[1:])]))


def flicker_report(source_dir: Path, anime_dir: Path) -> dict[str, float]:
    src, out = mean_consecutive_ssim(source_dir), mean_consecutive_ssim(anime_dir)
    return {"source_ssim": src, "anime_ssim": out, "ratio": out / src}
