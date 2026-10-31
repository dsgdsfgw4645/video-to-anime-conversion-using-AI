"""Flicker metrics (plan.md "Verification").

Two views of how steady a stylized shot is:

* whole frame: mean SSIM between consecutive frames, stylized vs source. The source's value is the
  natural amount of motion, so a ratio well below 1 means the stylized shot changes more than it should.
* static regions: only pixels where the source itself doesn't change between two frames. Anything the
  stylized shot changes there is pure flicker, since nothing moved. This is the number phase 3+ must
  improve on; it ignores real motion, which the whole-frame number can't.
"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter
from skimage.metrics import structural_similarity

SIZE = (256, 256)
STATIC_THRESHOLD = 6.0   # a source pixel is "static" if it changes by less than this (0-255 levels)
MIN_STATIC_FRACTION = 0.02  # pairs with less static area than this are skipped (a pan or a cut)


def _gray(path: Path, size: tuple[int, int], blur: float = 0) -> np.ndarray:
    with Image.open(path) as im:
        g = im.convert("L").resize(size)
        if blur:
            g = g.filter(ImageFilter.GaussianBlur(blur))
        return np.asarray(g, dtype=np.float32)


def _frames(frames_dir: Path, max_frames: int | None) -> list[Path]:
    frames = sorted(frames_dir.glob("frame_*.png"))[:max_frames]
    if len(frames) < 2:
        raise ValueError(f"need at least 2 frames in {frames_dir}")
    return frames


def mean_consecutive_ssim(frames_dir: Path, size: tuple[int, int] = SIZE, max_frames: int | None = None) -> float:
    grays = [_gray(f, size).astype(np.uint8) for f in _frames(frames_dir, max_frames)]
    return float(np.mean([structural_similarity(a, b) for a, b in zip(grays, grays[1:])]))


def static_region_flicker(source_dir: Path, anime_dir: Path, size: tuple[int, int] = SIZE,
                          max_frames: int | None = None, threshold: float = STATIC_THRESHOLD) -> dict[str, float]:
    """Flicker of the stylized frames measured only where the source doesn't move.

    static_fraction: share of pixels that were static (a low value means the shot moves a lot, so
    the numbers rest on little data). static_diff: mean absolute change of the stylized frame on those
    pixels, in 0-255 levels (0 is perfectly steady). static_ssim: SSIM of the stylized frames on them.
    """
    src_files, anime_files = _frames(source_dir, max_frames), _frames(anime_dir, max_frames)
    n = min(len(src_files), len(anime_files))
    src = [_gray(f, size, blur=1.5) for f in src_files[:n]]   # blur so sensor noise isn't read as motion
    anime = [_gray(f, size) for f in anime_files[:n]]
    fractions, diffs, ssims = [], [], []
    for i in range(n - 1):
        mask = np.abs(src[i + 1] - src[i]) < threshold
        if mask.mean() < MIN_STATIC_FRACTION:
            continue
        fractions.append(mask.mean())
        diffs.append(np.abs(anime[i + 1] - anime[i])[mask].mean())
        _, smap = structural_similarity(anime[i].astype(np.uint8), anime[i + 1].astype(np.uint8), full=True)
        ssims.append(smap[mask].mean())
    if not diffs:
        raise ValueError("the source has no static regions to measure (it moves everywhere in every frame)")
    return {"static_fraction": float(np.mean(fractions)), "static_diff": float(np.mean(diffs)),
            "static_ssim": float(np.mean(ssims))}


def flicker_report(source_dir: Path, anime_dir: Path, max_frames: int | None = None) -> dict[str, float]:
    src = mean_consecutive_ssim(source_dir, max_frames=max_frames)
    out = mean_consecutive_ssim(anime_dir, max_frames=max_frames)
    return {"source_ssim": src, "anime_ssim": out, "ratio": out / src,
            **static_region_flicker(source_dir, anime_dir, max_frames=max_frames)}
