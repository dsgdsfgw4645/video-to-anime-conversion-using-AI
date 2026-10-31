"""Phase 3: flow-warp deflicker (plan.md stage 5).

Each stylized frame is blended with the previous *output* frame, warped along the optical flow of the
SOURCE footage. Where the source is still, the previous anime frame is carried over, so the random
per-frame redraw is averaged away; where it moves, the warp follows the motion; where the warp can't be
trusted (occlusions, fast motion), the fresh stylized frame is used as is. It runs on the CPU (OpenCV),
so it needs no GPU memory on top of stylizing.

Layout: work/<project>/deflicker/<shot>/frame_%05d.png, resumable like the other stages.
"""
import json
from pathlib import Path

import cv2
import numpy as np
from tqdm import tqdm

from pipeline.shot_state import SETTINGS, prepare


def deflicker_settings(cfg: dict, anime_dir: Path) -> dict:
    """What changes a deflickered frame: the temporal settings and the stylized frames' own settings."""
    src = anime_dir / SETTINGS
    return {"temporal": cfg["temporal"],
            "anime": json.loads(src.read_text(encoding="utf-8")) if src.exists() else None}


def _read(path: Path) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(path)
    return img


def blend_frame(anime: np.ndarray, prev_out: np.ndarray, src: np.ndarray, prev_src: np.ndarray,
                strength: float, error_threshold: float, sigma: float = 0) -> np.ndarray:
    """One step: `anime` blended with `prev_out` warped to this frame. All arrays are BGR uint8, same size.

    strength: weight of the warped previous frame where the flow is trusted (0 = off, 1 = copy it).
    error_threshold: mean color error (0-255) between the warped previous source and this source above
    which the warp is not trusted at all.
    sigma: if > 0, only the colors and tones below that blur radius (pixels) are blended; the fresh frame
    keeps its own fine detail and edges, so the warp's softening doesn't show. 0 blends everything.
    """
    g, pg = (cv2.cvtColor(x, cv2.COLOR_BGR2GRAY) for x in (src, prev_src))
    # flow from the current source frame back to the previous one: for each pixel here, where it was.
    flow = cv2.calcOpticalFlowFarneback(g, pg, None, 0.5, 4, 25, 3, 7, 1.5, 0)
    h, w = g.shape
    xs, ys = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    mx, my = xs + flow[..., 0], ys + flow[..., 1]
    warp = lambda img: cv2.remap(img, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    # Trust map: how well does the warped previous SOURCE reproduce this SOURCE frame?
    err = cv2.GaussianBlur(np.abs(warp(prev_src).astype(np.float32) - src.astype(np.float32)).mean(axis=2), (0, 0), 3)
    trust = np.clip(1.0 - err / error_threshold, 0.0, 1.0)[..., None]
    a = strength * trust
    anime_f, warped = anime.astype(np.float32), warp(prev_out).astype(np.float32)
    if sigma > 0:  # move only the low frequencies of the fresh frame toward the warped one
        low = lambda x: cv2.GaussianBlur(x, (0, 0), sigma)
        return np.clip(anime_f + a * (low(warped) - low(anime_f)), 0, 255).astype(np.uint8)
    return np.clip(anime_f * (1 - a) + warped * a, 0, 255).astype(np.uint8)


def output_stage(source: str) -> str:
    """Folder name of the deflickered copy of a stage: `deflicker` for anime, `deflicker_<source>` otherwise."""
    return "deflicker" if source == "anime" else f"deflicker_{source}"


def deflicker_shot(cfg: dict, project_dir: Path, shot: str, source: str = "anime") -> int:
    """Deflicker project_dir/<source>/<shot> (anime, or animatediff) into project_dir/<output_stage>/<shot>. Returns frames made.

    The first frame is copied unchanged. Raises SettingsChanged (nothing touched) if the output folder
    holds frames made with other settings.
    """
    anime_dir, src_dir = project_dir / source / shot, project_dir / "frames" / shot
    out_dir = project_dir / output_stage(source) / shot
    t = cfg["temporal"]
    prepare(out_dir, deflicker_settings(cfg, anime_dir))
    frames = sorted(anime_dir.glob("frame_*.png"))
    made = 0
    for i, f in enumerate(tqdm(frames, desc="deflicker", unit="frame")):
        dest = out_dir / f.name
        if dest.exists():
            continue
        anime = _read(f)
        if i == 0:
            out = anime
        else:
            size = (anime.shape[1], anime.shape[0])
            src, prev_src = (cv2.resize(_read(src_dir / n.name), size, interpolation=cv2.INTER_AREA)
                             for n in (f, frames[i - 1]))
            out = blend_frame(anime, _read(out_dir / frames[i - 1].name), src, prev_src,
                              t["strength"], t["error_threshold"], t.get("lowpass_sigma", 0))
        cv2.imwrite(str(dest), out)
        made += 1
    return made
