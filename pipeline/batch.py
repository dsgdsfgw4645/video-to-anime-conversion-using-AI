"""Phase 2: stylize every frame of a shot through ComfyUI, one at a time, resumable.

Layout (see CLAUDE.md): work/<project>/<stage>/<shot>/frame_%05d.png. A frame whose anime output
already exists is skipped, so an interrupted run picks up where it stopped. The seed is the same
on every frame of the shot to limit flicker.
"""
import json
from pathlib import Path

from PIL import Image
from tqdm import tqdm

from pipeline.comfy_client import ComfyClient
from pipeline.shot_state import SETTINGS, prepare
from pipeline.stylize import ANIME_NODE, LINEART_NODE, build_workflow


def stylize_settings(cfg: dict, frames_dir: Path, seed: int | None, denoise: float | None) -> dict:
    """Everything that changes a stylized frame: effective sampler values, style, models, and the source frames' own settings."""
    src = frames_dir / SETTINGS
    return {
        "sampling": {**cfg["sampling"],
                     "seed": seed if seed is not None else cfg["sampling"]["seed"],
                     "denoise": denoise if denoise is not None else cfg["sampling"]["denoise"]},
        "style": cfg["style"], "models": cfg["models"], "controlnet": cfg["controlnet"],
        "target_megapixels": cfg["video"]["target_megapixels"],
        "frames": json.loads(src.read_text(encoding="utf-8")) if src.exists() else None,
    }


def stylize_shot(cfg: dict, project_dir: Path, shot: str,
                 seed: int | None = None, denoise: float | None = None) -> int:
    """Stylize project_dir/frames/<shot> into project_dir/anime/<shot> (+ lineart/<shot>). Returns frames made.

    Finished frames are skipped only if they were made with the same settings; otherwise SettingsChanged
    is raised before anything is deleted or overwritten.
    """
    frames_dir = project_dir / "frames" / shot
    prepare(project_dir / "anime" / shot, stylize_settings(cfg, frames_dir, seed, denoise))  # before needing the server
    client = ComfyClient(cfg["comfyui"]["url"])
    if not client.is_up():
        raise RuntimeError("ComfyUI is not reachable. Start it with scripts\\start_comfyui.ps1")
    frames = sorted(frames_dir.glob("frame_*.png"))
    done = 0
    for frame in tqdm(frames, desc="stylize", unit="frame"):
        if (project_dir / "anime" / shot / frame.name).exists():
            continue
        with Image.open(frame) as im:
            size = im.size
        wf = build_workflow(cfg, client.upload_image(frame), size, seed=seed, denoise=denoise)
        entry = client.wait(client.queue(wf))
        client.download_outputs(
            entry, project_dir,
            names={ANIME_NODE: f"anime/{shot}/{frame.name}", LINEART_NODE: f"lineart/{shot}/{frame.name}"},
        )
        done += 1
    return done
