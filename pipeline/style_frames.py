"""Phase 4: pull a varied, clean set of training frames out of a film (the style dataset for the style LoRA).

Steps: find the letterbox bars and crop them, sample the film twice a second, split it into scenes at
colour-histogram jumps, take the sharpest good frame from every few seconds of each scene, drop near
duplicates, and cap the count by spreading the picks evenly over the film's length.
Output: <out_dir>/frame_00001.png ... plus settings.json and contact_sheet.jpg (look at it before training).
"""
from pathlib import Path

import cv2
import numpy as np

from pipeline.shot_state import prepare

VIDEO_EXT = {".mkv", ".mp4", ".avi", ".mov", ".webm", ".m4v", ".mpg", ".mpeg", ".ts", ".wmv"}

DEFAULTS = {
    "max_images": 250,          # cap; the picks are spread evenly over the film
    "sample_interval": 0.5,     # seconds between sampled frames
    "scene_cut": 0.5,           # histogram correlation below this between samples = new scene
    "max_scene_seconds": 6.0,   # long scenes give one frame per this many seconds
    "skip_start_pct": 1.0,      # skip the studio logos
    "skip_end_pct": 8.0,        # skip the credits
    "crop_bottom_pct": 0.0,     # extra crop (percent of the picture height) if subtitles are burned in
    "max_side": 1024,           # saved long side in pixels (training uses 512, so this is plenty)
    "dedupe": 6.0,              # frames closer than this (0-255 mean pixel difference at 16x16) count as the same
}


def find_video(folder: Path) -> Path | None:
    """The largest video file in `folder`, or None."""
    files = [p for p in folder.glob("*") if p.suffix.lower() in VIDEO_EXT] if folder.is_dir() else []
    return max(files, key=lambda p: p.stat().st_size) if files else None


def detect_crop(cap: cv2.VideoCapture, samples: int = 40, dark: float = 20.0) -> tuple[tuple[int, int], tuple[int, int]]:
    """((x0, x1), (y0, y1)) of the picture without black bars. A row or column is a bar if it stays dark in every sample."""
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    h, w = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)), int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    rows, cols = np.zeros(h), np.zeros(w)
    for i in np.linspace(n * 0.05, n * 0.9, samples).astype(int):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
        ok, f = cap.read()
        if not ok:
            continue
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32)
        rows, cols = np.maximum(rows, g.mean(1)), np.maximum(cols, g.mean(0))
    return _span(cols, dark, w), _span(rows, dark, h)


def _span(profile: np.ndarray, dark: float, size: int) -> tuple[int, int]:
    lit = np.where(profile >= dark)[0]
    if len(lit) == 0:
        return 0, size
    lo, hi = int(lit[0]), int(lit[-1]) + 1
    # leave a few pixels off the edge so a soft bar border can't leak in
    pad = 2 if (lo > 0 or hi < size) else 0
    return lo + pad, hi - pad


def _hist(frame: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(cv2.resize(frame, (160, 90), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2HSV)
    h = cv2.calcHist([hsv], [0, 1], None, [16, 8], [0, 180, 0, 256])
    return cv2.normalize(h, h).flatten()


def scan(cap: cv2.VideoCapture, box: tuple[int, int, int, int], p: dict) -> list[dict]:
    """One pass over the film: for every sampled frame keep its index, histogram, sharpness and brightness."""
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    step = max(1, round(fps * p["sample_interval"]))
    first, last = int(n * p["skip_start_pct"] / 100), int(n * (1 - p["skip_end_pct"] / 100))
    x0, y0, x1, y1 = box
    cap.set(cv2.CAP_PROP_POS_FRAMES, first)
    out, i = [], first
    while i < last:
        if not cap.grab():
            break
        if (i - first) % step == 0:
            ok, f = cap.retrieve()
            if ok:
                f = f[y0:y1, x0:x1]
                g = cv2.cvtColor(cv2.resize(f, (480, max(1, round(480 * f.shape[0] / f.shape[1]))),
                                            interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
                out.append({"idx": i, "t": i / fps, "hist": _hist(f), "sharp": float(cv2.Laplacian(g, cv2.CV_64F).var()),
                            "mean": float(g.mean()), "std": float(g.std()),
                            "thumb": cv2.resize(g, (16, 16), interpolation=cv2.INTER_AREA).astype(np.float32)})
        i += 1
    return out


def pick(samples: list[dict], p: dict) -> list[dict]:
    """Choose the frames to save from the scan: sharpest good frame per scene chunk, deduplicated, capped."""
    if not samples:
        return []
    median_sharp = float(np.median([s["sharp"] for s in samples]))
    good = lambda s: 25 <= s["mean"] <= 235 and s["std"] >= 18 and s["sharp"] >= 0.25 * median_sharp  # noqa: E731

    scenes, cur = [], [samples[0]]
    for a, b in zip(samples, samples[1:]):
        if cv2.compareHist(a["hist"], b["hist"], cv2.HISTCMP_CORREL) < p["scene_cut"]:
            scenes.append(cur)
            cur = []
        cur.append(b)
    scenes.append(cur)

    picks = []
    for sc in scenes:
        if len(sc) >= 3:                       # the first and last samples of a scene sit on the cut or its fade
            sc = sc[1:-1]
        t0 = sc[0]["t"]
        chunks: dict[int, list[dict]] = {}
        for s in sc:
            chunks.setdefault(int((s["t"] - t0) // p["max_scene_seconds"]), []).append(s)
        for chunk in chunks.values():
            ok = [s for s in chunk if good(s)]
            if ok:
                picks.append(max(ok, key=lambda s: s["sharp"]))

    picks.sort(key=lambda s: s["idx"])
    kept = []
    for s in picks:                            # drop near duplicates of anything already kept
        if all(float(np.abs(s["thumb"] - k["thumb"]).mean()) >= p["dedupe"] for k in kept):
            kept.append(s)
    if len(kept) > p["max_images"]:
        kept = [kept[i] for i in np.linspace(0, len(kept) - 1, p["max_images"]).round().astype(int)]
    return kept


def contact_sheet(paths: list[Path], out: Path, cols: int = 10, cell: int = 192) -> None:
    rows = []
    for r in range(0, len(paths), cols):
        tiles = []
        for p in paths[r:r + cols]:
            im = cv2.imread(str(p))
            k = cell / max(im.shape[:2])
            small = cv2.resize(im, (max(1, round(im.shape[1] * k)), max(1, round(im.shape[0] * k))), interpolation=cv2.INTER_AREA)
            tile = np.zeros((cell, cell, 3), np.uint8)
            y, x = (cell - small.shape[0]) // 2, (cell - small.shape[1]) // 2
            tile[y:y + small.shape[0], x:x + small.shape[1]] = small
            tiles.append(tile)
        tiles += [np.zeros((cell, cell, 3), np.uint8)] * (cols - len(tiles))
        rows.append(np.hstack(tiles))
    cv2.imwrite(str(out), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 85])


def extract_style_frames(video: Path, out_dir: Path, params: dict | None = None, log=print) -> int:
    """Write the style dataset into out_dir. Resumable; changed settings raise SettingsChanged and touch nothing."""
    p = {**DEFAULTS, **(params or {})}
    st = video.stat()
    prepare(out_dir, {"video": str(video.resolve()), "size": st.st_size, "mtime_ns": st.st_mtime_ns, **p})
    existing = sorted(out_dir.glob("frame_*.png"))
    if existing:
        log(f"{len(existing)} frames already in {out_dir} (same settings); nothing to do.")
        return len(existing)

    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open {video}")
    (x0, x1), (y0, y1) = detect_crop(cap)
    y1 = y1 - round((y1 - y0) * p["crop_bottom_pct"] / 100)
    log(f"Picture area: x {x0}-{x1}, y {y0}-{y1} (letterbox bars removed)")
    log("Scanning the film (a few minutes for a feature film) ...")
    samples = scan(cap, (x0, y0, x1, y1), p)
    chosen = pick(samples, p)
    log(f"{len(samples)} frames sampled, {len(chosen)} chosen")

    scale = min(1.0, p["max_side"] / max(x1 - x0, y1 - y0))
    for n, s in enumerate(chosen, 1):
        cap.set(cv2.CAP_PROP_POS_FRAMES, s["idx"])
        ok, f = cap.read()
        if not ok:
            continue
        f = f[y0:y1, x0:x1]
        if scale < 1.0:
            f = cv2.resize(f, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        cv2.imwrite(str(out_dir / f"frame_{n:05d}.png"), f)
    cap.release()
    saved = sorted(out_dir.glob("frame_*.png"))
    if saved:
        contact_sheet(saved, out_dir / "contact_sheet.jpg")
    log(f"Saved {len(saved)} frames to {out_dir}. Open contact_sheet.jpg there and delete any bad frames "
        "(subtitles, logos, blur) before captioning.")
    return len(saved)
