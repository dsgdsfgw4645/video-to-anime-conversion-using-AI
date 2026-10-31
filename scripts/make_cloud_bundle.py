"""Pack what the cloud notebook needs into one zip you upload to Kaggle as a dataset.

Run with the project venv:  .venv\Scripts\python.exe scripts\make_cloud_bundle.py [shot] [--project default]
The video, start, seconds and shot come from the config's `input:` section (shot can also be passed). If the
shot has no extracted frames yet, they are extracted from the config's video (no stylizing, so it takes seconds).
The config in the zip is your config/project.yaml if you have one, else project.example.yaml.
Output: work/cloud/bundle_<shot>.zip with the code, workflows, config, the IP-Adapter reference and
work/<project>/frames/<shot>/. No models are included; the notebook downloads them.
"""
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.stylize import ROOT, load_config  # noqa: E402
from pipeline.video import extract_frames  # noqa: E402

CODE = ["cli.py", "pipeline", "workflows", "scripts/download_models.py", "config/project.example.yaml"]


def ensure_frames(cfg: dict, shot: str, frames: Path) -> None:
    """Extract the shot's frames from the config's video if they aren't there yet."""
    if any(frames.glob("frame_*.png")):
        return
    inp = cfg.get("input", {})
    video = ROOT / inp["video"] if inp.get("video") else None
    if inp.get("shot") != shot or video is None or not video.exists():
        raise SystemExit(f"no extracted frames in {frames}, and the config's input.shot/video don't describe '{shot}'. "
                         "Set input.video, start, seconds and shot in the config and run again.")
    n = extract_frames(video, frames, cfg["video"]["work_fps"], inp.get("start", 0), inp.get("seconds"))
    print(f"extracted {n} frames from {video.name}")


def bundle_files(shot: str, project: str) -> list[Path]:
    cfg = load_config()
    files: list[Path] = []
    for item in CODE:
        p = ROOT / item
        files += [f for f in p.rglob("*") if f.is_file() and "__pycache__" not in f.parts] if p.is_dir() else [p]
    if (ROOT / "config" / "project.yaml").exists():
        files.append(ROOT / "config" / "project.yaml")   # read before the example in the cloud too
    reference = ROOT / cfg["animatediff"]["ip_adapter"]["reference"]
    if cfg["animatediff"]["ip_adapter"]["enabled"] and not reference.exists():
        raise SystemExit(f"IP-Adapter reference image not found: {reference}. Set animatediff.ip_adapter.reference in the config.")
    if reference.exists():
        files.append(reference)
    frames = ROOT / "work" / project / "frames" / shot
    ensure_frames(cfg, shot, frames)
    return files + sorted(frames.glob("*"))


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    project = sys.argv[sys.argv.index("--project") + 1] if "--project" in sys.argv else "default"
    shot = args[0] if args and args[0] != project else load_config().get("input", {}).get("shot")
    if not shot:
        raise SystemExit("pass a shot name or set input.shot in the config")
    out = ROOT / "work" / "cloud" / f"bundle_{shot}.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as z:   # PNGs are already compressed
        for f in bundle_files(shot, project):
            z.write(f, f.relative_to(ROOT).as_posix())
    print(f"wrote {out} ({out.stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
