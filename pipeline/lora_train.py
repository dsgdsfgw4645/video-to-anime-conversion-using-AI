"""Phase 4: train a LoRA locally with kohya sd-scripts, tuned for the 6 GB RTX 2060.

Memory plan: 512 px with aspect buckets, batch 1, fp16 mixed precision, gradient checkpointing,
8-bit AdamW, latents cached, scaled-dot-product attention. Base model = the same checkpoint the ComfyUI
workflows use (Counterfeit), at the default clip skip, because the workflows have no clip-skip node.
"""
import json
import math
import os
import socket
import subprocess
import sys
from pathlib import Path

from pipeline.captioning import list_images

ROOT = Path(__file__).resolve().parents[1]
KOHYA = ROOT / "third_party" / "sd-scripts"
PY = ROOT / ".venv-train" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")

LORA = {"network_dim": 32, "network_alpha": 16, "learning_rate": 1e-4, "text_encoder_lr": 5e-5,
        "resolution": 512, "epochs": 10, "save_every_n_epochs": 2, "seed": 42}


class TrainingError(RuntimeError):
    pass


def plan(images: int, steps: int, epochs: int) -> int:
    """Repeats per image so that images * repeats * epochs is close to the wanted total steps."""
    return max(1, math.ceil(steps / (images * epochs)))


def dataset_toml(image_dir: Path, repeats: int, resolution: int, flip: bool) -> str:
    # keep_tokens = 1 keeps the trigger word first when captions are shuffled; toml paths use /
    return f"""[general]
shuffle_caption = true
caption_extension = ".txt"
keep_tokens = 1

[[datasets]]
resolution = {resolution}
batch_size = 1
enable_bucket = true
min_bucket_reso = 256
max_bucket_reso = 1024
bucket_reso_steps = 64

  [[datasets.subsets]]
  image_dir = "{image_dir.as_posix()}"
  num_repeats = {repeats}
  flip_aug = {str(flip).lower()}
"""


def build_command(checkpoint: Path, toml: Path, out_dir: Path, name: str, p: dict, max_steps: int | None = None) -> list[str]:
    cmd = [str(PY), "train_network.py",
           "--pretrained_model_name_or_path", str(checkpoint),
           "--dataset_config", str(toml),
           "--output_dir", str(out_dir), "--output_name", name,
           "--logging_dir", str(out_dir / "logs"),
           "--network_module", "networks.lora",
           "--network_dim", str(p["network_dim"]), "--network_alpha", str(p["network_alpha"]),
           "--learning_rate", str(p["learning_rate"]), "--text_encoder_lr", str(p["text_encoder_lr"]),
           "--optimizer_type", "AdamW8bit", "--lr_scheduler", "cosine", "--lr_warmup_steps", "100",
           "--mixed_precision", "fp16", "--save_precision", "fp16", "--save_model_as", "safetensors",
           "--gradient_checkpointing", "--cache_latents", "--sdpa",
           "--max_data_loader_n_workers", "0", "--seed", str(p["seed"])]
    if max_steps:   # kohya ignores max_train_steps when max_train_epochs is set, so give only one of them
        cmd += ["--max_train_steps", str(max_steps)]
    else:
        cmd += ["--max_train_epochs", str(p["epochs"]), "--save_every_n_epochs", str(p["save_every_n_epochs"])]
    return cmd


def comfyui_running(host: str = "127.0.0.1", port: int = 8188) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def train(name: str, image_dir: Path, checkpoint: Path, out_root: Path, steps: int, p: dict | None = None,
          flip: bool = False, smoke: bool = False, log=print) -> Path:
    """Train one LoRA into out_root/<name>/<name>.safetensors. Returns that path."""
    p = {**LORA, **(p or {})}
    images = list_images(image_dir)
    if not images:
        raise TrainingError(f"No images in {image_dir}. Run extract_style.py / caption.py first.")
    missing = [i.name for i in images if not i.with_suffix(".txt").exists()]
    if missing:
        raise TrainingError(f"{len(missing)} images have no caption (e.g. {missing[0]}). Run training/caption.py.")
    if not PY.exists() or not KOHYA.exists():
        raise TrainingError("Training environment missing. Run scripts/setup_training.py.")
    if not checkpoint.exists():
        raise TrainingError(f"Base checkpoint not found: {checkpoint}. Run scripts/download_models.py.")
    if comfyui_running():
        raise TrainingError("ComfyUI is running on port 8188 and holds the GPU. Stop it, then run again.")

    repeats = plan(len(images), steps, p["epochs"])
    out_dir = out_root / (name + ("_smoketest" if smoke else ""))
    final = out_dir / f"{name}.safetensors"
    record = {"images": len(images), "repeats": repeats, "flip": flip, "checkpoint": checkpoint.name, **p}
    rec = out_dir / "settings.json"
    if final.exists() and not smoke:
        old = json.loads(rec.read_text(encoding="utf-8")) if rec.exists() else None
        if old == record:
            log(f"{final} already trained with these settings; nothing to do.")
            return final
        raise TrainingError(f"Stopped: {final} exists and the settings differ ({'no record' if old is None else 'changed'}). "
                            "Nothing was changed. Set a new training.<target>.run name in the config to train again.")
    out_dir.mkdir(parents=True, exist_ok=True)
    toml = out_dir / "dataset.toml"
    toml.write_text(dataset_toml(image_dir, repeats, p["resolution"], flip), encoding="utf-8")
    log(f"Training {name}: {len(images)} images x {repeats} repeats x {p['epochs']} epochs "
        f"= about {len(images) * repeats * p['epochs']} steps" + (" (smoke test: 20 steps)" if smoke else ""))
    r = subprocess.run(build_command(checkpoint, toml, out_dir, name, p, 20 if smoke else None), cwd=KOHYA,
                       env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})   # kohya prints non-cp1252 characters
    if r.returncode:
        raise TrainingError(f"kohya train_network.py failed (exit code {r.returncode}); see the output above.")
    if not smoke:
        rec.write_text(json.dumps(record, indent=2), encoding="utf-8")
    log(f"Done: {final}")
    return final
