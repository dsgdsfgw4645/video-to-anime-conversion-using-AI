"""Phase 4: compare LoRA checkpoints on a fixed prompt grid (same seed everywhere), through ComfyUI.

One txt2img graph (checkpoint -> LoraLoader -> sampler) is run for every prompt x variant. A variant is a
checkpoint file at a weight; the first column is the plain checkpoint with the LoRA at strength 0, as the
baseline. Images land in <out_dir>/<prompt#>_<variant>.png and one labelled sheet, grid.jpg, joins them.
Resumable: finished images are skipped, but only if the grid's settings are unchanged (else it stops).
"""
import json
import shutil
from pathlib import Path

import cv2
import numpy as np

from pipeline.comfy_client import ComfyClient
from pipeline.server import comfy_server

ROOT = Path(__file__).resolve().parents[1]
LORA_DIR = ROOT / "third_party" / "ComfyUI" / "models" / "loras"
SAVE_NODE = "8"


def build_graph(checkpoint: str, lora: str, weight: float, positive: str, negative: str, seed: int,
                size: tuple[int, int], sampling: dict) -> dict:
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint}},
        "2": {"class_type": "LoraLoader", "inputs": {"model": ["1", 0], "clip": ["1", 1], "lora_name": lora,
                                                       "strength_model": weight, "strength_clip": weight}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": positive, "clip": ["2", 1]}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["2", 1]}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": size[0], "height": size[1], "batch_size": 1}},
        "6": {"class_type": "KSampler", "inputs": {
            "model": ["2", 0], "positive": ["3", 0], "negative": ["4", 0], "latent_image": ["5", 0], "seed": seed,
            "steps": sampling["steps"], "cfg": sampling["cfg"], "sampler_name": sampling["sampler"],
            "scheduler": sampling["scheduler"], "denoise": 1.0}},
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
        SAVE_NODE: {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": "lora_grid"}},
    }


def install_loras(files: list[Path]) -> None:
    """Copy LoRA files flat into ComfyUI's models/loras (a running ComfyUI sees new LoRAs without a restart)."""
    LORA_DIR.mkdir(parents=True, exist_ok=True)
    for f in files:
        dst = LORA_DIR / f.name
        if not dst.exists() or dst.stat().st_size != f.stat().st_size:
            shutil.copy2(f, dst)


def sheet(images: list[list[Path | None]], cols: list[str], rows: list[str], out: Path, cell: tuple[int, int]) -> None:
    """One labelled sheet: columns = variants, rows = prompts."""
    cw, ch = cell
    head, side = 44, 0
    canvas = np.full((head + ch * len(rows), cw * len(cols), 3), 24, np.uint8)
    for c, label in enumerate(cols):
        cv2.putText(canvas, label, (c * cw + 6, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
    for r, row in enumerate(images):
        for c, p in enumerate(row):
            if p and p.exists():
                im = cv2.resize(cv2.imread(str(p)), (cw, ch), interpolation=cv2.INTER_AREA)
                canvas[head + r * ch: head + (r + 1) * ch, c * cw: (c + 1) * cw] = im
    cv2.imwrite(str(out), canvas, [cv2.IMWRITE_JPEG_QUALITY, 90])


def run_grid(cfg: dict, name: str, lora_files: list[Path], weights: list[float], prompts: list[dict],
             out_dir: Path, seed: int = 777, size: tuple[int, int] = (512, 768), log=print) -> Path:
    """prompts: [{"label": str, "positive": str, "negative": str (optional extra negatives)}].

    Variants: baseline (first LoRA at strength 0), then each file at weights[0], and the last file at the
    other weights. Returns the path of grid.jpg.
    """
    checkpoint = cfg["models"]["checkpoint"]
    base_neg = cfg["style"]["negative"]
    variants = [("no LoRA", lora_files[-1].name, 0.0)]
    variants += [(f"{'ep' + str(int(f.stem.split('-')[-1])) if '-' in f.stem else 'final'} w{weights[0]}", f.name, weights[0]) for f in lora_files]
    variants += [(f"final w{w}", lora_files[-1].name, w) for w in weights[1:]]
    settings = {"checkpoint": checkpoint, "seed": seed, "size": size, "sampling": cfg["sampling"],
                "style_positive": cfg["style"]["positive"], "prompts": prompts, "variants": variants,
                "lora_sizes": {f.name: f.stat().st_size for f in lora_files}}
    out_dir.mkdir(parents=True, exist_ok=True)
    rec = out_dir / "settings.json"
    settings = json.loads(json.dumps(settings))
    if rec.exists() and json.loads(rec.read_text(encoding="utf-8")) != settings:
        raise RuntimeError(f"Stopped: {out_dir} holds a grid made with different settings. Nothing was changed. "
                           "Delete that folder to make a new grid, or use another name.")
    rec.write_text(json.dumps(settings, indent=2), encoding="utf-8")

    install_loras(lora_files)
    paths = [[out_dir / f"{r + 1}_{c}.png" for c in range(len(variants))] for r in range(len(prompts))]
    todo = [(r, c) for r in range(len(prompts)) for c in range(len(variants)) if not paths[r][c].exists()]
    if todo:
        client = ComfyClient(cfg["comfyui"]["url"])
        with comfy_server(client, cfg):
            for n, (r, c) in enumerate(todo, 1):
                label, lora, w = variants[c]
                pr = prompts[r]
                wf = build_graph(checkpoint, lora, w, f"{cfg['style']['positive']}, {pr['positive']}",
                                 f"{base_neg}, {pr['negative']}" if pr.get("negative") else base_neg,
                                 seed, size, cfg["sampling"])
                client.run(wf, out_dir, names={SAVE_NODE: paths[r][c].name})
                log(f"[{n}/{len(todo)}] {pr['label']} | {label}")
    grid = out_dir / "grid.jpg"
    sheet(paths, [v[0] for v in variants], [p["label"] for p in prompts], grid, (256, 384))
    log(f"Grid: {grid}")
    return grid
