# Video → Anime Converter

Live-action video to consistent anime, in the style of Corridor Crew's *Anime Rock Paper Scissors*.
Full design and roadmap: [plan.md](plan.md).

## Setup (phase 1) (Windows, RTX 2060 6 GB)

Prerequisites (installed via winget): Python 3.11, Git, FFmpeg, and a current Visual C++ Redistributable
(PyTorch fails with `WinError 1114` on an old one).

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126
git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git third_party/ComfyUI
.venv\Scripts\python.exe -m pip install -r third_party/ComfyUI/requirements.txt
.venv\Scripts\python.exe -m pip install -r requirements.txt
git clone --depth 1 https://github.com/Fannovel16/comfyui_controlnet_aux.git third_party/ComfyUI/custom_nodes/comfyui_controlnet_aux
# only the controlnet_aux deps that anime lineart needs (the full list pulls mediapipe, which can pin numpy<2):
.venv\Scripts\python.exe -m pip install scikit-image python-dateutil omegaconf addict yacs matplotlib scikit-learn
.venv\Scripts\python.exe scripts\download_models.py
```

## Run the smoke test

```powershell
scripts\start_comfyui.ps1                                   # terminal 1: server on :8188
.venv\Scripts\python.exe scripts\test_single_frame.py       # terminal 2: restyles ComfyUI's example.png
.venv\Scripts\python.exe scripts\test_single_frame.py my_frame.png --denoise 0.45
```

Outputs land in `work/phase1/` (`anime_*.png` and the `lineart_*.png` control map).
Settings come from `config/project.yaml`, falling back to `config/project.example.yaml`.

## Convert a video (phase 2)

ComfyUI must be running. The input clip, start time and length come from the `input:` section of the config;
command-line options override them.

```powershell
scripts\start_comfyui.ps1                                   # terminal 1
.venv\Scripts\python.exe cli.py preview                     # terminal 2: config's slice (4 s if seconds is unset)
.venv\Scripts\python.exe cli.py preview other.mp4 --start 10 --seconds 3 --denoise 0.4
.venv\Scripts\python.exe cli.py run                         # config's slice; seconds: null = whole clip
.venv\Scripts\python.exe cli.py flicker <shot>              # frame-to-frame SSIM, stylized vs source
.venv\Scripts\python.exe -m pytest tests -q                 # no GPU or ComfyUI needed
```

Everything goes under `work/<project>/` (default project `default`): `frames/<shot>` (source frames at 12 fps),
`anime/<shot>` (stylized), `lineart/<shot>` (debug control maps) and `out/<shot>.mp4` (encoded, with the source audio).
Re-running a command resumes: frames already stylized are skipped. Delete `anime/<shot>` to redo a shot.
Expect about 15 s per frame on the RTX 2060 (12 frames per second of video). A sample clip (CC BY 3.0, ThierryTuyishimeTV,
[Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Beautiful_Traditional_South_African_Dance!.webm)) is in `samples/dance/`.
Results and the flicker baseline are in [docs/phase2-results.md](docs/phase2-results.md).

## Layout

| Path | Purpose |
|---|---|
| `cli.py` | `preview`, `run`, `flicker` commands |
| `pipeline/comfy_client.py` | ComfyUI HTTP API client (upload, queue, wait, download) |
| `pipeline/stylize.py` | config loading and `build_workflow()` (patches the graph by node id) |
| `pipeline/video.py` | ffmpeg frame extraction and encoding |
| `pipeline/batch.py` | resumable per-frame stylize loop |
| `pipeline/metrics.py` | flicker metric |
| `tests/` | phase 2 tests |
| `samples/` | test clips |
| `workflows/` | ComfyUI API-format workflow graphs |
| `scripts/` | model download, server launcher, phase 1 smoke test |
| `config/` | project settings |
| `third_party/ComfyUI` | local ComfyUI checkout (not ours) |
