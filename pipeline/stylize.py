"""Build the phase-1 img2img + lineart ComfyUI graph for one frame.

Shared by scripts/test_single_frame.py and the later batch stages, so every caller patches
the workflow JSON the same way. Node ids are hard-coded: if workflows/img2img_lineart_api.json
is renumbered, update build_workflow().
"""
import json
import math
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / "workflows" / "img2img_lineart_api.json"

# Node ids of the two SaveImage nodes in the workflow.
ANIME_NODE = "12"
LINEART_NODE = "13"


def load_config() -> dict:
    """Read config/project.yaml, falling back to config/project.example.yaml."""
    cfg = ROOT / "config" / "project.yaml"
    if not cfg.exists():
        cfg = ROOT / "config" / "project.example.yaml"
    return yaml.safe_load(cfg.read_text(encoding="utf-8"))


def lineart_resolution(megapixels: float, size: tuple[int, int], step: int = 8) -> int:
    """Short side of the frame after ImageScaleToTotalPixels (which rounds to `step`), for the lineart node.

    The preprocessor's `resolution` sets the map's short side, so mirroring the scale step draws the
    lineart at the frame's own size.
    """
    w, h = size
    scale = math.sqrt(megapixels * 1024 * 1024 / (w * h))
    return min(round(w * scale / step), round(h * scale / step)) * step


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
    wf["4"]["inputs"]["text"] = cfg["style"]["positive"]
    wf["5"]["inputs"]["text"] = cfg["style"]["negative"]
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
