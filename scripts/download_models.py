"""Download the phase-1 models into the local ComfyUI models folder.

Run with the project venv:  .venv\\Scripts\\python.exe scripts\\download_models.py
"""
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


def main() -> None:
    for repo, filename, subdir in FILES:
        dest = COMFY / subdir
        dest.mkdir(parents=True, exist_ok=True)
        if (dest / filename).exists():
            print(f"skip   {subdir}/{filename} (already present)")
            continue
        print(f"fetch  {repo}/{filename}")
        hf_hub_download(repo_id=repo, filename=filename, local_dir=dest)
    print("done")


if __name__ == "__main__":
    main()
