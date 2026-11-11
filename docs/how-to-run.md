# How to run the project

Your reference for running everything, from the IDE (VS Code) or from a command prompt. **This file is kept up to date as the project grows.** The change log at the end says what was added and when.

Contents: [Quick start](#1-quick-start) · [One-time setup and what is in git](#2-one-time-setup-and-what-is-in-git) · [Run from the IDE](#3-run-from-the-ide-vs-code) · [Run from a command prompt](#4-run-from-a-command-prompt) · [Phase 1](#5-phase-1-single-frame-test) · [Phase 2](#6-phase-2-convert-a-video) · [Phase 3](#7-phase-3-steadier-video-deflicker-and-the-cloud-stage) · [Whole project](#8-the-whole-project-end-to-end) · [Settings](#9-settings-you-change) · [Outputs](#10-where-the-outputs-go) · [Shots and resuming](#11-shots-resuming-and-overwrite-protection) · [The ComfyUI server](#12-the-comfyui-server) · [Tests](#13-tests) · [Troubleshooting](#14-troubleshooting) · [Not built yet](#15-not-built-yet) · [Change log](#16-change-log)

## 1. Quick start

After the one-time setup:

1. Open the project folder in VS Code.
2. Open the **Run and Debug** panel (Ctrl+Shift+D).
3. Pick **Phase 2: convert video (config input)** and press **Ctrl+F5**.

That is the whole project: it reads the video and settings from `config/project.example.yaml`, starts ComfyUI itself, stylizes every frame, stops ComfyUI, and writes the video to `work/default/out/<shot>.mp4`. No terminal and no manual server step.

## 2. One-time setup and what is in git

**What is in git (pushed to GitHub):** the whole project: `cli.py`, `pipeline/`, `scripts/`, `tests/`, `workflows/`, `config/project.example.yaml`, `notebooks/`, `docs/`, `README.md`, `CLAUDE.md`, `plan.md`, `requirements.txt`, `.vscode/` and the small sample files in `samples/`.

**What is not in git (listed in `.gitignore`), and where it comes from:**

| Folder | Size | Where it comes from |
|---|---|---|
| `.venv/` | about 6 GB | The project's Python environment (PyTorch and the rest). You create it once with the setup commands below. It holds absolute paths to this machine, so it can't be copied to another computer. Never commit it. |
| `third_party/` | about 3 GB | ComfyUI, its `comfyui_controlnet_aux` node, and the downloaded models. The setup commands clone ComfyUI and `scripts\download_models.py` fetches the models. It is not created by running the project. |
| `work/` | grows with use | **Created automatically by running the project**: frames, stylized frames, mp4s, cloud bundle zips (section 10). Safe to delete; it is rebuilt from your input video. |
| `result_*/` | about 40 MB each | The folders you get when you unzip the Kaggle results. Copy their contents into `work/default/` (section 7). |
| `__pycache__/`, `.pytest_cache/` | small | Python and test caches, created automatically. |

`config/project.yaml` (your own settings) is in the project and is not ignored. The code reads it first and falls back to `config/project.example.yaml`. It holds the selfie setting "D" (see section 9); the example keeps the original defaults.

**Setting up on a new computer (or after deleting `.venv` or `third_party`):**

1. Install with winget: Python 3.11, Git, FFmpeg, a current Visual C++ Redistributable. The system `python` (3.15) is not used.
2. `git clone https://github.com/dsgdsfgw4645/video-to-anime-conversion-using-AI.git`, then open the folder.
3. Run the commands in [README.md](../README.md#setup-windows-rtx-2060-6-gb) in order. They create `.venv`, install PyTorch (CUDA) and the requirements, clone ComfyUI and the lineart node into `third_party/`, and run `scripts\download_models.py` (about 3 GB; the IDE has **Setup: download models** too).
4. Check it: **Tests: pytest** (no GPU needed), then **Phase 1: single-frame smoke test** (proves the models and GPU work).
5. Optional: copy `config/project.example.yaml` to `config/project.yaml` for your own settings.

VS Code extensions to have: **Python** (with Debugpy) and **PowerShell**. `.vscode/settings.json` already points VS Code at `.venv`, so the Run button uses the right Python.

The AnimateDiff stage does **not** run on this machine (it needs about 16 GB of GPU memory). It runs in a Kaggle notebook, which installs its own copy of ComfyUI and the extra nodes (AnimateDiff, Advanced-ControlNet and others). Nothing for it needs installing locally.

## 3. Run from the IDE (VS Code)

Open **Run and Debug** (Ctrl+Shift+D), choose a configuration from the drop-down, then **F5** (with debugger) or **Ctrl+F5** (without). These live in `.vscode/launch.json`.

| Configuration | What it does | Typical time |
|---|---|---|
| **Phase 2: convert video (config input)** | Converts the config's video slice to anime. This is the main one. | 15 to 18 s per frame |
| **Phase 2: short preview (config input, 4 s default)** | Same, but if `input.seconds` is empty it uses 4 seconds. | 15 to 18 s per frame |
| **Phase 3: deflicker (config shot)** | Blends each stylized frame with the motion-warped previous one (CPU only), writes `deflicker/<shot>` and `out/<shot>_deflicker.mp4`. The shot must already be stylized (phase 2). | about 11 s for 48 frames |
| **Phase 3: flicker check of the deflickered shot** | Same measurement as the phase 2 check, on the deflickered frames. | a few seconds |
| **Phase 3 cloud: pack the Kaggle bundle (config shot)** | Zips the code, config and the shot's frames into `work/cloud/bundle_<shot>.zip` to upload to Kaggle (extracts the frames itself if needed). | a few seconds |
| **Phase 3 cloud: deflicker the AnimateDiff result (config shot)** | After unpacking the Kaggle result into `work/default/`: deflickers `animatediff/<shot>`. | seconds |
| **Phase 3 cloud: flicker check of the AnimateDiff result** | Measures `animatediff/<shot>`. | a few seconds |
| **Phase 3 cloud: flicker check of the deflickered AnimateDiff result** | Measures `deflicker_animatediff/<shot>`. | a few seconds |
| **Phase 3 cloud: encode the AnimateDiff result to mp4** | Writes `out/<shot>_animatediff.mp4`. | seconds |
| **Phase 2: flicker check (config shot)** | Prints how steady the frames are (whole frame, static regions, and color), for the shot named in the config. | a few seconds |
| **Phase 1: single-frame smoke test** | Restyles ComfyUI's example image once. | about 40 s |
| **Setup: download models** | Fetches the checkpoint, ControlNet and lineart weights. Skips what exists. | minutes, first time only |
| **Tests: pytest** | Runs the automated tests. No GPU needed. | about 5 s |
| **ComfyUI server only** | Starts the server and keeps it running, for the ComfyUI web page (http://127.0.0.1:8188). Not needed for normal runs. | stays running |
| **PowerShell: Launch Current File** | Runs whichever `.ps1` file is open. | |

You can also open `cli.py` and press the **Run** button (the triangle at the top right). With no command, it behaves like **Phase 2: convert video**.

**To change what a run does, edit the config, not the command.** Video, start, length, shot name, denoise and the rest are in `config/project.example.yaml` (section 9). To run phase 1 on your own image, add its path to `"args"` in the "Phase 1" configuration, for example `"args": ["D:/photos/me.png", "--denoise", "0.45"]`.

## 4. Run from a command prompt

Open a terminal in the project folder (PowerShell). Always use the project's Python:

```powershell
.venv\Scripts\python.exe cli.py                 # same as `run`; no command needed
.venv\Scripts\python.exe cli.py run             # convert the config's slice
.venv\Scripts\python.exe cli.py preview         # short slice (4 s if input.seconds is empty)
.venv\Scripts\python.exe cli.py flicker         # steadiness of the config's shot
.venv\Scripts\python.exe cli.py deflicker       # phase 3: flow-warp deflicker of the config's shot
.venv\Scripts\python.exe cli.py flicker --stage deflicker   # measure the deflickered frames
# phase 3, cloud stage (the Kaggle notebook runs `cli.py animatediff`; see section 7):
.venv\Scripts\python.exe scripts\make_cloud_bundle.py      # pack the zip to upload to Kaggle
.venv\Scripts\python.exe cli.py flicker --stage animatediff            # after unpacking the Kaggle result
.venv\Scripts\python.exe cli.py deflicker --source animatediff         # deflicker the AnimateDiff frames
.venv\Scripts\python.exe cli.py flicker --stage deflicker_animatediff
.venv\Scripts\python.exe cli.py encode --stage animatediff             # frames of any stage -> out/<shot>_<stage>.mp4
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
.venv\Scripts\python.exe scripts\make_cloud_bundle.py dance_run1_ipa --set animatediff.ip_adapter.enabled=true   # a variant bundle, config untouched
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

The server starts and stops by itself (section 12).

## 6. Phase 2: convert a video

**What it is:** the frame pipeline. ffmpeg splits the video into frames at 12 fps, every frame goes through the phase 1 graph, and ffmpeg joins the results back into a video with the original audio.

| | |
|---|---|
| IDE | Run **Phase 2: convert video (config input)** |
| Terminal | `.venv\Scripts\python.exe cli.py run` |
| Input | `input.video`, `input.start`, `input.seconds` from the config (or the command line) |
| Output | `work/default/out/<shot>.mp4`, plus frames and lineart maps (section 10) |
| Time | 15 to 18 s per frame, 12 frames per video second. A 4-second shot (48 frames) takes about 12 to 14 minutes. |

Typical loop: edit the config (a new `shot:` name, a different `denoise:`), run, watch `out/<shot>.mp4`, run **flicker check**.

## 7. Phase 3: steadier video (deflicker and the cloud stage)

The design, tuning and all results are in [phase3-guide.md](phase3-guide.md); this section is how to run it.

Phase 2 stylizes every frame on its own, so the result flickers and the colors of clothes wander. Phase 3 has two tools. Use one or both.

**A. Local deflicker (CPU, seconds, nothing to install).** Run it after phase 2: **Phase 3: deflicker (config shot)** or `.venv\Scripts\python.exe cli.py deflicker`. It blends each frame with the previous one warped along the source video's motion. It writes `work/default/deflicker/<shot>/` and `out/<shot>_deflicker.mp4`.

**B. AnimateDiff in the cloud (Kaggle free GPU).** The whole shot goes through one AnimateDiff pass, which keeps neighbouring frames and colors consistent. It needs about 16 GB of GPU memory, so it can't run on the RTX 2060. The full guide is [cloud-kaggle.md](cloud-kaggle.md); in short:

1. **Pack** (locally): set `input.video`, `start`, `seconds`, `shot` in the config, then run **Phase 3 cloud: pack the Kaggle bundle**. It extracts the frames itself (no stylizing) and writes `work/cloud/bundle_<shot>.zip`.
2. **Upload** that zip to kaggle.com/datasets as a new dataset. Kaggle unzips it; that is fine. Only one project may be in the dataset.
3. **Run the notebook** `notebooks/kaggle_animatediff.ipynb`: kaggle.com/code, File > Import Notebook, Add Input (your dataset), Accelerator **GPU T4**, Internet **On**, Run All. It installs everything, runs AnimateDiff, measures flicker and runs the deflicker on top.
4. **Download** `result_<shot>.zip` from the notebook's Output tab and unzip it into the project folder. If you get a `result_<shot>` subfolder, copy its `work\default\...` folders into the project's `work\default\`. Do not overwrite anything else.
5. **Measure and look:** `cli.py flicker <shot> --stage animatediff` and `--stage deflicker_animatediff`, and play the mp4s in `work/default/out/`.

**Which stage is which** (`cli.py flicker <shot> --stage <name>`; `<shot>` is the shot name, and the three columns are measured the same way for every stage):

| Stage folder | What it is |
|---|---|
| `anime` | phase 2, per-frame (the baseline) |
| `deflicker` | phase 2 + local deflicker |
| `animatediff` | cloud AnimateDiff |
| `deflicker_animatediff` | cloud AnimateDiff + deflicker |

**How well each worked on the sample clip** (`dance_run1`; lower is steadier in every column; details in `docs/phase3-guide.md`):

| Stage | Static change | Color flicker | Color drift |
|---|---|---|---|
| per-frame baseline | 5.85 | 1.86 | 2.60 |
| + local deflicker | 3.88 | 0.82 | 1.95 |
| AnimateDiff alone | 4.34 | 0.69 | 1.47 |
| AnimateDiff + deflicker (best) | 3.97 | 0.53 | 1.40 |

The local deflicker alone removes most of the grayscale flicker; AnimateDiff is what keeps the colors steady. **IP-Adapter** (a color reference image) is optional and **off by default**: on the sample clip it did not help. The metrics don't see everything, so watch the video: AnimateDiff's limbs and crowd are blockier than the per-frame version. These numbers are from the first clip; on a second, harder clip (handheld camera) the same ordering held with a bigger gap, and AnimateDiff + deflicker cut color flicker by 62% (`phase3-guide.md` section 5.6).

**A different video:** set a new `input.shot` (and `video`, `start`, `seconds`) in the config, pack, upload, run, unpack as above. Or skip the config edit and pack straight from the command line: `.venv\Scripts\python.exe scripts\make_cloud_bundle.py my_shot --set input.video=samples/capetown/capetown_dance.webm --set input.start=8 --set input.seconds=4` (it extracts the frames itself, so you do not have to run phase 2 first; phase 2 is only needed if you also want the per-frame baseline to compare against). To try a variant without editing the config, pass overrides to the pack step, for example `scripts\make_cloud_bundle.py my_shot_ipa --set animatediff.ip_adapter.enabled=true`.

## 8. The whole project, end to end

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
6. Optional, for steadier results (section 7): **Phase 3: deflicker (config shot)**, or the Kaggle AnimateDiff route.

Phase 4 (LoRA training) is built and has its own run configurations (section 14b and `training/README.md`). Phases 5 and 6 (compositing, product) are not built yet (section 15).

## 9. Settings you change

All in `config/project.yaml`, which is read instead of `config/project.example.yaml` (the example stays as the template with the original defaults; the table's Default column is the example's). `project.yaml` currently has setting "D" for `my video new.MOV`: whole clip, shot `full_D`, style LoRA `bloodlust_style` at 0.6 (actor LoRA off), prompt adds `black hair, red eyes`, denoise 0.6, ControlNet 1.0 (the face follows the source lineart; "A" was the same with 0.8), deflicker strength 0.9 / sigma 8 / error 25. Running `cli.py` (or the VS Code run button) with it reuses the finished `full_D` frames; for another experiment give it a new `input.shot`. Note that the file is a complete copy: new keys added to the example later must be copied in by hand.

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
| `animatediff.*` | The cloud stage: motion module, window size, and `ip_adapter.enabled` (off by default) / `weight` / `reference`. Used by `cli.py animatediff` (cloud GPU only; see `docs/cloud-kaggle.md`). | `v3_sd15_mm.ckpt`, 16, 4, off, 0.5 |
| `temporal.mode`, `temporal.radius`, `temporal.strength`, `temporal.lowpass_sigma`, `temporal.error_threshold` | Phase 3 deflicker. **`mode: median`** (`project.yaml`) takes the per-pixel median of the `radius` frames on each side (3 default in the example; `project.yaml` uses 6, about 0.5 s each way at 12 fps), warped onto the frame along the source flow: steadier lines and shapes, no error build-up, and a one-frame colour flip is outvoted; `lowpass_sigma` 2 keeps the lines crisp (0 is steadier but softens them) and `strength` is how far toward the median (1). **`mode: recursive`** (the example's default): weight of the warped previous frame (0.9), the blur radius in pixels below which colors are blended so edges stay crisp, and the source color error above which the warp is ignored (25). **Sigma: 2 for a wide shot, 8 for a close-up face** — at 2 a face's cel shading is dragged along the optical flow and smears (`docs/phase4-results.md`); `project.yaml` uses 8. Changing them under an existing shot stops the run; use a new shot name. | `recursive`, `3`, `0.9`, `2`, `25` (`project.yaml`: `median`, `6`, `1.0`, `2`, `25`) |
| `sampling.seed` | Same seed on every frame of a shot, to limit flicker. | `12345` |
| `sampling.denoise` | How far the result moves from the source: lower stays closer. | `0.4` |
| `sampling.steps`, `cfg`, `sampler`, `scheduler` | Sampler settings. | 24, 7.0, euler_ancestral, normal |
| `controlnet.lineart_strength` | How strictly lineart guides the result. | `0.8` |
| `controlnet.smooth_radius` | `0` = off. Above 0, the lineart maps are smoothed over time first (median of this many maps on each side, warped by the source's optical flow) so the face lines the ControlNet follows stay steady. 3 at 12 fps gave a small gain; it adds a quick pre-pass. | `0` |
| `video.work_fps` | Frame rate used for stylizing and for the output. | `12` |
| `video.target_megapixels` | Working size per frame. About 0.4 fits a 6 GB GPU. | `0.4` |

## 10. Where the outputs go

Everything is under `work/<project>/` (default `work/default/`). `work/` is generated by running the project and is git-ignored. The unzipped Kaggle results (`result_*/` in the project folder) are git-ignored too.

| Folder | Contents |
|---|---|
| `frames/<shot>/` | Source frames, `frame_00001.png` ... , and `settings.json` |
| `anime/<shot>/` | Stylized frames and `settings.json` |
| `lineart/<shot>/` | The lineart control maps (for checking the guidance) |
| `lineart_raw/<shot>/`, `lineart_smooth/<shot>/` | Only with `controlnet.smooth_radius` > 0: the extractor's maps, and the time-smoothed maps the ControlNet reads |
| `deflicker/<shot>/` | Phase 3: the local deflicker applied to `anime/<shot>` |
| `animatediff/<shot>/` | Phase 3: the cloud AnimateDiff result (copied in from the Kaggle download) |
| `deflicker_animatediff/<shot>/` | Phase 3: the deflicker applied to the AnimateDiff result |
| `out/<shot>.mp4` | The finished phase 2 video, 12 fps, with the source audio |
| `out/<shot>_<stage>.mp4` | The same for the other stages (`_deflicker`, `_animatediff`, `_deflicker_animatediff`) |
| `work/cloud/bundle_<shot>.zip` | What you upload to Kaggle |
| `work/phase1/` | Phase 1 test output |
| `work/comfyui.log` | Log of a server the project started |

## 11. Shots, resuming and overwrite protection

A **shot** is one named run. Its frames and video are kept under that name.

- **Same shot, same settings:** the run resumes. Frames that already exist are skipped, so a crash or stop costs at most one frame. If everything is done, nothing runs and the server isn't even started.
- **Same shot, different settings** (a different video, start, seconds, seed, denoise, prompts, models and so on): the run **stops with a message** and changes nothing. A shot can't be overwritten by accident, and there is no force option.
- **To try new settings:** give the run a new shot name (`input.shot` in the config, or `--shot`). Every shot keeps its own frames and video, so you can compare them.
- **To keep using a shot,** change the settings back to what it was made with.
- Shots made before settings were tracked (`dance_preview`, `dance_d040`, `verify_d040`, `verify_msg`) have no record, so they are locked the same way. `dance_d040` is the phase 2 baseline video.

## 12. The ComfyUI server

You don't have to start it. Every run that needs it calls the same check:

- A server already answers: it is used and left alone, including one you started yourself.
- Nothing answers and `comfyui.autostart` is `true`: the project starts `scripts/start_comfyui.ps1` in the background, waits for it (about 35 seconds on this machine), runs, and then stops it (`comfyui.autostop`). Its log is `work/comfyui.log`.

On Linux (the Kaggle notebook) the same check starts `python main.py` instead of the PowerShell script.

Start it by hand only to use the ComfyUI web page: run **ComfyUI server only** (IDE) or `scripts\start_comfyui.ps1`, then open http://127.0.0.1:8188. Keep it to one server at a time on a 6 GB GPU.

## 13. Tests

**Tests: pytest** (IDE) or `.venv\Scripts\python.exe -m pytest tests -q`. They use real ffmpeg on a generated clip and a fake ComfyUI, so they need no GPU. They cover frame extraction, resuming, audio, the settings protection, the CLI, the server start and stop logic, the flicker and color metrics, the deflicker (both modes), the AnimateDiff graph and shot runner (with a fake ComfyUI), the cloud bundle, and the LoRA settings and file paths. 67 tests. VS Code's Testing panel also lists them.

They do not test the ComfyUI graphs themselves. Phase 1, a real preview and a Kaggle run do that.

**Reading the output of a run:** after stylizing it prints `GPU memory: peak ... MiB of 6144 MiB used`. The pipeline peaks at about 5.4 GB, so close other programs that use the GPU. That small headroom is why the AnimateDiff stage runs in the cloud.

## 14. Troubleshooting

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
| A run takes very long | Expected: 15 to 18 s per frame. Use a short `input.seconds` while testing. |
| Kaggle: `No project found under /kaggle/input` | Add your dataset to the notebook (Add Input). Re-upload if it is empty. |
| Kaggle: `ComfyUI does not have these nodes: ...` or `Node 'ACN_...' not found` | Run notebook step 2 again (installs the node packs), then step 4 (starts a fresh ComfyUI; a running one never sees new nodes). Use the current notebook and a freshly packed bundle. |
| Kaggle runs old code | The notebook runs the code in your uploaded dataset. After changing code, pack a new bundle and upload it as a new dataset version. |
| A bundle zip is only 1 KB | A failed pack can leave an empty zip. The real one is 44 to 130 MB, depending on the clip and the LoRAs; delete the empty one and pack again. |
| `cli.py animatediff` or `deflicker` says the settings changed | The default `animatediff.ip_adapter.enabled` changed to off. Shots made earlier with it on are protected; use a new shot name. |
| Unzipped Kaggle result is not found by `cli.py flicker` | The folders must be in `work/default/`, not in `result_<shot>/work/default/`. Copy them over (do not overwrite other shots). |

## 14b. Phase 4: LoRA training and use

Put the film in `training/input/` and photos of each actor in `training/data/actors/<name>/` (see `training/README.md`). Run `training/extract_style.py` (VS Code: "Phase 4: extract style frames") to fill `training/data/style/images/`, then check `contact_sheet.jpg` there. Settings are under `training:` in the config. Then run `training/caption.py` (VS Code: "Phase 4: caption style frames and actor photos"): it converts the actor photos (HEIC ok) to `training/data/actors_ready/<name>/` (`photo_NNN.jpg`, the full photo) and adds a face crop (`_face`) and an upper-body crop (`_upper`) cut from the original full-resolution photo next to it, nothing replaced (YuNet face detector, about 230 KB, downloaded once; `training.actors.crops: false` turns it off; crops are skipped when the face is too small, a second person is in the shot, or the crop is nearly the whole photo), downloads the WD14 tagger once (about 380 MB, CPU) and writes a `.txt` caption next to every image. Trigger words: `training.style.trigger` (default `bloodlust_style`) and `<name>_person` for actors (override with `training.actors.<name>.trigger`). Existing captions are never overwritten, so hand edits stay; delete a `.txt` to regenerate. 

**Training (local, 6 GB).** Once: `scripts/setup_training.py` (VS Code: "Phase 4: set up the training environment"; clones kohya sd-scripts into `third_party/` and builds `.venv-train`, a separate venv so `.venv` is untouched). Then close ComfyUI (it holds the GPU; the script refuses to start while port 8188 is open) and run `training/train.py --target style` or `--target Adwait` (VS Code entries for both, plus a 20-step smoke test). Output: `training/output/<name>/<name>.safetensors`, with an intermediate checkpoint every 2 epochs. Measured on the RTX 2060: 1.25 steps/s, about 3.6 GB of GPU memory, so 2400 to 2500 steps take about 33 minutes. The base model is the config's checkpoint (Counterfeit) at clip skip 1, to match the ComfyUI workflows, which have no clip-skip node. A finished LoRA is never overwritten: with changed settings the run stops; set `training.<target>.run` to a new name. 

**Checking a LoRA.** `training/eval_grid.py --target Adwait|style` (VS Code entries for both) copies the LoRA files into ComfyUI's `models/loras`, starts ComfyUI if needed, and renders the same 4 prompts with the same seed for the plain checkpoint, each saved epoch at weight 0.8 and the final file at two other weights (32 images, about 5 minutes). Result: `training/output/eval/<name>/grid.jpg` plus the single images. Results of the first run (actor `adwait_person`, style `bloodlust_style`, both 2400 to 2500 steps) are in `docs/phase4-results.md`. 

**Using LoRAs in the conversion.** List them under `style.loras` in the config (`file:` is the path to the .safetensors, relative to the project root or absolute, so pointing at another model is a one-line change; it is copied into ComfyUI's models/loras and the name defaults to the file's name; weight, optional trigger word and extra negatives; see the example in `config/project.example.yaml`). `cli.py run` / `preview` then chain a `LoraLoader` per entry into the img2img graph, add the trigger words to the prompt, and copy the files from `training/output/` into ComfyUI's `models/loras` if needed. The default is an empty list, which gives exactly the old graph. The list is part of the shot's recorded settings: change it and the shot stops, so use a new shot name. To try a variant without editing your config, set the environment variable `ANIME_CONFIG` to another yaml file. The AnimateDiff cloud workflow uses the same list: the bundle carries the LoRA files and the notebook copies them into ComfyUI (`docs/cloud-kaggle.md`).

**What the testing settled** (`docs/phase4-results.md` has the pictures and numbers):
- The **style LoRA at 0.6 with denoise 0.6 and ControlNet 1.0** (0.8 in the earlier `full_A`) gives the anime look on a close-up face. `config/project.yaml` holds exactly this.
- The **actor LoRA is off.** Trained on real photos, it pulls the face back to photographic and fights the anime look. The lineart ControlNet already carries the likeness in a close-up, so it adds little there.
- Add `black hair, red eyes` to the prompt to stop the hair and eye colour changing between frames; put `scar, blood, smoke` in the LoRA's negatives to keep the vampire-hunter details out.
- **Do not put `red hair` in the negatives**: it also removes the red eyes.
- For a close-up face use `temporal.mode: median` (radius 3 to 6, `lowpass_sigma: 2`); in recursive mode set `lowpass_sigma: 8`, or the shading smears. Stronger settings (strength 0.97, sigma 16 or 24) are no steadier: what remains (glasses flipping red/grey, face lines changing) comes from the generator, not the deflicker.
- **A jawline that flips between anime-sharp and round is the ControlNet, not the prompt.** At `lineart_strength: 0.8` it traces the real jaw, which wins on some frames and loses on others. 0.6 hands the shape to the style LoRA and keeps it steady; 0.5 is sharper but gaunt. Jaw words in the prompt alone barely help. The sharp-jaw (0.6) and colour-fix (glasses/skin words) variants cost image quality, so they are not in the config; `full_D` went the other way, ControlNet 1.0, to keep the face like the source.
- The **AnimateDiff cloud pass softens this look** even with the LoRA applied, so the local path is the one to use for a face.

## 15. Not built yet

From `plan.md`: phases 1 to 4 are done. Phase 4 is complete except for `cli.py train`, so training, captioning and evaluation are run through the scripts in `training/` (section 14b). Still to come: phase 5 (matting, compositing, face pass) and phase 6 (per-shot config list, web UI, cloud worker).

Open items from the earlier phases:
- **IP-Adapter** has only been tried at weight 0.5; lower weights are untested. It did not help, and it does not fix the cloud stage's softer look either (`docs/phase4-results.md`).
- **More clips.** The phase 3 settings were tuned on one clip and held up on a second, but a close-up face needed a different deflicker setting (`temporal.lowpass_sigma` 8 instead of 2).
- **RAFT optical flow** was tried in the deflicker and not kept: no gain on either test clip, even in fast camera pans (`phase3-guide.md` section 5.5).
- **The actor LoRA** is off by default: trained on real photos, it pulls the face back to photographic. Training it on anime-styled versions of the photos is the open idea (`docs/phase4-results.md`).

The numbers to compare against, on `dance_run1`, are in section 7 and `docs/phase3-guide.md`.

## 16. Change log

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
| 2026-10-31 | `cli.py flicker` also prints a color-steadiness line (frame-to-frame change and drift over the shot, Lab chroma units, lower = steadier). |
| 2026-10-31 | `make_cloud_bundle.py` takes `--set KEY=VALUE` overrides and a shot name for variants (e.g. `dance_run1_noip --set animatediff.ip_adapter.enabled=false`), and always stores the effective config in the zip. |
| 2026-10-31 | IP-Adapter is now off by default in the cloud stage (`animatediff.ip_adapter.enabled: false`): AnimateDiff alone was as steady and kept the source's colors better. `download_models.py --cloud` skips its 2.6 GB of models when it is off. |
| 2026-10-31 | This document and the README now say what is in git and what is generated or rebuilt (`.venv`, `third_party`, `work`), how to set up from a fresh clone, and how to run phase 3 end to end (section 7). |
| 2026-10-31 | Added `docs/phase3-guide.md` (design, files, tuning and results of phase 3) and moved the phase 3 results there from `phase2-results.md`. |
| 2026-11-01 | Phase 4 started: `training/extract_style.py` (film to style frames with contact sheet), `training/` folders for the film and actor photos, `training:` config section, one VS Code run config. Captioning and training not built yet. |
| 2026-11-02 | Phase 4: `training/caption.py` (actor photo conversion, WD14 captioning with trigger words); new dependencies in `.venv`: `onnxruntime` (CPU), `pillow-heif`. |
| 2026-11-02 | Phase 4: actor photos also get face and upper-body crops (`pipeline/photo_crops.py`, YuNet) next to the full photos; the contact sheet in `actors_ready/<name>/` shows all of them. |
| 2026-11-02 | Phase 4: local LoRA training: `scripts/setup_training.py` (kohya sd-scripts + `.venv-train`), `training/train.py`, `training.lora` config, four VS Code entries. |
| 2026-11-02 | Phase 4: first LoRAs trained (actor `adwait_person`, style `bloodlust_style`), `training/eval_grid.py` (comparison grid) and two VS Code entries. |
| 2026-11-02 | Phase 4: `style.loras` in the config puts trained LoRAs into the local img2img graph; `ANIME_CONFIG` env var picks another config file. First test: shot `dance_lora1` (see `docs/phase4-results.md`). |
| 2026-11-03 | `config/project.yaml` created with the selfie setting "A" (style LoRA 0.6, denoise 0.6, ControlNet 0.8, actor LoRA off, whole clip `my video new.MOV`, shot `full_A`); the LoRA test now sets its own `style.loras`. Deflicker of `full_A` and `full_C` measured in `docs/phase4-results.md`. |
| 2026-11-03 | Cloud stage carries LoRAs: `style.loras` goes into the AnimateDiff graph, `make_cloud_bundle.py` packs the LoRA files under `loras/`, notebook step 3 copies them into ComfyUI. Bundle for `full_A` built (`work/cloud/bundle_full_A.zip`, 129 MB). Rebuild and re-upload the Kaggle dataset after this change: the old notebook and code do not know LoRAs. |
| 2026-11-05 | Deflicker `temporal.lowpass_sigma` raised from 2 to 8 in `config/project.yaml`: at 2 the face's cel shading was dragged along the optical flow and smeared. The cloud AnimateDiff run of `full_A` applied the style LoRA correctly but still softens the anime look, so the local path stays the one for this clip (`docs/phase4-results.md`). |
| 2026-11-05 | Documentation brought up to date across `README.md`, `plan.md`, `CLAUDE.md`, `docs/phase1-guide.md`, `phase2-results.md`, `phase3-guide.md`, `cloud-kaggle.md` and `phase4-results.md`: phase 4 is built, the settled LoRA and deflicker settings are recorded, and the stale "phase 4 not started" notes are gone. |
| 2026-11-05 | `config/project.yaml` switched to the sharp-jaw settings ("J2"): `controlnet.lineart_strength` 0.8 -> 0.6, `sharp jawline, angular face, defined chin, narrow face` added to the prompt and `round face, chubby, soft jaw, double chin, fat` to the negatives, shot name `full_A` -> `full_B`. At 0.8 the jawline flipped between anime-sharp and round between frames (`docs/phase4-results.md`). |
| 2026-11-07 | `config/project.yaml` colour fix ("K2"): `dark grey glasses` added to the prompt (no skin-colour words: any of them overshoots), `red glasses, red frame, colored glasses, pale skin, pasty, red lips` to the negatives, `controlnet.lineart_strength` 0.6 -> 0.7. Skin had swung white/pale and the glasses red/black/brown (`docs/phase4-results.md`). |
| 2026-11-07 | `config/project.yaml` set back to setting "A" (everything the `full_A` run used: no jaw/glasses/skin words, ControlNet 0.8, style LoRA 0.6, denoise 0.6, shot `full_A`), keeping the deflicker settings (`lowpass_sigma: 8`). The jaw (J2) and colour (K1 to K6) experiments cost image quality; they stay documented in `docs/phase4-results.md` but are not in the config. |
| 2026-11-07 | `config/project.yaml` = the `full_D` run: `controlnet.lineart_strength` 0.8 -> 1.0 (the face follows the source lineart; the prompt is unchanged from `full_A`) and shot `full_D`; deflicker unchanged (strength 0.9, `lowpass_sigma: 8`, error threshold 25). Stronger deflicker variants (strength 0.97, sigma 16/24) were no steadier (`docs/phase4-results.md`). |
| 2026-11-07 | New deflicker mode `temporal.mode: median` (+ `temporal.radius`) in `pipeline/temporal.py`: per-pixel median of the 3 frames on each side warped onto the frame, non-recursive, so no error build-up. `config/project.yaml` now uses it (`lowpass_sigma: 2`, strength 1.0); the example keeps `recursive`. On `full_D` the whole-frame SSIM ratio went 0.893 -> 0.939. Changing mode needs a new shot name (the deflicker folder of `full_D` holds recursive frames, so `cli.py deflicker` stops with `SettingsChanged` until that folder is moved or deleted). 65 tests. |
| 2026-11-07 | `style.loras` entries take `file:`, the path to the LoRA (relative to the project root or absolute); `config/project.yaml` now points at `training/output/bloodlust_style/bloodlust_style.safetensors`. `name:` is optional (the file name); without `file:` the old lookup (ComfyUI's models/loras, then `training/output/<run>/`) still works. The path is not part of a shot's recorded settings, so existing shots like `full_D` are still resumable, and the cloud bundle strips it from its copy of the config. 67 tests. |
| 2026-11-07 | `config/project.yaml`: `temporal.radius` 3 -> 6 (the deflicker settings of the `fps24_T` test, at 12 fps: median mode, strength 1.0, `lowpass_sigma: 2`, error threshold 25). Radius 6 uses 6 frames each way, twice the time span of 3. The existing `deflicker/full_D` frames were made with radius 3, so `cli.py deflicker` stops with `SettingsChanged` until that folder is moved. |
| 2026-11-07 | Config comments only: `video.work_fps` is marked as the output fps (it already set the extract, stylize and encode rate; changing it needs a new shot name), and `temporal.radius` lists suggested values per fps (12: 3 or 6, 15: 4 or 8, 24: 6 or 12, 30: 8 or 15; radius / fps = seconds each way). |
| 2026-11-07 | `config/project.yaml` = the `full_E` run: `video.work_fps` 12 -> 30, `temporal.radius` 6 -> 8 (0.27 s each way at 30 fps; the per-fps radius suggestions are in the comments above `radius`), shot `full_E`. Whole clip: 190 frames, about 65 min render + 8 min deflicker. Results in `docs/phase4-results.md`. |
| 2026-11-08 | New `controlnet.smooth_radius` (default 0 = off, in both config files): smooths the lineart maps over time before the ControlNet (`pipeline/lineart.py`, new folders `lineart_raw/` and `lineart_smooth/`). It is part of the shot's recorded `controlnet` settings, so changing it needs a new shot name. `ComfyClient.upload_image` takes an optional upload name. Results in `docs/phase4-results.md`. 68 tests. |
| 2026-11-08 | `config/project.yaml` input changed to `my video new2.MOV`, shot `new2_30fps` (30 fps, `temporal.radius` 8, everything else as `full_E`). An earlier run on `my video new1.MOV` (shot `new1_30fps`, radius 15) was stopped by the system's low-memory guard and then by hand at 177 of 475 frames; it resumes with the same shot name and settings. New videos must be set in `input.video` and given a new `input.shot`. |
