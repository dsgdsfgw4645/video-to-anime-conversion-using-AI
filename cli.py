"""Video -> anime CLI (phase 2: ingest -> per-frame img2img -> encode).

  .venv\Scripts\python.exe cli.py preview            # video/start/seconds from config `input:`
  .venv\Scripts\python.exe cli.py preview other.mp4 --start 10 --seconds 3   # CLI overrides config
  .venv\Scripts\python.exe cli.py run                # config's slice; set seconds: null for the whole clip
Re-running the same command resumes: finished frames are skipped.
"""
from pathlib import Path
from typing import Optional

import typer

from pipeline.batch import stylize_shot
from pipeline.metrics import flicker_report
from pipeline.stylize import ROOT, load_config
from pipeline.video import encode, extract_frames

app = typer.Typer(add_completion=False)


def _process(video: Optional[Path], project: str, shot: Optional[str], start: Optional[float],
             seconds: Optional[float], seed: Optional[int], denoise: Optional[float]) -> None:
    cfg = load_config()
    inp = cfg.get("input", {})
    # CLI options win over the config's `input:` section.
    video = video or (ROOT / inp["video"] if inp.get("video") else None)
    if video is None or not video.exists():
        raise typer.BadParameter(f"video not found: {video}. Pass one or set input.video in the config.")
    start = start if start is not None else inp.get("start", 0)
    seconds = seconds if seconds is not None else inp.get("seconds")
    fps = cfg["video"]["work_fps"]
    shot = shot or video.stem
    pdir = ROOT / "work" / project
    n = extract_frames(video, pdir / "frames" / shot, fps, start, seconds)
    typer.echo(f"{n} frames at {fps} fps")
    made = stylize_shot(cfg, pdir, shot, seed, denoise)
    typer.echo(f"stylized {made} new frames")
    out = encode(pdir / "anime" / shot, pdir / "out" / f"{shot}.mp4", fps, video, start, seconds)
    typer.echo(f"wrote {out}")


@app.command()
def preview(
    video: Optional[Path] = typer.Argument(None, help="defaults to input.video in the config"),
    start: Optional[float] = typer.Option(None, help="start time in seconds (default: config input.start)"),
    seconds: Optional[float] = typer.Option(None, help="length in seconds (default: config input.seconds, else 4)"),
    project: str = "default", shot: Optional[str] = None,
    seed: Optional[int] = None, denoise: Optional[float] = None,
) -> None:
    """Stylize a short slice of the clip."""
    if seconds is None:
        seconds = load_config().get("input", {}).get("seconds") or 4
    name = shot or f"{(video or Path(load_config()['input']['video'])).stem}_preview"
    _process(video, project, name, start, seconds, seed, denoise)


@app.command()
def run(
    video: Optional[Path] = typer.Argument(None, help="defaults to input.video in the config"),
    project: str = "default", shot: Optional[str] = None,
    start: Optional[float] = None, seconds: Optional[float] = None,
    seed: Optional[int] = None, denoise: Optional[float] = None,
) -> None:
    """Stylize the config's slice (or --start/--seconds of it); seconds: null in config = whole clip."""
    _process(video, project, shot, start, seconds, seed, denoise)


@app.command()
def flicker(shot: str, project: str = "default") -> None:
    """Mean consecutive-frame SSIM of a stylized shot vs its source (the phase 2 baseline to beat)."""
    pdir = ROOT / "work" / project
    r = flicker_report(pdir / "frames" / shot, pdir / "anime" / shot)
    typer.echo(f"source {r['source_ssim']:.3f}  anime {r['anime_ssim']:.3f}  ratio {r['ratio']:.3f}")


if __name__ == "__main__":
    app()
