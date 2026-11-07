"""Build the phase-1 img2img + lineart ComfyUI graph for one frame.

Shared by scripts/test_single_frame.py and the later batch stages, so every caller patches
the workflow JSON the same way. Node ids are hard-coded: if workflows/img2img_lineart_api.json
is renumbered, update build_workflow().
"""
import json
import math
import os
import shutil
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / "workflows" / "img2img_lineart_api.json"

# Node ids of the two SaveImage nodes in the workflow.
ANIME_NODE = "12"
LINEART_NODE = "13"


def load_config() -> dict:
    """Read config/project.yaml, falling back to config/project.example.yaml.

    The environment variable ANIME_CONFIG (a path) overrides both, for trying a variant without editing the config.
    """
    cfg = Path(os.environ["ANIME_CONFIG"]) if os.environ.get("ANIME_CONFIG") else ROOT / "config" / "project.yaml"
    if not cfg.exists():
        cfg = ROOT / "config" / "project.example.yaml"
    data = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    for lora in (data.get("style") or {}).get("loras") or []:   # `file` alone is enough: the name is its file name
        if lora.get("file") and not lora.get("name"):
            lora["name"] = Path(lora["file"]).name
    return data


def lineart_resolution(megapixels: float, size: tuple[int, int], step: int = 8) -> int:
    """Short side of the frame after ImageScaleToTotalPixels (which rounds to `step`), for the lineart node.

    The preprocessor's `resolution` sets the map's short side, so mirroring the scale step draws the
    lineart at the frame's own size.
    """
    w, h = size
    scale = math.sqrt(megapixels * 1024 * 1024 / (w * h))
    return min(round(w * scale / step), round(h * scale / step)) * step


LORA_DIR = ROOT / "third_party" / "ComfyUI" / "models" / "loras"


def lora_file(lora: dict) -> Path | None:
    """The file a style.loras entry points at with `file:` (relative to the project root, or absolute), else None."""
    return (ROOT / lora["file"]) if lora.get("file") else None


def style_record(style: dict) -> dict:
    """The style section as recorded in a shot's settings.json: no empty `loras`, and no `file` paths
    (moving a LoRA file on disk is not a changed setting; its `name` and `weight` are)."""
    out = {k: v for k, v in style.items() if k != "loras" or v}   # no loras = same record as before LoRAs existed
    if out.get("loras"):
        out["loras"] = [{k: v for k, v in l.items() if k != "file"} for l in out["loras"]]
    return out


def install_loras(cfg: dict) -> None:
    """Make sure every LoRA in style.loras is in ComfyUI's models/loras.

    An entry with `file:` is copied from there (again if its size changed). Without `file:` an existing
    models/loras/<name> is used, else it is looked for in training/output/<run>/. In the cloud the notebook has
    already put the files in models/loras and the bundled config has no `file:`.
    """
    for lora in cfg["style"].get("loras") or []:
        dst = LORA_DIR / lora["name"]
        src = lora_file(lora)
        if src is not None:
            if not src.is_file():
                raise FileNotFoundError(f"LoRA file not found: {src} (style.loras `file:` in the config).")
            if not dst.exists() or dst.stat().st_size != src.stat().st_size:
                LORA_DIR.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            continue
        if dst.exists():
            continue
        found = sorted((ROOT / "training" / "output").glob(f"*/{lora['name']}"))
        if not found:
            raise FileNotFoundError(f"LoRA {lora['name']} is in neither {LORA_DIR} nor training/output/<run>/. Train it first.")
        LORA_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(found[0], dst)


def apply_loras(wf: dict, loras: list[dict], positive: str, negative: str, model_node: str = "10") -> tuple[str, str]:
    """Chain a LoraLoader per entry after the checkpoint (node 1) and rewire what read the checkpoint's model and clip.

    Entries: {name, weight, trigger (optional, put first in the prompt), negative (optional, added to the negative prompt)}.
    New nodes get ids "20", "21", ... Returns the positive and negative prompt with the triggers / extra negatives added.
    model_node: the node whose "model" input receives the LoRA'd model ("10" = the KSampler of the img2img graph;
    the AnimateDiff graph passes the node that reads the checkpoint's model).
    """
    model, clip = ["1", 0], ["1", 1]
    triggers, extra = [], []
    for i, lora in enumerate(loras or []):
        node = str(20 + i)
        wf[node] = {"class_type": "LoraLoader", "inputs": {
            "model": model, "clip": clip, "lora_name": lora["name"],
            "strength_model": lora["weight"], "strength_clip": lora["weight"]}}
        model, clip = [node, 0], [node, 1]
        if lora.get("trigger"):
            triggers.append(lora["trigger"])
        if lora.get("negative"):
            extra.append(lora["negative"])
    if loras:
        wf[model_node]["inputs"]["model"] = model
        wf["4"]["inputs"]["clip"] = clip
        wf["5"]["inputs"]["clip"] = clip
    return ", ".join(triggers + [positive]), ", ".join([negative] + extra)


def build_workflow(
    cfg: dict,
    image_name: str,
    size: tuple[int, int],
    seed: int | None = None,
    denoise: float | None = None,
) -> dict:
    """Return the workflow with config values written in.

    image_name: the name ComfyUI returned from upload_image (goes into the LoadImage node).
    size: (width, height) of that image, used to size the lineart map.
    seed, denoise: override the config values (e.g. a per-shot seed).
    """
    wf = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    s = cfg["sampling"]
    wf["1"]["inputs"]["ckpt_name"] = cfg["models"]["checkpoint"]
    wf["2"]["inputs"]["image"] = image_name
    wf["3"]["inputs"]["megapixels"] = cfg["video"]["target_megapixels"]
    wf["7"]["inputs"]["resolution"] = lineart_resolution(
        wf["3"]["inputs"]["megapixels"], size, wf["3"]["inputs"]["resolution_steps"])
    wf["4"]["inputs"]["text"], wf["5"]["inputs"]["text"] = apply_loras(
        wf, cfg["style"].get("loras"), cfg["style"]["positive"], cfg["style"]["negative"])
    wf["6"]["inputs"]["control_net_name"] = cfg["models"]["controlnet_lineart"]
    wf["8"]["inputs"]["strength"] = cfg["controlnet"]["lineart_strength"]
    wf["10"]["inputs"].update(
        seed=seed if seed is not None else s["seed"],
        steps=s["steps"],
        cfg=s["cfg"],
        sampler_name=s["sampler"],
        scheduler=s["scheduler"],
        denoise=denoise if denoise is not None else s["denoise"],
    )
    return wf
