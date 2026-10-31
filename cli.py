r"""Video -> anime CLI (phase 2: ingest -> per-frame img2img -> encode).

  .venv\Scripts\python.exe cli.py preview            # video/start/seconds from config `input:`
  .venv\Scripts\python.exe cli.py preview other.mp4 --start 10 --seconds 3   # CLI overrides config
  .venv\Scripts\python.exe cli.py run                # config's slice; set seconds: null for the whole clip
  .venv\Scripts\python.exe cli.py                  # no command = run, so an IDE's run button works
ComfyUI is started automatically if it isn't running (and stopped afterwards if cli.py started it).
Re-running the same command resumes: finished frames are skipped.
"""
from pathlib import Path
from typing import Optional

import typer

from pipeline.batch import stylize_shot
from pipeline.metrics import flicker_report
from pipeline.shot_state import SettingsChanged
from pipeline.stylize import ROOT, load_config
from pipeline.video import encode, extract_frames

app = typer.Typer(add_completion=False)


def resolve_shot(cli_shot: Optional[str], inp: dict, video: Path, suffix: str = "") -> str:
    """--shot wins, then input.shot in the config, then the video's file name plus `suffix`."""
    return cli_shot or inp.get("shot") or f"{video.stem}{suffix}"


def _process(video: Optional[Path], project: str, shot: Optional[str], start: Optional[float],
             seconds: Optional[float], seed: Optional[int], denoise: Optional[float], suffix: str = "") -> None:
    cfg = load_config()
    inp = cfg.get("input", {})
    # CLI options win over the config's `input:` section.
    video = video or (ROOT / inp["video"] if inp.get("video") else None)
    if video is None or not video.exists():
        raise typer.BadParameter(f"video not found: {video}. Pass one or set input.video in the config.")
    start = start if start is not None else inp.get("start", 0)
    seconds = seconds if seconds is not None else inp.get("seconds")
    fps = cfg["video"]["work_fps"]
    shot = resolve_shot(shot, inp, video, suffix)
    pdir = ROOT / "work" / project
    try:
        n = extract_frames(video, pdir / "frames" / shot, fps, start, seconds)
        typer.echo(f"{n} frames at {fps} fps")
        made = stylize_shot(cfg, pdir, shot, seed, denoise)
    except SettingsChanged as e:  # nothing was changed; stop before encoding too
        typer.echo(str(e), err=True)
        raise typer.Exit(1)
    typer.echo(f"stylized {made} new frames")
    out = encode(pdir / "anime" / shot, pdir / "out" / f"{shot}.mp4", fps, video, start, seconds)
    typer.echo(f"wrote {out}")


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """With no command (e.g. the IDE's run button), run the config's input slice."""
    if ctx.invoked_subcommand is None:
        run(video=None, project="default", shot=None, start=None, seconds=None, seed=None, denoise=None)


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
    _process(video, project, shot, start, seconds, seed, denoise, suffix="_preview")


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
def flicker(
    shot: Optional[str] = typer.Argument(None, help="defaults to input.shot in the config"),
    project: str = "default",
    frames: Optional[int] = typer.Option(None, help="only use the first N frames"),
) -> None:
    """Flicker of a stylized shot: whole-frame SSIM vs the source, and change in static regions (lower = steadier)."""
    inp = load_config().get("input", {})
    shot = shot or inp.get("shot")
    if not shot:
        raise typer.BadParameter("pass a shot name or set input.shot in the config.")
    pdir = ROOT / "work" / project
    r = flicker_report(pdir / "frames" / shot, pdir / "anime" / shot, frames)
    typer.echo(f"whole frame:    source SSIM {r['source_ssim']:.3f}  anime SSIM {r['anime_ssim']:.3f}  ratio {r['ratio']:.3f}")
    typer.echo(f"static regions: {r['static_fraction']:.0%} of pixels; anime changes by {r['static_diff']:.2f} levels "
               f"(0 = steady), SSIM {r['static_ssim']:.3f}")


if __name__ == "__main__":
    app()
