# Phase 2 Guide: the frame pipeline MVP

Video in, anime video out, one frame at a time: ingest -> per-frame img2img + lineart ControlNet -> encode.
This is the baseline that phase 3 (consistency) has to beat. It reuses the phase 1 graph unchanged.

## 1. How a run flows

`cli.py preview|run` calls `_process()`:

1. **Resolve inputs.** Video, start, seconds and shot come from the CLI, else from `input:` in the config (shot: else the video's file name, plus `_preview` for `preview`). `preview` uses 4 s if no length is given anywhere. A missing file is a clear error.
2. **Ingest** (`pipeline.video.extract_frames`): ffmpeg writes `work/<project>/frames/<shot>/frame_%05d.png` at `video.work_fps` (12). If frames already exist and were made with the same settings, it reuses them; with different settings the run stops (section 3).
3. **Stylize** (`pipeline.batch.stylize_shot`): for each source frame whose `anime/<shot>/frame_*.png` is missing, upload it, build the graph with `build_workflow()` (the lineart size is derived from the frame), queue, wait, and save the anime frame and the lineart debug map under `anime/` and `lineart/`. The settings check runs first. ComfyUI is started on demand (`pipeline/server.py`) only if at least one frame is left to do, and stopped again if the run started it. The seed is the same on every frame.
4. **Encode** (`pipeline.video.encode`): H.264, CRF 18, yuv420p (sizes rounded down to even), with the matching slice of the source audio as AAC. Output: `work/<project>/out/<shot>.mp4`.

The shot name comes from `--shot`, else `input.shot` in the config, else the video's file name (`<name>_preview` for `preview`). Use a new name to keep several variants side by side.

## 2. Files

| File | Purpose |
|---|---|
| `cli.py` | Typer commands `preview`, `run`, `flicker`; no command means `run` |
| `pipeline/server.py` | `comfy_server`: starts ComfyUI if it isn't running and stops it afterwards |
| `pipeline/video.py` | `extract_frames`, `encode`, `has_audio` (ffmpeg/ffprobe wrappers) |
| `pipeline/batch.py` | `stylize_shot`: the resumable loop over `ComfyClient` |
| `pipeline/shot_state.py` | `prepare`, `SettingsChanged`: records each shot's settings and refuses to reuse a shot made with different ones |
| `pipeline/metrics.py` | `mean_consecutive_ssim`, `static_region_flicker`, `flicker_report` |
| `pipeline/vram.py` | `VramMonitor`: peak GPU memory of a run, printed after stylizing |
| `tests/test_phase2.py` | 19 tests; ComfyUI is faked, ffmpeg is real |
| `config/project.example.yaml` | new `input:` section; `denoise` now 0.4 |
| `samples/dance/dance.webm` | test clip, 51 s, 1080p. CC BY 3.0, ThierryTuyishimeTV, Wikimedia Commons |

## 3. Resuming and redoing

- Re-running the same command with the same settings skips frames that already exist, so a crash or Ctrl+C costs at most one frame.
- Each stage records its settings in `settings.json`: `frames/<shot>` holds the video (path, size, mtime), start, seconds and fps; `anime/<shot>` holds the effective seed and denoise, sampling, prompts, models, ControlNet strength, megapixels and the frames' own settings.
- If a rerun's settings differ, or the shot has no record (made before tracking), the run stops with a message naming what changed (for example `sampling.denoise 0.4 -> 0.5`) and exit code 1. Nothing is deleted, overwritten or encoded.
- There is no force option on purpose. To try new settings, set a new shot name (`input.shot` in the config, or `--shot`); every shot then keeps its own frames and video, which is how phase 3 is compared with the baseline. To keep using a shot, change the settings back.
- The check runs on extraction (video, start, seconds, fps) and on stylizing (seed, denoise, sampling, prompts, models, ControlNet strength, megapixels, and the source frames' settings).

## 4. Verified

- `pytest tests -q`: 24 pass (extraction count and resume, slicing, audio and duration, odd frame sizes, resume after a mid-shot crash, flicker metric, and settings tracking: stop on changed start, denoise or seed leaving every file untouched, different source frames, shots with no record, the CLI exiting with a message and keeping the old video, running with no command, the server start and stop logic, skipping the server when nothing is left to do, the static-region flicker metric and the VRAM monitor).
- Real run on the dance clip (5 s start, 4 s long, denoise 0.4): 48 frames, about 15 s per frame (about 12 min) on the RTX 2060, output has 48 video frames plus audio.
- A 1 s slice at denoise 0.55 also ran, and drifted much more in colors and outfits than 0.4.

## 5. Baseline for phase 3

`cli.py flicker <shot>` (add `--frames N` to use only the first N frames) measures two things on a 256x256 grayscale copy of each frame:

- **Whole frame:** mean SSIM between consecutive frames, stylized vs source. The source's value is the natural motion; a ratio well below 1 means the stylized shot changes more than it should.
- **Static regions:** only pixels where the source itself doesn't change between two frames (after a small blur, under 6 of 255 levels). The stylized frame changing there is pure flicker, because nothing moved. `static_diff` is the mean change in levels (0 = perfectly steady); lower is better. This is the number phase 3 has to improve on, because real motion doesn't count against it.

**The baseline to beat** is `dance_run1` (4 s, denoise 0.4, seed 12345, 48 frames):

| whole-frame source SSIM | anime SSIM | ratio | static pixels | static change (levels) | static SSIM |
|---|---|---|---|---|---|
| 0.875 | 0.833 | 0.951 | 87% | **5.85** | 0.873 |

The metric tells settings apart when the runs cover the same frames. Same 12-frame window (start 5 s):

| Run | denoise | whole-frame ratio | static change (levels) | static SSIM |
|---|---|---|---|---|
| `dance_d040` (first 12 frames) | 0.4 | 0.970 | 5.92 | 0.842 |
| `verify_d040` | 0.5 | 0.946 | 7.07 | 0.827 |
| `dance_preview` | 0.55 | 0.951 | 6.82 | 0.834 |

Denoise 0.4 is the steadiest on both measures. An earlier version of this guide said the metric "did not separate" 0.4 and 0.55; that compared a 48-frame run with a 12-frame run, which is not like for like. Compare runs of the same length and window. The 0.5 and 0.55 values are close enough that their order is within noise.

Limits: the static metric rests on how much of the shot is still (87% here, a mostly locked-off camera). On a shot with a camera move it has little to measure, and it raises an error if no pixel is ever static. It measures change, not quality: a frame that is steady but wrong scores well.

## 6. Peak GPU memory

Measured on a real run (`vram_check`, 6 frames, fresh server, RTX 2060 6 GB): **peak 5399 MiB of 6144 MiB used, headroom 745 MiB**, with about 850 MiB in use by the desktop before the run. So the pipeline itself needs roughly 4.5 GB. Every run now prints this line (`pipeline/vram.py` polls `nvidia-smi`). The figure is the whole GPU, so close other GPU programs when you compare runs.

What it means for phase 3: there is less than 1 GB of headroom. Adding AnimateDiff, IP-Adapter or more ControlNets at 0.4 MP will probably not fit; expect to need a lower resolution, fewer frames per batch, or the cloud GPU the plan already allows for.

## 7. Known issues and pending

- The checkpoint lightens skin tones and re-colors clothing between source and anime. Phase 3 (IP-Adapter) or phase 4 (style/actor LoRA) should fix it.
- Small figures in wide shots lose faces and detail at 0.4 MP.
- No temporal consistency: each frame is independent apart from the shared seed.
- No scene detection or multi-shot handling yet (the `input:` section would become a list of shots in phase 6).
- Source frames are saved at full resolution (about 3 MB each at 1080p), so a long clip needs several GB under `work/`.

## 8. Phase 3 so far: flow-warp deflicker

`cli.py deflicker dance_run1` (`pipeline/temporal.py`, CPU only, about 10 s for 48 frames) blends each stylized frame with the previous output warped along the optical flow (Farneback) of the source frames; where the warp does not reproduce the source it is ignored. Same 48 frames as the baseline:

| | whole-frame ratio | static change (levels) | static SSIM |
|---|---|---|---|
| baseline `anime` | 0.951 | 5.85 | 0.873 |
| `deflicker` (strength 0.6, threshold 25) | 1.006 | **3.78** | 0.918 |

The full blend (sigma 0, every frequency) is 35% steadier where nothing moves, but softens moving limbs, and above strength 0.7 it smears trails behind them. The default is now `temporal.lowpass_sigma: 2` with strength 0.9 (tuned, see the sweep below), which blends only coarse colors and tones so the fresh frame keeps its edges:

| setting | whole-frame ratio | static change | static SSIM |
|---|---|---|---|
| strength 0.8, sigma 3 (default) | 0.981 | 4.34 | 0.897 |
| strength 0.9, sigma 3 | 0.983 | 4.23 | 0.898 |
| strength 0.9, sigma 6 | 0.968 | 4.78 | 0.886 |

This removes about 26% of the flicker (the rest is edges redrawn each frame). On the highest-motion frame (10) edges and feet stay as sharp as the baseline, with a faint tint of the previous frame on one dancer's trousers. The table above (3.78) is the sigma 0 full blend. Not yet judged by eye (check `out/dance_run1_deflicker.mp4` for ghosting on moving limbs), strength is untuned, and AnimateDiff / IP-Adapter are still pending.

Tuning sweep on `dance_run1` (sharpness = Laplacian variance relative to the unprocessed anime frames; 1.00 = as sharp):

| strength | sigma | threshold | static change | static SSIM | sharpness |
|---|---|---|---|---|---|
| 0.6 | 0 (full blend) | 25 | 3.78 | 0.918 | 0.58 |
| 0.9 | 1.5 | 25 | 3.64 | 0.912 | 0.93 |
| 1.0 | 1.5 | 25 | 3.51 | 0.913 | 0.92 |
| **0.9** | **2** | 25 | **3.88** | 0.906 | **0.97** |
| 1.0 | 2 | 25 | 3.77 | 0.907 | 0.97 |
| 0.8 | 3 | 25 | 4.34 | 0.897 | 1.00 |
| 1.0 | 3 | 15 | 4.26 | 0.898 | 1.00 |

Chosen: strength 0.9, sigma 2. A lower error threshold (15) was slightly worse everywhere. One clip, one frame inspected by eye; retune on other footage.

## 9. Phase 3 result: AnimateDiff + IP-Adapter on Kaggle (T4), `dance_run1`

Same 48 frames, denoise 0.4, seed 12345, IP-Adapter weight 0.5 with a frame-28 reference. Lower is steadier in every column.

| stage | static change (levels) | color flicker | color drift |
|---|---|---|---|
| per-frame baseline (`anime`) | 5.85 | 1.86 | 2.60 |
| per-frame + local deflicker (`deflicker`) | 3.88 | 0.82 | 1.95 |
| AnimateDiff + IP-Adapter (`animatediff`) | 4.30 | 0.76 | 1.63 |
| **AnimateDiff + IP-Adapter + deflicker** (`deflicker_animatediff`) | **3.88** | **0.57** | **1.55** |

`cli.py flicker <shot> --stage <stage>` prints all of these (whole-frame ratios: 0.951, 0.992, 0.985, 0.994).

**Color metric** (`pipeline/metrics.py: color_consistency`): for each cell of a 32x32 grid, the stylizer's color offset is (stylized Lab chroma - source Lab chroma). A steady stylizer keeps that offset constant while things move. `color_flicker` is the mean frame-to-frame change of the offset (color jumps), `color_drift` the spread of the offset over the whole shot (outfits changing color over time). Units are Lab chroma (a/b), 0 = steady. It is a mean over the whole frame, so it understates changes on small subjects (the dancers are a small part of the frame); look at the video as well.

What the numbers say:
- **Color jumps (flicker):** AnimateDiff cuts it by 59% (1.86 to 0.76); the local deflicker alone gets 56% (0.82). With both, 69% (0.57).
- **Slow color drift:** only AnimateDiff + IP-Adapter helps a lot (2.60 to 1.63, 37%). The deflicker alone cuts it by 25%, because it carries the previous frame's colors forward and cannot correct a color that is already wrong. The two together reach 1.55.
- **Static flicker (grayscale):** the per-frame route plus deflicker already equals the full cloud route (3.88 both). The cloud route earns its cost in color steadiness, not in grayscale flicker.
- **Best result:** AnimateDiff + IP-Adapter + deflicker is the steadiest on all three measures. Frame by frame it keeps skin tones and outfits steady across the shot; its limbs and crowd are blockier and slightly distorted.
- **Not yet separated:** how much of the color steadiness is AnimateDiff and how much is IP-Adapter (needs an AnimateDiff-only run under a new shot name).

### 9b. Does IP-Adapter help? AnimateDiff alone vs with IP-Adapter (same frames, seed, denoise)

Shot `dance_run1_noip` is `dance_run1` with `animatediff.ip_adapter.enabled: false` (frames byte-identical).

| stage | static change | color flicker | color drift |
|---|---|---|---|
| AnimateDiff alone | 4.34 | **0.69** | **1.47** |
| AnimateDiff + IP-Adapter 0.5 | **4.30** | 0.76 | 1.63 |
| AnimateDiff alone + deflicker | 3.97 | **0.53** | **1.40** |
| AnimateDiff + IP-Adapter 0.5 + deflicker | **3.88** | 0.57 | 1.55 |
| AnimateDiff + IP-Adapter 0.5, reference = frame 20 of the AnimateDiff-only output (`dance_run1_refad`) | 4.61 | 0.73 | 1.53 |
| the same + deflicker | 4.24 | 0.54 | 1.45 |

- **AnimateDiff is what steadies the shot.** IP-Adapter at weight 0.5 with the frame-28 reference gives no measurable gain in steadiness: static change is the same, and the color numbers are about 10% worse with it (single clip and seed, so treat small differences with care).
- **What it does change:** the look. With IP-Adapter the palette is more saturated and takes on the reference's colors (red hair and red socks appear that are not in the source). AnimateDiff alone stays closer to the source's colors (skin tones, a blue skirt).
- **Likely cause:** the reference (frame 28 of the per-frame output) itself contains the recolored outfits (reds and oranges) that the per-frame stylizer invented, so IP-Adapter pushes those colors onto every frame. A reference whose colors match the source, or a lower weight, is untested.
- **Better reference tried (`dance_run1_refad`):** with a reference taken from the AnimateDiff-only output, the stray red accents are gone and the color numbers fall between the other two runs, but static flicker is worse (4.61 against 4.34) and nothing beats AnimateDiff alone.
- **Decision:** IP-Adapter is off by default (`animatediff.ip_adapter.enabled: false`). Untested: weights below 0.5, and footage where the checkpoint recolors more strongly; turn it on with `--set animatediff.ip_adapter.enabled=true` when packing.
