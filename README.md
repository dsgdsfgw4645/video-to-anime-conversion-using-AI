# Video → Anime Converter

Live-action video to consistent anime, in the style of Corridor Crew's *Anime Rock Paper Scissors*.
Full design and roadmap: [plan.md](plan.md).

## Setup (Windows, RTX 2060 6 GB)

This repository holds the project's code and docs. It does **not** hold `.venv/` (the Python environment, about 6 GB), `third_party/` (ComfyUI and the models, about 3 GB) or `work/` (everything a run generates). You create `.venv` and `third_party` once with the commands below; `work/` appears when you run the project. On a new computer: `git clone https://github.com/dsgdsfgw4645/video-to-anime-conversion-using-AI.git`, open the folder, then follow these steps.

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

Then run the tests (`.venv\Scripts\python.exe -m pytest tests -q`) and the smoke test below to check everything works. The full run reference, for the IDE and the command prompt, is in [docs/how-to-run.md](docs/how-to-run.md). In VS Code, pick a run configuration in Run and Debug (Ctrl+Shift+D); ComfyUI starts by itself when needed.

## Run the smoke test

```powershell
scripts\start_comfyui.ps1                                   # optional: the scripts below start the server themselves if it is not running
.venv\Scripts\python.exe scripts\test_single_frame.py       # terminal 2: restyles ComfyUI's example.png
.venv\Scripts\python.exe scripts\test_single_frame.py my_frame.png --denoise 0.45
```

Outputs land in `work/phase1/` (`anime_*.png` and the `lineart_*.png` control map).
Settings come from `config/project.yaml`, falling back to `config/project.example.yaml`.

## Convert a video (phase 2)

ComfyUI starts by itself if it isn't running (set `comfyui.autostart: false` to disable). The input clip, start time, length and shot name come from the `input:` section of the config;
command-line options override them.

```powershell
scripts\start_comfyui.ps1                                   # optional: cli.py starts the server itself if it is not running
.venv\Scripts\python.exe cli.py preview                     # terminal 2: config's slice (4 s if seconds is unset)
.venv\Scripts\python.exe cli.py preview other.mp4 --start 10 --seconds 3 --denoise 0.4
.venv\Scripts\python.exe cli.py                             # no command = run (works from an IDE's run button)
.venv\Scripts\python.exe cli.py run                         # config's slice; seconds: null = whole clip
.venv\Scripts\python.exe cli.py flicker <shot>              # flicker: whole-frame SSIM, change in static regions, and color steadiness (lower = steadier); --frames N
.venv\Scripts\python.exe -m pytest tests -q                 # no GPU or ComfyUI needed
```

Everything goes under `work/<project>/` (default project `default`): `frames/<shot>` (source frames at 12 fps),
`anime/<shot>` (stylized), `lineart/<shot>` (debug control maps) and `out/<shot>.mp4` (encoded, with the source audio).
Re-running a command resumes: frames already stylized are skipped, but only if they were made with the same settings (video, `--start`, `--seconds`, `--seed`, `--denoise`, prompts, models). If the settings changed, the run stops with a message and changes nothing, so a shot can't be overwritten by accident. Set a new shot name (`input.shot` in the config, or `--shot`) to try new settings.
Expect 15 to 18 s per frame on the RTX 2060 (12 frames per second of video). A sample clip (CC BY 3.0, ThierryTuyishimeTV,
[Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Beautiful_Traditional_South_African_Dance!.webm)) is in `samples/dance/`.
A second, harder clip (handheld camera, several people; CC BY-SA 4.0, 23Faerie, [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Cape_Town_Palestine_Soccer_Match_Dance.webm)) is in `samples/capetown/`; the test uses 4 s from second 8: `cli.py run samples/capetown/capetown_dance.webm --start 8 --seconds 4 --shot capetown_run1`.
Results and the flicker baseline are in [docs/phase2-results.md](docs/phase2-results.md).

## Steadier video (phase 3)

```powershell
.venv\Scripts\python.exe cli.py deflicker                  # local, CPU, seconds: blend frames along the source's motion
.venv\Scripts\python.exe cli.py flicker --stage deflicker  # measure it
.venv\Scripts\python.exe scripts\make_cloud_bundle.py       # pack the zip for the Kaggle AnimateDiff notebook
```

The AnimateDiff stage needs about 16 GB of GPU memory, so it runs in a Kaggle notebook (`notebooks/kaggle_animatediff.ipynb`), not on this machine. Upload the zip as a Kaggle dataset, run the notebook, unzip the result into the project folder and measure it with `cli.py flicker --stage animatediff`. Step by step: [docs/how-to-run.md](docs/how-to-run.md#7-phase-3-steadier-video-deflicker-and-the-cloud-stage) and [docs/cloud-kaggle.md](docs/cloud-kaggle.md). Design, tuning and results: [docs/phase3-guide.md](docs/phase3-guide.md).

## Layout

| Path | Purpose |
|---|---|
| `cli.py` | `preview`, `run`, `flicker`, `deflicker`, `animatediff`, `encode` commands; no command means `run` |
| `pipeline/comfy_client.py` | ComfyUI HTTP API client (upload, queue, wait, download) |
| `pipeline/stylize.py` | config loading and `build_workflow()` (patches the graph by node id) |
| `pipeline/video.py` | ffmpeg frame extraction and encoding |
| `pipeline/batch.py` | resumable per-frame stylize loop |
| `pipeline/shot_state.py` | records each shot's settings; stops a run that would overwrite a shot |
| `pipeline/server.py` | starts ComfyUI when it isn't running, stops it afterwards |
| `pipeline/metrics.py` | flicker metrics (whole frame, static regions, color) |
| `pipeline/temporal.py` | phase 3 deflicker (optical-flow blend, CPU) |
| `pipeline/animatediff.py` | phase 3 cloud stage: one AnimateDiff pass over a whole shot (needs about 16 GB GPU) |
| `pipeline/vram.py` | peak GPU memory of a run |
| `tests/` | automated tests (no GPU needed) |
| `docs/` | `how-to-run.md` (run reference), `phase1-guide.md`, `phase2-results.md`, `phase3-guide.md`, `cloud-kaggle.md` |
| `.vscode/` | interpreter setting and run configurations |
| `samples/` | test clips |
| `workflows/` | ComfyUI API-format workflow graphs |
| `scripts/` | model download, server launcher, phase 1 smoke test, `make_cloud_bundle.py` (zip for Kaggle) |
| `notebooks/` | the Kaggle notebook for the cloud stage |
| `config/` | project settings |
| `third_party/ComfyUI` | local ComfyUI checkout (not ours); git-ignored, created by the setup commands |
| `.venv/`, `work/` | git-ignored: the Python environment (setup commands) and everything a run generates |
