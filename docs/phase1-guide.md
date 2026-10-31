# Phase 1 Guide: where everything lives and who calls what

Everything here was checked against the files on disk (sizes measured, checkpoint contents read from its header). Paths are relative to the project root `D:\projects\video to anime conversion using AI` unless they start with a drive letter.

---

## 1. The one-minute picture

```
you run:  scripts\test_single_frame.py  my_image.png
              │ reads settings                      ┌─ config/project.example.yaml  (or project.yaml)
              │ loads the graph  ───────────────────┼─ workflows/img2img_lineart_api.json
              │ talks HTTP via                      └─ pipeline/comfy_client.py
              ▼
      ComfyUI server  (third_party/ComfyUI, started by scripts/start_comfyui.ps1, port 8188)
              │ runs the 13-node graph, loading weights from:
              ├─ models/checkpoints/Counterfeit-V3.0_fix_fp16.safetensors   (UNet + CLIP + VAE)
              ├─ models/controlnet/control_v11p_sd15s2_lineart_anime_fp16.safetensors
              └─ custom_nodes/comfyui_controlnet_aux/ckpts/lllyasviel/Annotators/netG.pth
              ▼
      third_party/ComfyUI/output/*.png   ──copied by the client──►   work/phase1/*.png
```

Two separate programs are involved. **ComfyUI is the engine that loads models and runs the diffusion.** **Our Python code never touches a model file**; it only sends a graph over HTTP and downloads the resulting PNGs.

---

## 2. Every model and weight file

All of these are on disk now. Total model data is about 2.9 GB.

| # | File | Size | Full location | What it is | Who loads it |
|---|---|---|---|---|---|
| 1 | `Counterfeit-V3.0_fix_fp16.safetensors` | 2,034 MB | `third_party\ComfyUI\models\checkpoints\` | Anime Stable Diffusion 1.5 checkpoint (gsdf/Counterfeit-V3.0). **Contains three models in one file** (see below). | Workflow node `"1"` (`CheckpointLoaderSimple`) |
| 2 | `control_v11p_sd15s2_lineart_anime_fp16.safetensors` | 689 MB | `third_party\ComfyUI\models\controlnet\` | ControlNet for anime line art. It forces the output to follow the outlines. | Node `"6"` (`ControlNetLoader`) |
| 3 | `netG.pth` | 208 MB | `third_party\ComfyUI\custom_nodes\comfyui_controlnet_aux\ckpts\lllyasviel\Annotators\` | The line-art *extractor* network (photo → line drawing). It is not a diffusion model. | Node `"7"` (`AnimeLineArtPreprocessor`), at the moment it runs |

### The checkpoint is really three models

I read the safetensors header. All tensors are fp16.

| Part | Tensors | Size | Used by node |
|---|---|---|---|
| UNet (the denoiser) | 686 | ~1,639 MB | `"10"` KSampler, via output 0 of node `"1"` (`MODEL`) |
| CLIP text encoder (turns prompt text into numbers) | 197 | ~235 MB | `"4"` and `"5"` CLIPTextEncode, via output 1 (`CLIP`) |
| VAE (converts between pixels and latents) | 248 | ~160 MB | `"9"` VAEEncode, `"11"` VAEDecode, `"8"` ControlNet, via output 2 (`VAE`) |

That is why `models\clip`, `models\vae`, `models\text_encoders` and `models\unet` are all **empty**. Nothing is missing. The CLIP *tokenizer* (the vocab files that split text into tokens) is not a download either; it ships inside ComfyUI at `third_party\ComfyUI\comfy\sd1_tokenizer\`.

### Things that look like files but aren't models

- `.cache\huggingface\download\*.metadata` folders inside `models\checkpoints`, `models\controlnet` and the `Annotators` folder are bookkeeping from the Hugging Face downloader (a hash and a timestamp). They are about 0 bytes and safe to ignore.
- `C:\Users\adwai\.cache\huggingface\` holds about 1 MB of downloader logs. The model files themselves are **not** cached there. They were downloaded directly into the ComfyUI folders.
- `models\configs\` (11 small files) are ComfyUI's built-in YAML configs for old SD architectures. They aren't downloads.

### How each file got there (this matters for a cloud GPU later)

| File | Downloaded by | When |
|---|---|---|
| Checkpoint, ControlNet, `netG.pth` | `scripts/download_models.py` (the `FILES` list at the top; paths are relative to `third_party/ComfyUI`) | Setup, explicit |

`netG.pth` is in the script too, so a fresh or cloud machine gets it at setup. (Before that, the controlnet_aux node downloaded it from `lllyasviel/Annotators` the first time the workflow ran, and it still would as a fallback.)

### Folders that exist but are empty (reserved for later phases)

| Folder under `third_party\ComfyUI\models\` | Will hold | Phase |
|---|---|---|
| `loras\` | Style LoRA and one LoRA per actor | 4 |
| `controlnet\` (more files) | Depth, OpenPose ControlNets | 3 |
| `clip_vision\` | CLIP-Vision model that IP-Adapter needs | 3 |
| `ipadapter\` (needs creating) | IP-Adapter weights | 3 |
| `animatediff_models\` (created by the AnimateDiff node) | Motion module | 3 |
| `optical_flow\`, `frame_interpolation\` | RAFT, RIFE | 3 / 5 |
| `vae\`, `upscale_models\`, `embeddings\` | Optional extras | as needed |

---

## 3. Who calls what, step by step

### 3.1 The Python side (`scripts/test_single_frame.py`)

1. `load_config()` (in `pipeline/stylize.py`) reads `config\project.yaml` if it exists, otherwise `config\project.example.yaml`. **`project.yaml` does not exist yet**, so the example file is what's actually being used.
2. It makes a `ComfyClient(cfg["comfyui"]["url"])` and wraps the rest in `comfy_server()` (`pipeline/server.py`, added in phase 2). That calls `client.is_up()` (`GET /system_stats`); if nothing answers, it starts `scripts\start_comfyui.ps1` in the background, waits, and stops the server again afterwards. A server you started yourself is used and left alone.
3. `build_workflow()` (in `pipeline/stylize.py`) loads `workflows\img2img_lineart_api.json` and **overwrites specific fields by node id** (table in section 4).
4. `client.upload_image()` sends your image to ComfyUI's `input\` folder (`POST /upload/image`) and gets back the file name to put in node `"2"`.
5. `client.run()` does three things in order:
   - `queue()` → `POST /prompt` (server starts working).
   - `wait()` → polls `GET /history/<id>` once per second until finished.
   - `download_outputs()` → `GET /view?...` for each saved image, writes it to `work\phase1\` and returns the paths keyed by node id. An optional `names` argument renames them (e.g. `{"12": "anime/frame_00001.png"}`).

### 3.2 The ComfyUI side: the 13-node graph (`workflows\img2img_lineart_api.json`)

Execution follows the data dependencies, not the numeric order.

| Node | Class | Takes input from | Does | Weight file touched |
|---|---|---|---|---|
| 1 | CheckpointLoaderSimple | none | Loads UNet + CLIP + VAE | **Counterfeit…fp16.safetensors** |
| 2 | LoadImage | none | Reads your uploaded image from `ComfyUI\input\` | none |
| 3 | ImageScaleToTotalPixels | 2 | Resizes to about 0.4 megapixels (the VRAM budget) | none |
| 4 | CLIPTextEncode (positive) | 1 (CLIP) | Encodes the positive prompt | uses CLIP part of #1 |
| 5 | CLIPTextEncode (negative) | 1 (CLIP) | Encodes the negative prompt | uses CLIP part of #1 |
| 6 | ControlNetLoader | none | Loads the lineart ControlNet | **control_v11p…lineart_anime_fp16.safetensors** |
| 7 | AnimeLineArtPreprocessor | 3 | Photo → line drawing | **netG.pth** |
| 8 | ControlNetApplyAdvanced | 4, 5, 6, 7, 1 (VAE) | Attaches the line art to both prompts as guidance | none |
| 9 | VAEEncode | 3, 1 (VAE) | Pixels → latent (the img2img starting point) | uses VAE part of #1 |
| 10 | KSampler | 1 (MODEL), 8, 9 | Denoises the latent. **This is the heavy step.** | uses UNet part of #1 |
| 11 | VAEDecode | 10, 1 (VAE) | Latent → pixels | uses VAE part of #1 |
| 12 | SaveImage (`anime`) | 11 | Writes the result to `ComfyUI\output\anime_NNNNN_.png` | none |
| 13 | SaveImage (`lineart`) | 7 | Writes the control map to `ComfyUI\output\lineart_NNNNN_.png` (debug) | none |

---

## 4. Config key → graph node (what changes what)

| `config/project.example.yaml` key | Node it overwrites | Field |
|---|---|---|
| `models.checkpoint` | `"1"` | `ckpt_name` |
| `video.target_megapixels` | `"3"` | `megapixels` |
| `style.positive` | `"4"` | `text` |
| `style.negative` | `"5"` | `text` |
| `models.controlnet_lineart` | `"6"` | `control_net_name` |
| `controlnet.lineart_strength` | `"8"` | `strength` |
| `sampling.seed / steps / cfg / sampler / scheduler / denoise` | `"10"` | `seed, steps, cfg, sampler_name, scheduler, denoise` |
| `--denoise`, `--seed` on the command line (`test_single_frame.py` or `cli.py`) | `"10"` | override the two above |
| the image argument | `"2"` | `image` (via `upload_image`) |

Not graph nodes: `comfyui.url` is used by the client (its port is used when the server is auto-started), `comfyui.autostart` and `comfyui.autostop` are used by `pipeline/server.py`, and `video.work_fps` and `input.*` are used by `cli.py` (phase 2). `style.style_lora` is still a placeholder for phase 4.

---

## 5. File-by-file reference

### Ours (all small)

| File | Purpose |
|---|---|
| `plan.md` | The approved 7-stage architecture and 6-phase roadmap |
| `CLAUDE.md` | Orientation for future Claude Code sessions |
| `README.md` | Setup and run commands |
| `requirements.txt` | Pipeline-side Python deps (torch is installed separately with the CUDA index) |
| `config/project.example.yaml` | All tunable settings (see section 4) |
| `pipeline/comfy_client.py` | `ComfyClient`: `is_up`, `upload_image`, `queue`, `wait`, `download_outputs`, `run`. The only code that talks to ComfyUI. |
| `workflows/img2img_lineart_api.json` | The 13-node graph (API format) |
| `scripts/start_comfyui.ps1` | Refreshes PATH, then starts ComfyUI with the project venv on `127.0.0.1:8188` |
| `scripts/download_models.py` | Downloads the checkpoint, ControlNet and `netG.pth` from Hugging Face into their ComfyUI folders. Skips files already present. |
| `scripts/test_single_frame.py` | The phase-1 smoke test (section 3.1) |
| `pipeline/stylize.py` | `load_config()` and `build_workflow()`: writes config values into the graph by node id. Shared by the smoke test and later batch stages. |
| `pipeline/__init__.py` | Empty; makes `pipeline` importable |
| *Phase 3 files* | `pipeline/temporal.py`, `pipeline/animatediff.py`, `scripts/make_cloud_bundle.py`, `notebooks/`, `tests/test_phase3.py`: described in `phase3-guide.md` |
| *Phase 2 files* | `cli.py`, `pipeline/video.py`, `pipeline/batch.py`, `pipeline/metrics.py`, `tests/test_phase2.py`: described in `phase2-results.md` |

### Not ours

| Path | What |
|---|---|
| `.venv\` (5.7 GB) | Python 3.11 environment: PyTorch 2.14+cu126 and ComfyUI's requirements |
| `third_party\ComfyUI\` (3.0 GB) | Upstream ComfyUI. Don't edit. |
| `third_party\ComfyUI\custom_nodes\comfyui_controlnet_aux\` | Third-party node pack providing node 7 |

### Generated output

| Path | Contents |
|---|---|
| `third_party\ComfyUI\output\` | Where ComfyUI itself saves. The counter increments every run (`anime_00001_`, `00002_`, …). |
| `work\phase1\` | The client's copy of each run's outputs. Currently 4 files: `anime_00001_`, `anime_00002_`, `lineart_00001_`, `lineart_00002_`, so there are two runs' worth. |
| `third_party\ComfyUI\input\` | `example.png` (ComfyUI's mascot drawing, the test image) plus anything you upload. |

### Installed outside the project

Python 3.11, Git, FFmpeg and a newer Visual C++ Redistributable (all via winget, system-wide), plus the 1 MB downloader log folder under `C:\Users\adwai\.cache\huggingface`.

---

## 6. Phase 1: done vs pending

### Done (verified)

- Toolchain installed; PyTorch sees the RTX 2060 (6 GB) with CUDA.
- ComfyUI cloned and runs; controlnet_aux node added with only the dependencies the anime preprocessor needs.
- Anime checkpoint and lineart ControlNet downloaded; `netG.pth` auto-downloaded on first run.
- `ComfyClient`, the workflow, config file and scripts written.
- **Lineart size fix:** the preprocessor's `resolution` sets the map's short side, so `test_single_frame.py` now mirrors node 3's scaling and writes the result into node 7. Verified: the map is 648×648, matching the 648×648 output (it was 512×512 before). The JSON's `512` is just a placeholder that code overwrites.
- **One end-to-end run succeeded** in about 39 s: image in, anime image plus lineart map out. I looked at both: colors became flat cel-shaded anime, and the pose, clouds and hill were preserved.

### Pending or not yet verified

| Item | Detail |
|---|---|
| ~~Test on a real photo or video frame~~ | Done in phase 2 on a real dance clip (see `phase2-results.md`). Close-up faces are still untested. |
| ~~Peak VRAM not measured~~ | Measured in phase 2: peak 5399 MiB of 6144 MiB (see `phase2-results.md` section 6). |
| No `config/project.yaml` | Only the example is used. Create your own copy before changing settings. |
| Settings partly tuned | Phase 2 lowered `denoise` to 0.4. `lineart_strength 0.8` and the prompts are still first guesses. |
| Node ids are hard-coded | Editing the workflow in ComfyUI's UI and re-exporting will renumber nodes and break the patching in `test_single_frame.py`. |
| Graphs not unit-tested | The tests fake ComfyUI, so nothing tests a ComfyUI graph itself; the graphs were checked by running them (phase 3's AnimateDiff graph also on Kaggle). |
| Duplicate outputs | Each run is stored twice (`ComfyUI\output` and `work\phase1`). Harmless; clear when disk matters. |

### Out of phase 1's scope, so correctly absent

Video ingest and encode and a CLI (built in phase 2, see `phase2-results.md`). AnimateDiff and the deflicker (built in phase 3, see `phase3-guide.md` and `cloud-kaggle.md`). Matting, other ControlNets, LoRAs and compositing are phases 4 to 6, not built yet.

---

## 7. How later phases will extend this

| Phase | New files and models | Touches |
|---|---|---|
| 2 Frame MVP (**done**) | `pipeline/video.py`, `batch.py`, `metrics.py`, `cli.py`, `tests/` | Reuses the client and workflow unchanged |
| 3 Consistency | AnimateDiff motion module, IP-Adapter and CLIP-Vision weights, depth/OpenPose ControlNets, new workflow JSON | New folders listed in section 2; more custom nodes |
| 4 Training | `training/`, kohya_ss; outputs land in `models\loras\` | Node `"1"` gets a LoraLoader after it |
| 5 Composite | `pipeline/preprocess.py` (matting), `composite.py` | Matting models (RVM or SAM2) |
| 6 Product | `cli.py`, FastAPI app | Wraps everything above |
