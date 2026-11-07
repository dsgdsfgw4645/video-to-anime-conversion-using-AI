"""Phase 3: stylize a whole shot in ONE ComfyUI pass with AnimateDiff and the lineart ControlNet (IP-Adapter optional, off by default).

Unlike pipeline/batch.py (one independent image per frame), the frames go through the sampler as one
batch; AnimateDiff's motion module, run over overlapping 16-frame windows, makes neighbouring frames agree,
and, if enabled, IP-Adapter ties the colors to a reference image. Needs far more than 6 GB at once, so it is meant for a
cloud GPU (see docs/cloud-kaggle.md). The ComfyUI it talks to needs AnimateDiff-Evolved,
ComfyUI_IPAdapter_plus, ComfyUI-VideoHelperSuite and ComfyUI-Advanced-ControlNet (the stock ControlNet nodes
fail with AnimateDiff's sliding windows), plus the models `scripts/download_models.py --cloud` fetches.

Layout: work/<project>/animatediff/<shot>/frame_%05d.png. One pass makes the whole shot, so a shot is
all or nothing: if the pass fails, nothing is written.
"""
import json
import shutil
from pathlib import Path

from PIL import Image

from pipeline.comfy_client import ComfyClient
from pipeline.server import comfy_server
from pipeline.shot_state import SETTINGS, prepare
from pipeline.stylize import ROOT, apply_loras, install_loras, lineart_resolution, style_record
from pipeline.vram import VramMonitor

WORKFLOW = ROOT / "workflows" / "animatediff_lineart_api.json"
OUTPUT_NODE = "12"
IP_NODES = ("14", "15", "16")   # LoadImage, IPAdapterUnifiedLoader, IPAdapter
STAGE = "animatediff"


def build_workflow(cfg: dict, frames_dir: Path, reference_name: str | None, size: tuple[int, int],
                   seed: int | None = None, denoise: float | None = None) -> dict:
    """The AnimateDiff graph with config values written in.

    frames_dir: absolute path ComfyUI reads the source frames from (the same machine as ComfyUI).
    reference_name: the IP-Adapter reference as uploaded to ComfyUI; ignored when IP-Adapter is disabled.
    size: (width, height) of a source frame, used to size the lineart map.
    """
    wf = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    s, ad = cfg["sampling"], cfg["animatediff"]
    wf["1"]["inputs"]["ckpt_name"] = cfg["models"]["checkpoint"]
    wf["2"]["inputs"]["directory"] = str(frames_dir)
    wf["3"]["inputs"]["megapixels"] = cfg["video"]["target_megapixels"]
    wf["7"]["inputs"]["resolution"] = lineart_resolution(
        wf["3"]["inputs"]["megapixels"], size, wf["3"]["inputs"]["resolution_steps"])
    positive, negative = cfg["style"]["positive"], cfg["style"]["negative"]
    wf["6"]["inputs"]["cnet"] = cfg["models"]["controlnet_lineart"]
    wf["8"]["inputs"]["strength"] = cfg["controlnet"]["lineart_strength"]
    wf["10"]["inputs"].update(
        seed=seed if seed is not None else s["seed"], steps=s["steps"], cfg=s["cfg"],
        sampler_name=s["sampler"], scheduler=s["scheduler"],
        denoise=denoise if denoise is not None else s["denoise"])
    wf["17"]["inputs"].update(context_length=ad["context_length"], context_overlap=ad["context_overlap"])
    wf["18"]["inputs"]["model_name"] = ad["motion_model"]
    if ad["ip_adapter"]["enabled"]:
        wf["14"]["inputs"]["image"] = reference_name
        wf["16"]["inputs"]["weight"] = ad["ip_adapter"]["weight"]
    else:  # AnimateDiff alone: drop the IP-Adapter nodes and feed the checkpoint straight in
        for node in IP_NODES:
            del wf[node]
        wf["18"]["inputs"]["model"] = ["1", 0]
    # style.loras: a LoraLoader chain after the checkpoint feeds the node that read the checkpoint's model
    # (the IP-Adapter loader, or AnimateDiff itself when IP-Adapter is off) and both prompt encoders
    positive, negative = apply_loras(wf, cfg["style"].get("loras") or [], positive, negative,
                                     model_node="15" if ad["ip_adapter"]["enabled"] else "18")
    wf["4"]["inputs"]["text"], wf["5"]["inputs"]["text"] = positive, negative
    return wf


def animatediff_settings(cfg: dict, frames_dir: Path, seed: int | None, denoise: float | None) -> dict:
    """Everything that changes the output: sampler values, style, models, AnimateDiff and IP-Adapter, source frames."""
    src = frames_dir / SETTINGS
    ad = cfg["animatediff"]
    reference = ROOT / ad["ip_adapter"]["reference"]
    return {
        "sampling": {**cfg["sampling"],
                     "seed": seed if seed is not None else cfg["sampling"]["seed"],
                     "denoise": denoise if denoise is not None else cfg["sampling"]["denoise"]},
        "style": style_record(cfg["style"]), "models": cfg["models"], "controlnet": cfg["controlnet"],
        "target_megapixels": cfg["video"]["target_megapixels"],
        "animatediff": {**ad, "ip_adapter": {**ad["ip_adapter"],
                                             "reference_bytes": reference.stat().st_size if reference.exists() else None}},
        "frames": json.loads(src.read_text(encoding="utf-8")) if src.exists() else None,
    }


def animatediff_shot(cfg: dict, project_dir: Path, shot: str,
                     seed: int | None = None, denoise: float | None = None) -> int:
    """Stylize project_dir/frames/<shot> into project_dir/animatediff/<shot>. Returns frames made.

    Raises SettingsChanged (nothing touched) if the output folder holds frames made with other settings.
    """
    frames_dir, out_dir = project_dir / "frames" / shot, project_dir / STAGE / shot
    frames = sorted(frames_dir.glob("frame_*.png"))
    if not frames:
        raise FileNotFoundError(f"no source frames in {frames_dir}; run `cli.py run` (or unpack the cloud bundle) first")
    prepare(out_dir, animatediff_settings(cfg, frames_dir, seed, denoise))
    if len(list(out_dir.glob("frame_*.png"))) == len(frames):
        return 0
    install_loras(cfg)   # copies from training/output/ if needed; in the cloud the notebook put them in models/loras
    ip = cfg["animatediff"]["ip_adapter"]
    reference = ROOT / ip["reference"]
    if ip["enabled"] and not reference.exists():
        raise FileNotFoundError(f"IP-Adapter reference image not found: {reference}")
    with Image.open(frames[0]) as im:
        size = im.size
    client = ComfyClient(cfg["comfyui"]["url"])
    with comfy_server(client, cfg), VramMonitor() as vram:
        wf = build_workflow(cfg, frames_dir.resolve(), client.upload_image(reference) if ip["enabled"] else None,
                            size, seed=seed, denoise=denoise)
        missing = client.missing_nodes(wf)
        if missing:
            raise RuntimeError(
                f"ComfyUI does not have these nodes: {', '.join(missing)}. Install the custom node packs listed in "
                "docs/cloud-kaggle.md, then RESTART ComfyUI (a server that was already running does not see new nodes), "
                "and check its log for 'IMPORT FAILED'.")
        entry = client.wait(client.queue(wf), timeout=cfg["animatediff"]["timeout_seconds"])
        tmp = out_dir / "_download"
        made = sorted(client.download_outputs(entry, tmp).get(OUTPUT_NODE, []))
    if len(made) != len(frames):
        shutil.rmtree(tmp, ignore_errors=True)
        raise RuntimeError(f"ComfyUI returned {len(made)} frames for {len(frames)} source frames")
    for result, frame in zip(made, frames):   # name each result after the source frame it came from
        result.replace(out_dir / frame.name)
    shutil.rmtree(tmp, ignore_errors=True)
    if vram.summary():
        print(vram.summary())
    return len(frames)
