# How to run the project

Your reference for running everything, from the IDE (VS Code) or from a command prompt. **This file is kept up to date as the project grows.** The change log at the end says what was added and when.

Contents: [Quick start](#1-quick-start) · [One-time setup](#2-one-time-setup) · [Run from the IDE](#3-run-from-the-ide-vs-code) · [Run from a command prompt](#4-run-from-a-command-prompt) · [Phase 1](#5-phase-1-single-frame-test) · [Phase 2](#6-phase-2-convert-a-video) · [Whole project](#7-the-whole-project-end-to-end) · [Settings](#8-settings-you-change) · [Outputs](#9-where-the-outputs-go) · [Shots and resuming](#10-shots-resuming-and-overwrite-protection) · [The ComfyUI server](#11-the-comfyui-server) · [Tests](#12-tests) · [Troubleshooting](#13-troubleshooting) · [Not built yet](#14-not-built-yet) · [Change log](#15-change-log)

## 1. Quick start

After the one-time setup:

1. Open the project folder in VS Code.
2. Open the **Run and Debug** panel (Ctrl+Shift+D).
3. Pick **Phase 2: convert video (config input)** and press **Ctrl+F5**.

That is the whole project: it reads the video and settings from `config/project.example.yaml`, starts ComfyUI itself, stylizes every frame, stops ComfyUI, and writes the video to `work/default/out/<shot>.mp4`. No terminal and no manual server step.

## 2. One-time setup

This is the only part that needs a terminal. It is already done on this machine; it is here for a new machine. The exact commands are in [README.md](../README.md#setup-phase-1).

| What | Why |
|---|---|
| Python 3.11, Git, FFmpeg, a current Visual C++ Redistributable | Installed with winget. The system `python` (3.15) is not used. |
| `.venv` with PyTorch (CUDA) and `requirements.txt` | The project's Python environment. |
| `third_party/ComfyUI` plus the `comfyui_controlnet_aux` node | The image engine. It is git-ignored and re-cloned. |
| Models (about 3 GB) | Run **Setup: download models** from the IDE, or `scripts\download_models.py`. |

VS Code extensions to have: **Python** (with Debugpy) and **PowerShell**. `.vscode/settings.json` already points VS Code at `.venv`, so the Run button uses the right Python.

## 3. Run from the IDE (VS Code)

Open **Run and Debug** (Ctrl+Shift+D), choose a configuration from the drop-down, then **F5** (with debugger) or **Ctrl+F5** (without). These live in `.vscode/launch.json`.

| Configuration | What it does | Typical time |
|---|---|---|
| **Phase 2: convert video (config input)** | Converts the config's video slice to anime. This is the main one. | about 15 s per frame |
| **Phase 2: short preview (config input, 4 s default)** | Same, but if `input.seconds` is empty it uses 4 seconds. | about 15 s per frame |
| **Phase 3 cloud: pack the Kaggle bundle (config shot)** | Zips the code, config, IP-Adapter reference and the shot's frames into `work/cloud/bundle_<shot>.zip` to upload to Kaggle. See `docs/cloud-kaggle.md`. | a few seconds |
| **Phase 3 cloud: deflicker / flicker check / encode ...** | After unzipping the notebook's result at the project root: deflicker the AnimateDiff frames, measure `animatediff` or `deflicker_animatediff`, or encode them to mp4. | seconds |
| **Phase 3: deflicker (config shot)** | Blends each stylized frame with the motion-warped previous one (CPU only), writes `deflicker/<shot>` and `out/<shot>_deflicker.mp4`. The shot must already be stylized. | about 10 s for 48 frames |
| **Phase 3: flicker check of the deflickered shot** | Same measurement as the Phase 2 check, on the deflickered frames. | a few seconds |
| **Phase 2: flicker check (config shot)** | Prints how steady the frames are (whole frame, and static regions), for the shot named in the config. | a few seconds |
| **Phase 1: single-frame smoke test** | Restyles ComfyUI's example image once. | about 40 s |
| **Setup: download models** | Fetches the checkpoint, ControlNet and lineart weights. Skips what exists. | minutes, first time only |
| **Tests: pytest** | Runs the automated tests. No GPU needed. | about 5 s |
| **ComfyUI server only** | Starts the server and keeps it running, for the ComfyUI web page (http://127.0.0.1:8188). Not needed for normal runs. | stays running |
| **PowerShell: Launch Current File** | Runs whichever `.ps1` file is open. | |

You can also open `cli.py` and press the **Run** button (the triangle at the top right). With no command, it behaves like **Phase 2: convert video**.

**To change what a run does, edit the config, not the command.** Video, start, length, shot name, denoise and the rest are in `config/project.example.yaml` (section 8). To run phase 1 on your own image, add its path to `"args"` in the "Phase 1" configuration, for example `"args": ["D:/photos/me.png", "--denoise", "0.45"]`.

## 4. Run from a command prompt

Open a terminal in the project folder (PowerShell). Always use the project's Python:

```powershell
.venv\Scripts\python.exe cli.py                 # same as `run`; no command needed
.venv\Scripts\python.exe cli.py run             # convert the config's slice
.venv\Scripts\python.exe cli.py preview         # short slice (4 s if input.seconds is empty)
.venv\Scripts\python.exe cli.py flicker         # steadiness of the config's shot
.venv\Scripts\python.exe cli.py deflicker       # phase 3: flow-warp deflicker of the config's shot
.venv\Scripts\python.exe cli.py flicker --stage deflicker   # measure the deflickered frames
.venv\Scripts\python.exe scripts\test_single_frame.py     # phase 1 smoke test
.venv\Scripts\python.exe scripts\download_models.py       # fetch models
.venv\Scripts\python.exe -m pytest tests -q               # tests
scripts\start_comfyui.ps1                                 # server only (blocks until Ctrl+C)
```

Anything in the config can be overridden for one run, so you don't have to edit the file:

```powershell
.venv\Scripts\python.exe cli.py run other.mp4 --start 10 --seconds 3 --shot test2 --denoise 0.4 --seed 7
.venv\Scripts\python.exe cli.py flicker test2 --frames 12   # only the first 12 frames, to compare runs of different lengths
.venv\Scripts\python.exe scripts\test_single_frame.py my_frame.png --denoise 0.45 --seed 1
```

`--project <name>` changes the folder under `work/` (default `default`).

## 5. Phase 1: single-frame test

**What it is:** one image through the img2img + anime-lineart ControlNet graph in ComfyUI. It proves the models and graph work. It is not for video.

| | |
|---|---|
| IDE | Run **Phase 1: single-frame smoke test** |
| Terminal | `.venv\Scripts\python.exe scripts\test_single_frame.py [image] [--denoise 0.45] [--seed 1]` |
| Input | `third_party/ComfyUI/input/example.png`, or the image you pass |
| Output | `work/phase1/` : the anime image and the lineart map |
| Time | about 40 s on the RTX 2060 (6 GB) |

The server starts and stops by itself (section 11).

## 6. Phase 2: convert a video

**What it is:** the frame pipeline. ffmpeg splits the video into frames at 12 fps, every frame goes through the phase 1 graph, and ffmpeg joins the results back into a video with the original audio.

| | |
|---|---|
| IDE | Run **Phase 2: convert video (config input)** |
| Terminal | `.venv\Scripts\python.exe cli.py run` |
| Input | `input.video`, `input.start`, `input.seconds` from the config (or the command line) |
| Output | `work/default/out/<shot>.mp4`, plus frames and lineart maps (section 9) |
| Time | about 15 s per frame, 12 frames per video second. The 4-second sample is about 12 minutes. |

Typical loop: edit the config (a new `shot:` name, a different `denoise:`), run, watch `out/<shot>.mp4`, run **flicker check**.

## 7. The whole project, end to end

There is one pipeline, and phase 2 contains phase 1:

```
config  ->  ffmpeg: video to frames  ->  for each frame: phase 1 ComfyUI graph  ->  ffmpeg: frames to video (+ audio)
```

So "run the whole project" is one run of **Phase 2: convert video (config input)** (or `cli.py`). Phase 1's single-image test is a smaller check of the same graph.

A full pass from nothing, all from the IDE:

1. **Setup: download models** (first time only).
2. **Tests: pytest** (optional, quick check that the code is intact).
3. **Phase 1: single-frame smoke test** (optional, proves the graph and GPU work).
4. **Phase 2: convert video (config input)**.
5. **Phase 2: flicker check (config shot)**.

Phases 3 to 6 (consistency, training, compositing, product) are not built yet (section 14).

## 8. Settings you change

All in `config/project.example.yaml`. If you create `config/project.yaml` (copy the example), that file is used instead and the example stays as a template.

| Key | Meaning | Default |
|---|---|---|
| `comfyui.url` | Where ComfyUI listens. The port is used when the server is auto-started. | `http://127.0.0.1:8188` |
| `comfyui.autostart` | Start ComfyUI when it isn't running. | `true` |
| `comfyui.autostop` | Stop it afterwards, only if the project started it. `false` leaves it running. | `true` |
| `input.video` | Video to convert, relative to the project folder. | `samples/dance/dance.webm` |
| `input.start` | Seconds into the video to start at. | `5` |
| `input.seconds` | How many seconds to convert. Empty or `null` means to the end. | `4` |
| `input.shot` | Name of this run. It names the folders and the output video. | `dance_run1` |
| `models.checkpoint`, `models.controlnet_lineart` | Which model files to use. | Counterfeit-V3.0, lineart anime |
| `style.positive`, `style.negative` | The prompts. | anime, cel shading, clean lineart ... |
| `animatediff.*` | The cloud stage: motion module, window size, and `ip_adapter.enabled` / `weight` / `reference`. Used by `cli.py animatediff` (cloud GPU only; see `docs/cloud-kaggle.md`). | `v3_sd15_mm.ckpt`, 16, 4, on, 0.5 |
| `temporal.strength`, `temporal.lowpass_sigma`, `temporal.error_threshold` | Phase 3 deflicker: weight of the warped previous frame (0.9), the blur radius in pixels below which colors are blended so edges stay crisp (2; 0 blends everything and softens), and the source color error above which the warp is ignored (25). Changing them under an existing shot stops the run; use a new shot name. | `0.9`, `2`, `25` |
| `sampling.seed` | Same seed on every frame of a shot, to limit flicker. | `12345` |
| `sampling.denoise` | How far the result moves from the source: lower stays closer. | `0.4` |
| `sampling.steps`, `cfg`, `sampler`, `scheduler` | Sampler settings. | 24, 7.0, euler_ancestral, normal |
| `controlnet.lineart_strength` | How strictly lineart guides the result. | `0.8` |
| `video.work_fps` | Frame rate used for stylizing and for the output. | `12` |
| `video.target_megapixels` | Working size per frame. About 0.4 fits a 6 GB GPU. | `0.4` |

## 9. Where the outputs go

Everything is under `work/<project>/` (default `work/default/`). `work/` is generated and git-ignored.

| Folder | Contents |
|---|---|
| `frames/<shot>/` | Source frames, `frame_00001.png` ... , and `settings.json` |
| `anime/<shot>/` | Stylized frames and `settings.json` |
| `lineart/<shot>/` | The lineart control maps (for checking the guidance) |
| `out/<shot>.mp4` | The finished video, 12 fps, with the source audio |
| `work/phase1/` | Phase 1 test output |
| `work/comfyui.log` | Log of a server the project started |

## 10. Shots, resuming and overwrite protection

A **shot** is one named run. Its frames and video are kept under that name.

- **Same shot, same settings:** the run resumes. Frames that already exist are skipped, so a crash or stop costs at most one frame. If everything is done, nothing runs and the server isn't even started.
- **Same shot, different settings** (a different video, start, seconds, seed, denoise, prompts, models and so on): the run **stops with a message** and changes nothing. A shot can't be overwritten by accident, and there is no force option.
- **To try new settings:** give the run a new shot name (`input.shot` in the config, or `--shot`). Every shot keeps its own frames and video, so you can compare them.
- **To keep using a shot,** change the settings back to what it was made with.
- Shots made before settings were tracked (`dance_preview`, `dance_d040`, `verify_d040`) have no record, so they are locked the same way. `dance_d040` is the phase 2 baseline video.

## 11. The ComfyUI server

You don't have to start it. Every run that needs it calls the same check:

- A server already answers: it is used and left alone, including one you started yourself.
- Nothing answers and `comfyui.autostart` is `true`: the project starts `scripts/start_comfyui.ps1` in the background, waits for it (about 20 seconds), runs, and then stops it (`comfyui.autostop`). Its log is `work/comfyui.log`.

Start it by hand only to use the ComfyUI web page: run **ComfyUI server only** (IDE) or `scripts\start_comfyui.ps1`, then open http://127.0.0.1:8188. Keep it to one server at a time on a 6 GB GPU.

## 12. Tests

**Tests: pytest** (IDE) or `.venv\Scripts\python.exe -m pytest tests -q`. They use real ffmpeg on a generated clip and a fake ComfyUI, so they need no GPU. They cover frame extraction, resuming, audio, the settings protection, the CLI, the server start and stop logic, and the flicker metric. VS Code's Testing panel also lists them.

They do not test the ComfyUI graph itself. Phase 1 and a real preview do that.

**Reading the output of a run:** after stylizing it prints `GPU memory: peak ... MiB of 6144 MiB used`. The pipeline peaks at about 5.4 GB, so close other programs that use the GPU. Peak memory is also why phase 3 additions may not fit.

## 13. Troubleshooting

| Problem | Fix |
|---|---|
| `Missing command` when running `cli.py` | Fixed: no command now means `run`. If you still see it, you have an old copy of `cli.py`. |
| `Stopped: ... already holds frames made with different settings` | Working as intended. Set a new `input.shot` (or `--shot`), or change the settings back. |
| `ComfyUI is not reachable` | `comfyui.autostart` is `false`. Set it to `true`, or start the server yourself. |
| `ComfyUI did not answer within 240s` | Open `work/comfyui.log`. Usually another server is using the GPU or port. |
| `OSError: WinError 1114` loading `c10.dll` | The Visual C++ Redistributable is too old. Upgrade `Microsoft.VCRedist.2015+.x64`. |
| `video not found` | Check `input.video` in the config, or pass a path. |
| VS Code uses the wrong Python | Ctrl+Shift+P, "Python: Select Interpreter", choose `.venv\Scripts\python.exe`. |
| The ComfyUI web page shows a "missing model" warning | Ignore it. The project runs its own workflow file, not the page's template. |
| Out of GPU memory | Close other ComfyUI servers. Lower `video.target_megapixels`. |
| A run takes very long | Expected: about 15 s per frame. Use a short `input.seconds` while testing. |

## 14. Not built yet

From `plan.md`: the rest of phase 3 (the AnimateDiff + IP-Adapter cloud stage runs on Kaggle (confirmed by the project owner); the flow-warp deflicker is built), phase 4 (LoRA training), phase 5 (matting, compositing, face pass), phase 6 (per-shot config list, web UI, cloud worker). Phase 2 is the baseline they are compared against, on the `dance_run1` shot: static-region change 5.85 levels (lower is steadier), whole-frame ratio 0.951 (`docs/phase2-results.md`).

## 15. Change log

Add a line here whenever something is added or changed that affects how the project is run.

| Date | Change |
|---|---|
| 2026-10-30 | Phase 1: single-frame test through ComfyUI. Phase 2: frame pipeline (`cli.py`: ingest, stylize, encode), flicker metric, tests, sample clip. |
| 2026-10-30 | Video, start and seconds can be set in the config (`input:`); command-line options override them. |
| 2026-10-31 | Shot settings are recorded per shot. A changed setting under the same shot name stops the run and overwrites nothing. |
| 2026-10-31 | Shot name can be set in the config (`input.shot`). |
| 2026-10-31 | `cli.py` with no command runs `run`, so the IDE's Run button works. |
| 2026-10-31 | The server starts and stops by itself (`comfyui.autostart`, `autostop`), and is not started when there is nothing to stylize. `flicker` defaults to the config's shot. VS Code run configurations and the interpreter setting added. This document added. |
| 2026-10-31 | Flicker check now also measures static regions (where the source doesn't move) and takes `--frames N`. Every run prints its peak GPU memory (5399 of 6144 MiB measured). New baseline recorded. |
| 2026-10-31 | Phase 3 started: `cli.py deflicker` (flow-warp deflicker, CPU only) and `flicker --stage deflicker`; `temporal:` config section; two VS Code run configs. |
| 2026-10-31 | Deflicker blends only low-frequency colors (`temporal.lowpass_sigma`), default strength 0.8, so moving edges stay crisp. Shots deflickered earlier with the old settings need a new shot name or a deleted `deflicker/<shot>` folder. |
| 2026-10-31 | Deflicker defaults tuned to `strength: 0.9`, `lowpass_sigma: 2` (static change 3.88 vs 5.85 baseline, 97% of the baseline sharpness). |
| 2026-10-31 | Cloud stage added: `cli.py animatediff` (one AnimateDiff + lineart ControlNet + IP-Adapter pass, ~16 GB GPU), `scripts/make_cloud_bundle.py`, `notebooks/kaggle_animatediff.ipynb`, `download_models.py --cloud`, `animatediff:` config section, `deflicker --source`, `encode --stage`. Guide: `docs/cloud-kaggle.md`. Ran end to end locally on a small test, then confirmed working on Kaggle. |
| 2026-10-31 | Cloud stage fixes found by running it: ComfyUI-Advanced-ControlNet nodes (stock ControlNet fails with sliding windows); `vram.py` no longer uses a Windows-only flag; `server.py` starts ComfyUI itself on Linux. |
