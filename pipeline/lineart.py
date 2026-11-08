"""Steadier lineart for the ControlNet (`controlnet.smooth_radius`).

The lineart extractor redraws the face's lines a little differently on every frame (a jaw line appears,
fades or shifts), and the ControlNet follows whatever it is given. With `smooth_radius` > 0 the maps are
made first (ComfyUI, preprocessor only, `lineart_raw/<shot>`), then each map is replaced by the per-pixel
median of itself and `smooth_radius` maps on each side, warped onto it along the SOURCE footage's optical
flow (the same machinery as the median deflicker), and saved to `lineart_smooth/<shot>`. The stylizer then
feeds those maps to the ControlNet instead of the raw ones.
"""
from pathlib import Path

import cv2
from tqdm import tqdm

from pipeline.temporal import _read, median_frame

ERROR_THRESHOLD = 25   # same meaning as temporal.error_threshold


def smooth_maps(raws: list, srcs: list, radius: int, error_threshold: float = ERROR_THRESHOLD) -> list:
    """Median-smooth a list of lineart maps (BGR uint8) over time; srcs are the matching source frames, same size."""
    out = []
    for i, raw in enumerate(raws):
        near = [(raws[k], srcs[k]) for k in range(max(0, i - radius), min(len(raws), i + radius + 1)) if k != i]
        out.append(median_frame(raw, srcs[i], near, error_threshold, sigma=0, strength=1.0))
    return out


def make_smooth_lineart(cfg: dict, client, project_dir: Path, shot: str, build_raw_workflow) -> Path:
    """Fill lineart_raw/<shot> (via ComfyUI) and lineart_smooth/<shot>; returns the smooth folder. Resumable."""
    radius = int(cfg["controlnet"]["smooth_radius"])
    frames = sorted((project_dir / "frames" / shot).glob("frame_*.png"))
    raw_dir, smooth_dir = project_dir / "lineart_raw" / shot, project_dir / "lineart_smooth" / shot
    raw_dir.mkdir(parents=True, exist_ok=True)
    smooth_dir.mkdir(parents=True, exist_ok=True)
    for f in tqdm([f for f in frames if not (raw_dir / f.name).exists()], desc="lineart", unit="frame"):
        wf, node = build_raw_workflow(f)
        client.download_outputs(client.wait(client.queue(wf)), project_dir, names={node: f"lineart_raw/{shot}/{f.name}"})
    if all((smooth_dir / f.name).exists() for f in frames):
        return smooth_dir
    raws = [_read(raw_dir / f.name) for f in frames]
    size = (raws[0].shape[1], raws[0].shape[0])
    srcs = [cv2.resize(_read(f), size, interpolation=cv2.INTER_AREA) for f in frames]
    for f, m in zip(frames, smooth_maps(raws, srcs, radius)):
        cv2.imwrite(str(smooth_dir / f.name), m)
    return smooth_dir
