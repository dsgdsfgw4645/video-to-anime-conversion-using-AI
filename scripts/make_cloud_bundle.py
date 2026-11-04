r"""Pack what the cloud notebook needs into one zip you upload to Kaggle as a dataset.

Run with the project venv:  .venv\Scripts\python.exe scripts\make_cloud_bundle.py [shot] [--set KEY=VALUE ...]
The video, start and seconds come from the config's `input:` section; the shot is `shot` if given, else
input.shot. If the shot has no extracted frames yet, they are extracted from the config's video (no stylizing,
so it takes seconds). `--set` changes a config value in the zip only, so a variant needs no config edit, e.g.
an AnimateDiff-only run under a new shot name:
    scripts\make_cloud_bundle.py dance_run1_noip --set animatediff.ip_adapter.enabled=false
The zip carries the effective config (your config/project.yaml or the example, plus the shot and --set values)
as config/project.yaml. Output: work/cloud/bundle_<shot>.zip with the code, workflows, config, the IP-Adapter
reference, work/<project>/frames/<shot>/ and the LoRA files named in style.loras (stored under loras/; the notebook
copies them into ComfyUI's models/loras). The base models are not included; the notebook downloads them.
"""
import argparse
import sys
import zipfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.stylize import LORA_DIR, ROOT, load_config  # noqa: E402
from pipeline.video import extract_frames  # noqa: E402

CODE = ["cli.py", "pipeline", "workflows", "scripts/download_models.py"]


def apply_overrides(cfg: dict, sets: list[str]) -> dict:
    """Return cfg with each 'a.b.c=value' applied (the value is read as YAML: false, 0.7, name ...)."""
    for item in sets:
        key, sep, value = item.partition("=")
        if not sep:
            raise SystemExit(f"--set needs KEY=VALUE, got '{item}'")
        *path, leaf = key.split(".")
        node = cfg
        for part in path:
            if not isinstance(node.get(part), dict):
                raise SystemExit(f"--set {key}: '{part}' is not a section of the config")
            node = node[part]
        if leaf not in node:
            raise SystemExit(f"--set {key}: no such setting")
        node[leaf] = yaml.safe_load(value)
    return cfg


def ensure_frames(cfg: dict, frames: Path) -> None:
    """Extract the shot's frames from the config's video if they aren't there yet."""
    if any(frames.glob("frame_*.png")):
        return
    inp = cfg.get("input", {})
    video = ROOT / inp["video"] if inp.get("video") else None
    if video is None or not video.exists():
        raise SystemExit(f"no extracted frames in {frames}, and input.video in the config doesn't point to a file.")
    n = extract_frames(video, frames, cfg["video"]["work_fps"], inp.get("start", 0), inp.get("seconds"))
    print(f"extracted {n} frames from {video.name}")


def find_lora(name: str) -> Path:
    """A LoRA file by name: ComfyUI's models/loras first, else training/output/<run>/."""
    for found in [LORA_DIR / name, *sorted((ROOT / "training" / "output").glob(f"*/{name}"))]:
        if found.is_file():
            return found
    raise SystemExit(f"LoRA {name} (style.loras in the config) is in neither {LORA_DIR} nor training/output/<run>/. Train it or fix the name.")


def bundle(cfg: dict, shot: str, project: str) -> tuple[list[tuple[Path, str]], str]:
    """(file, name inside the zip) pairs, and the config text to store in it as config/project.yaml."""
    files: list[Path] = []
    for item in CODE:
        p = ROOT / item
        files += [f for f in p.rglob("*") if f.is_file() and "__pycache__" not in f.parts] if p.is_dir() else [p]
    ip = cfg["animatediff"]["ip_adapter"]
    reference = ROOT / ip["reference"]
    if ip["enabled"] and not reference.exists():
        raise SystemExit(f"IP-Adapter reference image not found: {reference}. Set animatediff.ip_adapter.reference in the config.")
    if reference.exists():
        files.append(reference)
    frames = ROOT / "work" / project / "frames" / shot
    ensure_frames(cfg, frames)
    pairs = [(f, f.relative_to(ROOT).as_posix()) for f in files + sorted(frames.glob("*"))]
    pairs += [(find_lora(l["name"]), f"loras/{l['name']}") for l in cfg["style"].get("loras") or []]
    return pairs, yaml.safe_dump(cfg, sort_keys=False)


def main() -> None:
    ap = argparse.ArgumentParser(description="Pack the Kaggle bundle for a shot.")
    ap.add_argument("shot", nargs="?", help="shot name (default: input.shot in the config)")
    ap.add_argument("--project", default="default")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="override a config value in the bundle only")
    a = ap.parse_args()
    cfg = load_config()
    shot = a.shot or cfg.get("input", {}).get("shot")
    if not shot:
        raise SystemExit("pass a shot name or set input.shot in the config")
    cfg.setdefault("input", {})["shot"] = shot
    cfg = apply_overrides(cfg, a.set)
    files, config_text = bundle(cfg, shot, a.project)
    out = ROOT / "work" / "cloud" / f"bundle_{shot}.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as z:   # PNGs are already compressed
        for f, arcname in files:
            z.write(f, arcname)
        z.writestr("config/project.yaml", config_text)
    print(f"wrote {out} ({out.stat().st_size / 1e6:.0f} MB)")
    for lora in cfg["style"].get("loras") or []:
        print(f"  LoRA included: {lora['name']} (weight {lora['weight']})")


if __name__ == "__main__":
    main()
