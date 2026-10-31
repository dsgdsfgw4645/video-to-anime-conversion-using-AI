# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A video → anime converter modelled on Corridor Crew's *Anime Rock Paper Scissors*. Python drives a local ComfyUI server over its HTTP API. `plan.md` holds the full 7-stage architecture and 6-phase roadmap (ingest → preprocess → conditioning → stylize → temporal → composite → encode, plus an offline LoRA training track). **Phases 1 and 2 are built**: the single-image img2img + anime-lineart ControlNet test, plus a resumable frame pipeline (`cli.py`: ingest → per-frame img2img → encode, in `pipeline/video.py` and `pipeline/batch.py`). Tests live in `tests/` (phase 2 only; there is no linter). There is no temporal consistency, matting or LoRA yet (phases 3 to 5), so don't assume they exist.

## Commands

Windows / PowerShell. Always use the project venv (Python 3.11); the system default `python` is 3.15, which PyTorch doesn't support.

```powershell
scripts\start_comfyui.ps1                                  # ComfyUI server on 127.0.0.1:8188 (blocks; run in its own terminal/background)
.venv\Scripts\python.exe scripts\test_single_frame.py [image] [--denoise 0.45] [--seed 1]   # outputs to work/phase1/
.venv\Scripts\python.exe scripts\download_models.py        # idempotent; fetches checkpoint, ControlNet and netG.pth into third_party/ComfyUI
.venv\Scripts\python.exe cli.py preview [video] [--start 5 --seconds 4]   # defaults from config `input:`; ~15 s/frame; output work/default/out/<shot>.mp4
.venv\Scripts\python.exe cli.py                      # no command = `run` with the config's input (IDE run button)
.venv\Scripts\python.exe cli.py run [video]                # config's slice (`seconds: null` = whole clip); re-run to resume
.venv\Scripts\python.exe cli.py flicker <shot>   # consecutive-frame SSIM, stylized vs source (phase 2 baseline)
.venv\Scripts\python.exe -m pytest tests -q    # phase 2 tests; no GPU or ComfyUI needed
```

Full from-scratch setup is in `README.md`. `docs/how-to-run.md` is the user's run reference (IDE and command prompt, per phase, settings, troubleshooting) with a change log: **update it, including the change log, whenever you add or change anything that affects how the project is run**. A single-frame run takes about 40 s on the RTX 2060 (6 GB). `docs/phase1-guide.md` maps every model file to the workflow node that loads it and lists what phase 1 still has pending; keep it in sync when models or nodes change. `docs/phase2-results.md` covers the frame pipeline, the flicker baseline and known issues; update it when phase 3 changes the baseline.

## Architecture

- **`pipeline/comfy_client.py`** is the only thing that talks to ComfyUI: `upload_image` → `queue` → `wait` (polls `/history`, no websocket) → `download_outputs`. `run()` chains them. Outputs come back as `{node_id: [paths]}`; an optional `names={"12": "anime/frame_00001.png"}` saves them under your own names instead of ComfyUI's counter names. Future stages should call ComfyUI through this client.
- **Phase 2 frame pipeline:** `cli.py` (`preview`, `run`, `flicker`) → `pipeline/video.py` (ffmpeg `extract_frames` / `encode`, audio muxed from the source) → `pipeline/batch.py` (`stylize_shot`, one `ComfyClient` round trip per frame, skips frames whose `anime/<shot>/frame_*.png` exists). `pipeline/metrics.py` holds the flicker metric. Video, start, seconds and shot name come from the config's `input:` section (`shot` falls back to the video's file name, plus `_preview` for `preview`); CLI options override it.
- **ComfyUI is started on demand:** `pipeline/server.py` (`comfy_server`) uses a running server if there is one, otherwise starts `scripts/start_comfyui.ps1` hidden, waits, and stops it afterwards if it started it (`comfyui.autostart` / `autostop` in the config). `stylize_shot` and `test_single_frame.py` use it, and `stylize_shot` skips it when no frame is left to do. The user wants every entry point runnable from the IDE with no terminal step, so new scripts should take no required arguments, and each needs a `.vscode/launch.json` entry.
- **Resume and settings tracking:** `pipeline/shot_state.py` writes a `settings.json` into `frames/<shot>` (video, size, mtime, start, seconds, fps) and `anime/<shot>` (effective seed and denoise, sampling, style, models, ControlNet, megapixels, plus the frames' own settings). Same settings: finished frames are skipped (resume). Changed settings, or a shot made before tracking (no `settings.json`): the run stops with `SettingsChanged` (exit code 1, a message naming what changed) before deleting, overwriting or encoding anything. There is deliberately no force flag, so a shot can't be overwritten by accident: set a new shot name (`input.shot` in the config, or `--shot`). Shots in `work/` made before tracking (`dance_preview`, `dance_d040`, `verify_d040`, `verify_msg`) have no record and are locked the same way; `dance_d040` is the phase 2 baseline.
- **`workflows/*.json`** are ComfyUI *API-format* graphs, not UI-format ones. Re-export from ComfyUI with "Save (API Format)".
- **Workflows are patched by hard-coded node id** in `pipeline/stylize.py` (`build_workflow()` sets `wf["10"]` for the KSampler, `wf["4"]`/`wf["5"]` for the prompts, and so on). `scripts/test_single_frame.py` and `pipeline/batch.py` call it. If you renumber or add nodes in a workflow JSON, update `build_workflow()` and the `ANIME_NODE`/`LINEART_NODE` constants. `workflows/img2img_lineart_api.json` has both a final `SaveImage` (`anime`) and a debug one for the lineart map (`lineart`).
- **The script runs the JSON file, not whatever graph is open in the ComfyUI browser UI.** The UI's default template (it uses a `qwen_3_4b` CLIP and different sampler values) is unrelated to our workflow, and its "missing model" warning can be ignored. Our graph has no `CLIPLoader`: UNet, CLIP and VAE all come from the one checkpoint loaded by node `"1"`, so `models/clip` and `models/vae` are empty on purpose.
- **Model files:** the checkpoint, ControlNet and `netG.pth` (the lineart extractor weights, about 208 MB) are all fetched by `scripts/download_models.py`. Its `FILES` paths are relative to `third_party/ComfyUI`, since `netG.pth` goes under `custom_nodes/comfyui_controlnet_aux/ckpts/`, not `models/`.
- **Lineart map size:** the preprocessor's `resolution` sets the map's *short side*. `build_workflow()` in `pipeline/stylize.py` computes the short side node `"3"` produces and writes it into node `"7"`, so the map matches the frame. The JSON's `512` is only a placeholder; always build the graph through `build_workflow()` (phase 2's batch loop included).
- **`config/project.example.yaml`** is the single source of tunables (input video/start/seconds, models, prompts, seed, denoise, ControlNet strength, `target_megapixels`). Code reads `config/project.yaml` first, then falls back to the example; `project.yaml` doesn't exist yet. Default denoise is 0.4 (0.55 drifted on the dance clip).
- **Tests** (`pytest tests -q`) fake ComfyUI and use real ffmpeg on a generated clip, so they run without a GPU or server. `samples/dance/dance.webm` is the real test clip (CC BY 3.0, ThierryTuyishimeTV); stylizing is about 15 s/frame, so keep previews short.
- **`third_party/ComfyUI`** is an upstream checkout (plus the `comfyui_controlnet_aux` custom node). Treat it as vendor code; don't edit it. Its contributor `AGENTS.md` applies only to changes to ComfyUI itself.
- Design intent to preserve: stages read and write `work/<project>/<stage>/<shot>/frame_%05d.png` so they're resumable, and a fixed seed and prompt per shot limit flicker. Stylization targets 12 fps and about 0.4 MP, which is the 6 GB VRAM budget (SD1.5; SDXL and video models are cloud-only).

## Environment gotchas

- **PATH in new shells:** winget installs (git, ffmpeg) aren't on PATH in the tool shell until you refresh it: `$env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")`. `start_comfyui.ps1` already does this.
- **`OSError: WinError 1114` loading `c10.dll`** means the Visual C++ Redistributable is too old. Upgrade `Microsoft.VCRedist.2015+.x64`.
- **Don't `pip install -r` the controlnet_aux requirements.txt wholesale.** It pulls `mediapipe`/`onnxruntime-gpu`, which can pin numpy below 2 and break the torch stack. Install only the deps the specific preprocessor needs (the current minimal set is in `README.md`).
- `.venv/`, `third_party/` and `work/` are generated or vendored. There is no git repo in the project root yet.
