"""Download the phase-1 models into the local ComfyUI models folder.

Run with the project venv:  .venv\\Scripts\\python.exe scripts\\download_models.py [--cloud]
--cloud also fetches the AnimateDiff motion module and the IP-Adapter files (for the cloud GPU).
"""
import shutil
import sys
from pathlib import Path

from huggingface_hub import hf_hub_download

ROOT = Path(__file__).resolve().parent.parent
COMFY = ROOT / "third_party" / "ComfyUI"

# (repo, filename, folder under third_party/ComfyUI)
FILES = [
    ("gsdf/Counterfeit-V3.0", "Counterfeit-V3.0_fix_fp16.safetensors", "models/checkpoints"),
    (
        "comfyanonymous/ControlNet-v1-1_fp16_safetensors",
        "control_v11p_sd15s2_lineart_anime_fp16.safetensors",
        "models/controlnet",
    ),
    # Lineart extractor for node "7". controlnet_aux would fetch it on first run anyway;
    # listing it here means a fresh or offline machine doesn't need internet at that point.
    (
        "lllyasviel/Annotators",
        "netG.pth",
        "custom_nodes/comfyui_controlnet_aux/ckpts/lllyasviel/Annotators",
    ),
]


# Extra models for the cloud stage (cli.py animatediff), fetched with --cloud:
# (repo, file in the repo, folder under third_party/ComfyUI, name to save it as)
MOTION_FILES = [("guoyww/animatediff", "v3_sd15_mm.ckpt", "models/animatediff_models", "v3_sd15_mm.ckpt")]
# only needed when animatediff.ip_adapter.enabled is true (about 2.6 GB)
IP_ADAPTER_FILES = [
    ("h94/IP-Adapter", "models/ip-adapter_sd15.safetensors", "models/ipadapter", "ip-adapter_sd15.safetensors"),
    # the unified IP-Adapter loader looks for the ViT-H image encoder under this exact name
    ("h94/IP-Adapter", "models/image_encoder/model.safetensors", "models/clip_vision",
     "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors"),
]


def cloud_files(ip_adapter_enabled: bool) -> list:
    return MOTION_FILES + (IP_ADAPTER_FILES if ip_adapter_enabled else [])


def fetch_cloud() -> None:
    sys.path.insert(0, str(ROOT))
    from pipeline.stylize import load_config
    enabled = load_config()["animatediff"]["ip_adapter"]["enabled"]
    print(f"IP-Adapter {'on' if enabled else 'off'} in the config: {'fetching' if enabled else 'skipping'} its models")
    for repo, filename, subdir, name in cloud_files(enabled):
        dest = COMFY / subdir
        dest.mkdir(parents=True, exist_ok=True)
        if (dest / name).exists():
            print(f"skip   {subdir}/{name} (already present)")
            continue
        print(f"fetch  {repo}/{filename}")
        got = hf_hub_download(repo_id=repo, filename=filename, local_dir=dest / "_hf")
        Path(got).replace(dest / name)
        shutil.rmtree(dest / "_hf", ignore_errors=True)


def main() -> None:
    cloud = "--cloud" in sys.argv
    for repo, filename, subdir in FILES:
        dest = COMFY / subdir
        dest.mkdir(parents=True, exist_ok=True)
        if (dest / filename).exists():
            print(f"skip   {subdir}/{filename} (already present)")
            continue
        print(f"fetch  {repo}/{filename}")
        hf_hub_download(repo_id=repo, filename=filename, local_dir=dest)
    if cloud:
        fetch_cloud()
    print("done")


if __name__ == "__main__":
    main()
