# Phase 3 Guide: steadier video (deflicker, and AnimateDiff in the cloud)

Phase 2 stylizes every frame on its own, so the result flickers and the colors of clothes change from frame to frame. Phase 3 adds two ways to fix that, and measures each against the phase 2 baseline (`phase2-results.md`). You can use either, or both.

- **A. Flow-warp deflicker:** blends each stylized frame with the previous one, warped along the source video's motion. CPU only, seconds, runs on this machine.
- **B. AnimateDiff in the cloud:** the whole shot goes through ComfyUI in one pass with a motion module that keeps neighbouring frames consistent. It needs about 16 GB of GPU memory, so it runs in a Kaggle notebook, not on the RTX 2060 (6 GB).

**Short answer from the one clip tested (`dance_run1`):** the local deflicker alone removes most of the grayscale flicker; AnimateDiff is what keeps colors steady; AnimateDiff alone plus the deflicker is the best result; IP-Adapter (a color reference image) did not help and is off by default. Section 5 has the numbers.

## 1. How it works

```
phase 2 frames  ->  A. deflicker (local, CPU)  ->  deflicker/<shot>
frames/<shot>   ->  B. Kaggle: AnimateDiff pass  ->  animatediff/<shot>  ->  deflicker  ->  deflicker_animatediff/<shot>
```

**A. The deflicker** (`pipeline/temporal.py`, `cli.py deflicker`). For each frame after the first:
1. Optical flow (OpenCV Farneback) is computed between this source frame and the previous one, at the stylized frame's size.
2. The previous *output* frame is warped along that flow, so it lines up with the current frame.
3. A trust map says where the warp can be believed: where the warped previous *source* matches the current source (color error below `temporal.error_threshold`). Occlusions, fast motion and cuts get no blending.
4. Only the coarse colors and tones (blur radius `temporal.lowpass_sigma` pixels) of the fresh frame are moved toward the warped one, by `temporal.strength` times the trust. The fresh frame keeps its own edges and fine detail, so moving limbs stay sharp.

The first frame is copied unchanged. Blending every frequency (`lowpass_sigma: 0`) steadies a bit more but softens the picture to 58% of the original sharpness and leaves smeared trails behind moving limbs above strength 0.7, so it is not used.

**B. The cloud stage** (`pipeline/animatediff.py`, `cli.py animatediff`, run by `notebooks/kaggle_animatediff.ipynb`). `workflows/animatediff_lineart_api.json`:
1. The shot's frames are loaded as one batch (VideoHelperSuite `VHS_LoadImagesPath`) and scaled to `video.target_megapixels` (0.4), the same size as phase 2.
2. The same anime-lineart ControlNet as phase 2 guides the structure. It uses the **Advanced-ControlNet** nodes, because the stock ControlNet nodes crash AnimateDiff's sliding windows.
3. One KSampler pass (same seed, denoise 0.4, steps and prompts as phase 2) over the whole batch with **AnimateDiff v3** (`v3_sd15_mm.ckpt`), in overlapping 16-frame windows (overlap 4, `pyramid` blending), so the seams between windows blend.
4. Optionally **IP-Adapter** conditions every frame on a reference image. It is off by default.
5. The results are saved under the source frames' names.

One pass makes the whole shot, so the stage is all or nothing: if it fails, nothing is written.

## 2. Files

| File | Purpose |
|---|---|
| `pipeline/temporal.py` | the deflicker: `blend_frame`, `deflicker_shot`, `output_stage` |
| `pipeline/animatediff.py` | the cloud stage: `build_workflow`, `animatediff_shot`; checks that ComfyUI has the needed nodes |
| `workflows/animatediff_lineart_api.json` | the AnimateDiff graph (API format; patched by node id in `build_workflow()`) |
| `notebooks/kaggle_animatediff.ipynb` | the Kaggle notebook: install, download models, start ComfyUI, run, measure, package |
| `scripts/make_cloud_bundle.py` | packs the zip to upload: code, effective config, frames (extracted if missing); `--set KEY=VALUE` overrides for variants |
| `scripts/download_models.py --cloud` | fetches the AnimateDiff motion module, and the IP-Adapter models only if IP-Adapter is enabled |
| `pipeline/metrics.py` | the flicker metrics, now with `color_consistency` |
| `pipeline/comfy_client.py`, `server.py`, `vram.py` | `missing_nodes()`; starts ComfyUI on Linux too; no Windows-only flag |
| `cli.py` | commands `deflicker`, `animatediff`, `encode`; `flicker --stage` |
| `config/project.example.yaml` | new sections `animatediff:` and `temporal:` |
| `samples/dance/ip_reference.png`, `samples/dance/ip_reference_ad.png` | the two IP-Adapter reference images tried |
| `tests/test_phase3.py` | 22 tests (the whole suite is 47); ComfyUI is faked |
| `cloud-kaggle.md` | the step-by-step guide for the Kaggle route |

## 3. Running it

Section 7 of `how-to-run.md` has the steps for the IDE and the command prompt, and `cloud-kaggle.md` has the Kaggle details. In short:

```powershell
.venv\Scripts\python.exe cli.py deflicker                                  # A: after phase 2, writes deflicker/<shot> and out/<shot>_deflicker.mp4
.venv\Scripts\python.exe cli.py flicker --stage deflicker                  # measure it
.venv\Scripts\python.exe scripts\make_cloud_bundle.py                      # B: pack the zip for Kaggle (extracts the frames itself)
# upload the zip as a Kaggle dataset, run the notebook, unzip result_<shot>.zip into the project folder (merge work\default\...), then:
.venv\Scripts\python.exe cli.py flicker --stage animatediff
.venv\Scripts\python.exe cli.py deflicker --source animatediff             # (the notebook already ran this; harmless to repeat)
.venv\Scripts\python.exe cli.py flicker --stage deflicker_animatediff
.venv\Scripts\python.exe cli.py encode --stage animatediff                 # mp4 of any stage
```

Stage folders under `work/default/`: `anime` (phase 2), `deflicker`, `animatediff`, `deflicker_animatediff`. `cli.py flicker <shot> --stage <folder>` measures any of them.

## 4. Resuming and settings protection

Same rules as phase 2 (`phase2-results.md` section 3), with one difference:
- **Deflicker:** resumes per frame. A rerun with the same settings skips frames already made.
- **AnimateDiff:** all or nothing. A finished shot is not redone.
- Every stage folder has a `settings.json`. A changed setting under the same shot name stops the run and changes nothing; use a new shot name. This includes the stage's own settings (`temporal.*`, `animatediff.*` including the IP-Adapter reference file's size) and the settings of the stage it reads from.
- **The default of `animatediff.ip_adapter.enabled` changed** (on, then off), so a shot made with it on is protected the same way: use a new shot name to repeat it.
- Variants: `make_cloud_bundle.py <new_shot> --set KEY=VALUE` changes a setting inside the zip only, so no config edit is needed. The frames of a variant are extracted again from the same video slice and are byte-identical to the original's.

## 5. Results (`dance_run1`: 48 frames, start 5 s, denoise 0.4, seed 12345)

Lower is steadier in every column. "Static change" is the grayscale metric from phase 2 (mean change, in 0 to 255 levels, where the source does not move). "Color flicker" and "color drift" are described below.

### 5.1 The stages compared

| Stage | Static change | Color flicker | Color drift |
|---|---|---|---|
| per-frame baseline (`anime`, phase 2) | 5.85 | 1.86 | 2.60 |
| per-frame + local deflicker | 3.88 | 0.82 | 1.95 |
| AnimateDiff alone | 4.34 | 0.69 | 1.47 |
| **AnimateDiff alone + deflicker (best)** | 3.97 | **0.53** | **1.40** |
| AnimateDiff + IP-Adapter 0.5, reference = frame 28 of the per-frame output | 4.30 | 0.76 | 1.63 |
| the same + deflicker | **3.88** | 0.57 | 1.55 |
| AnimateDiff + IP-Adapter 0.5, reference = frame 20 of the AnimateDiff-only output (`dance_run1_refad`) | 4.61 | 0.73 | 1.53 |
| the same + deflicker | 4.24 | 0.54 | 1.45 |

**The color metric** (`pipeline/metrics.py: color_consistency`): for each cell of a 32x32 grid, the stylizer's color offset is the stylized Lab chroma minus the source Lab chroma. A steady stylizer keeps that offset constant while things move. *Color flicker* is the mean frame-to-frame change of the offset (color jumps). *Color drift* is its spread over the whole shot (outfits changing color over time). Units are Lab chroma; 0 is perfectly steady. It averages over the whole frame, so it understates changes on small subjects such as the dancers. Watch the video too.

### 5.2 What the numbers say

- **The local deflicker does most of the grayscale work.** Static change falls from 5.85 to 3.88 (34%) and color flicker from 1.86 to 0.82, in seconds on the CPU.
- **AnimateDiff is what steadies the colors.** Color drift falls from 2.60 to 1.47 (43%); the deflicker alone only gets to 1.95, because it carries the previous frame's colors forward and cannot correct a color that is already wrong.
- **Both together are best on color** (0.53 flicker, 1.40 drift) and nearly equal on static change (3.97 against 3.88). On grayscale flicker alone, the per-frame route plus the deflicker already matches the cloud route; the cloud route earns its cost in color.
- **IP-Adapter did not help.** With either reference it was no steadier than AnimateDiff alone and the color numbers were about 10% worse; the AnimateDiff-frame reference (`refad`) also made static flicker worse (4.61 against 4.34). With the first reference (a per-frame output frame that itself contains recolored outfits) it pushed red accents onto the dancers that are not in the source. Decision: IP-Adapter is off by default.
- Differences of a few percent are within what one clip and one seed can show; treat them with care.

### 5.3 What the frames look like

- The per-frame baseline recolors the dancers between frames (an outfit goes red, then orange, then grey), and the crowd's clothes change too.
- AnimateDiff keeps skin tones and outfits steady across the shot, but its limbs and the crowd are blockier and somewhat distorted. The metrics do not capture this.
- On the cloud output the deflicker is hard to see by eye; it changes the numbers more than the picture.

### 5.4 Deflicker tuning

Tuned on the per-frame output of this clip. Sharpness is the Laplacian variance relative to the unprocessed frames (1.00 = as sharp).

| strength | sigma | threshold | static change | static SSIM | sharpness |
|---|---|---|---|---|---|
| 0.6 | 0 (blend every frequency) | 25 | 3.78 | 0.918 | 0.58 |
| 0.9 | 1.5 | 25 | 3.64 | 0.912 | 0.93 |
| 1.0 | 1.5 | 25 | 3.51 | 0.913 | 0.92 |
| **0.9** | **2** | 25 | **3.88** | 0.906 | **0.97** |
| 1.0 | 2 | 25 | 3.77 | 0.907 | 0.97 |
| 0.8 | 3 | 25 | 4.34 | 0.897 | 1.00 |
| 1.0 | 3 | 15 | 4.26 | 0.898 | 1.00 |

Chosen: strength 0.9, sigma 2, threshold 25. The full blend (sigma 0) is as steady but loses 42% of the sharpness and smears moving limbs. A lower threshold (15) was slightly worse everywhere. Checked by eye on the highest-motion frame (frame 10); one faint tint of the previous frame remains on one dancer's trousers.

### 5.5 Tried and not kept: RAFT flow instead of Farneback

The deflicker measures motion with OpenCV's Farneback method. A learned flow model, torchvision's RAFT, was tried in its place (temporarily, on the same 48 frames and settings; the code was removed again because it gave no gain). Farneback is the first row of each pair:

| Input | Flow model | Static change | Color flicker | Color drift | Time |
|---|---|---|---|---|---|
| per-frame | **Farneback** | **3.88** | **0.82** | **1.95** | 11 s |
| per-frame | RAFT-small | 3.97 | 0.88 | 2.01 | 12 s |
| per-frame | RAFT-large | 3.94 | 0.84 | 1.99 | 21 s |
| AnimateDiff alone | **Farneback** | **3.97** | 0.54 | 1.40 | 12 s |
| AnimateDiff alone | RAFT-small | 4.00 | 0.54 | 1.40 | 12 s |
| AnimateDiff alone | RAFT-large | 4.00 | 0.54 | 1.40 | 19 s |

RAFT was equal or slightly worse, up to twice as slow, and needed `torchvision`, a weights download and the GPU. On the highest-motion frame (10), Farneback and RAFT-large differ by 1.1 grey levels on average, against 5.2 for what the deflicker changes at all; the pictures look the same.

That clip has a locked-off camera and 87% still pixels, the easy case for Farneback, so it was tested again on the second clip (`capetown`, handheld camera), in two windows of 4 s. First, how accurately each method's warp reproduces the next *source* frame (warp error: mean color error after warping the previous source frame, lower is better; "trusted" is the share of pixels the deflicker would blend), measured on the source frames only:

| Window of clip 2 | Farneback warp error | RAFT-large warp error | Trusted: Farneback / RAFT-large |
|---|---|---|---|
| 8 to 12 s (moderate camera move; `capetown_run1`) | 2.85 | 2.89 | 89.1% / 89.3% |
| 2 to 6 s (a whip-pan) | 4.12 | 3.56 | 84.2% / 86.7% |
| 13 to 17 s (fast pans; `capetown_pan1`) | 4.55 | 3.31 | 83.3% / 88.0% |

RAFT's flow is clearly more accurate during fast camera moves (up to 27% lower error), and equal on the moderate one. But a better flow did not give a steadier result. The deflicker applied to the per-frame output of the two stylized windows (strength 0.9, sigma 2, threshold 25):

| Window | Flow | Static change | Color flicker | Color drift |
|---|---|---|---|---|
| 8 to 12 s | no deflicker | 5.67 | 2.47 | 3.18 |
| 8 to 12 s | **Farneback** | **3.77** | **1.18** | **2.44** |
| 8 to 12 s | RAFT-small / RAFT-large | 3.81 / 3.81 | 1.22 / 1.20 | 2.48 / 2.46 |
| 13 to 17 s | no deflicker | 6.40 | 3.01 | 4.22 |
| 13 to 17 s | **Farneback** | **4.20** | **1.88** | **3.59** |
| 13 to 17 s | RAFT-small / RAFT-large | 4.49 / 4.48 | 1.94 / 1.92 | 3.69 / 3.68 |

On both windows RAFT was 1 to 7% worse than Farneback, never better, so it was not kept. (The bar was: at least 10% better on two of the three measures, with no loss of sharpness and a visible difference; RAFT never came close.) A likely reason is that the deflicker's trust map already rejects the pixels where Farneback is wrong, so a more accurate flow trusts more pixels but not better ones. The code was removed again; nothing about RAFT remains in the repository.

## 6. Verified

- `pytest tests -q`: 47 pass (22 in `tests/test_phase3.py`: deflicker effect, resume, settings protection, trust map, low-pass edge test, the AnimateDiff graph with and without IP-Adapter and with the sliding-window-safe ControlNet nodes, the shot runner with a fake ComfyUI, missing-node message, color metric on synthetic shots, bundle overrides, IP-Adapter off by default).
- The AnimateDiff graph was **run for real** on the local RTX 2060 (20 frames at 0.12 MP, 6 steps, 45 to 57 s, peak GPU memory 5221 MiB), with and without IP-Adapter, through `animatediff_shot()`; this found the ControlNet bug below. Then it ran on Kaggle at full size (48 frames, 0.4 MP) for all three runs in section 5.
- **Bugs found by running it:** the stock ControlNet nodes fail with AnimateDiff's sliding windows ("Control type ControlNet may not support required features for sliding context window"), fixed with ComfyUI-Advanced-ControlNet; a Windows-only subprocess flag in `vram.py` and a PowerShell-only server start crashed on Linux; Kaggle unzips uploaded datasets, so the notebook looks for the extracted project as well as a zip; a ComfyUI that was running before a custom node was installed never sees that node, so `animatediff_shot` now checks the nodes first and the notebook starts a fresh server.

## 7. Known issues and pending

- **One clip.** Everything was tuned and measured on `dance_run1` (a mostly locked-off camera). Other footage may need other settings.
- **AnimateDiff output has blockier limbs and a distorted crowd** that the metrics do not capture. The model is SD1.5 at 0.4 MP.
- **IP-Adapter** was only tried at weight 0.5 with two references. Lower weights, and footage where the checkpoint recolors more strongly, are untested.
- **RAFT flow was tried and not kept** (section 5.5): no gain on either clip, including fast camera pans.
- **The deflicker cannot fix a color that is already wrong,** only smooth changes between frames.
- **The cloud stage needs about 16 GB of GPU memory** and a Kaggle account (internet access in notebooks needs phone verification); free-tier limits change.
- **The static metric** depends on how much of the shot is still (87% here) and says nothing about quality; the color metric averages over the whole frame.
- A style or actor LoRA (phase 4) is still the way to change the checkpoint's look.
