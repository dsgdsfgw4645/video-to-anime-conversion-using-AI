# Phase 2 Guide: the frame pipeline MVP

Video in, anime video out, one frame at a time: ingest -> per-frame img2img + lineart ControlNet -> encode.
This is the baseline that phase 3 (consistency) has to beat. It reuses the phase 1 graph unchanged.

## 1. How a run flows

`cli.py preview|run` calls `_process()`:

1. **Resolve inputs.** Video, start, seconds and shot come from the CLI, else from `input:` in the config (shot: else the video's file name, plus `_preview` for `preview`). `preview` uses 4 s if no length is given anywhere. A missing file is a clear error.
2. **Ingest** (`pipeline.video.extract_frames`): ffmpeg writes `work/<project>/frames/<shot>/frame_%05d.png` at `video.work_fps` (12). If frames already exist, it does nothing.
3. **Stylize** (`pipeline.batch.stylize_shot`): for each source frame whose `anime/<shot>/frame_*.png` is missing, upload it, build the graph with `build_workflow()` (the lineart size is derived from the frame), queue, wait, and save the anime frame and the lineart debug map under `anime/` and `lineart/`. The seed is the same on every frame.
4. **Encode** (`pipeline.video.encode`): H.264, CRF 18, yuv420p (sizes rounded down to even), with the matching slice of the source audio as AAC. Output: `work/<project>/out/<shot>.mp4`.

The shot name comes from `--shot`, else `input.shot` in the config, else the video's file name (`<name>_preview` for `preview`). Use a new name to keep several variants side by side.

## 2. Files

| File | Purpose |
|---|---|
| `cli.py` | Typer commands `preview`, `run`, `flicker` |
| `pipeline/video.py` | `extract_frames`, `encode`, `has_audio` (ffmpeg/ffprobe wrappers) |
| `pipeline/batch.py` | `stylize_shot`: the resumable loop over `ComfyClient` |
| `pipeline/shot_state.py` | `prepare`, `SettingsChanged`: records each shot's settings and refuses to reuse a shot made with different ones |
| `pipeline/metrics.py` | `mean_consecutive_ssim`, `flicker_report` |
| `tests/test_phase2.py` | 11 tests; ComfyUI is faked, ffmpeg is real |
| `config/project.example.yaml` | new `input:` section; `denoise` now 0.4 |
| `samples/dance/dance.webm` | test clip, 51 s, 1080p. CC BY 3.0, ThierryTuyishimeTV, Wikimedia Commons |

## 3. Resuming and redoing

- Re-running the same command with the same settings skips frames that already exist, so a crash or Ctrl+C costs at most one frame.
- Each stage records its settings in `settings.json`: `frames/<shot>` holds the video (path, size, mtime), start, seconds and fps; `anime/<shot>` holds the effective seed and denoise, sampling, prompts, models, ControlNet strength, megapixels and the frames' own settings.
- If a rerun's settings differ, or the shot has no record (made before tracking), the run stops with a message naming what changed (for example `sampling.denoise 0.4 -> 0.5`) and exit code 1. Nothing is deleted, overwritten or encoded.
- There is no force option on purpose. To try new settings, set a new shot name (`input.shot` in the config, or `--shot`); every shot then keeps its own frames and video, which is how phase 3 is compared with the baseline. To keep using a shot, change the settings back.
- The check runs on extraction (video, start, seconds, fps) and on stylizing (seed, denoise, sampling, prompts, models, ControlNet strength, megapixels, and the source frames' settings).

## 4. Verified

- `pytest tests -q`: 11 pass (extraction count and resume, slicing, audio and duration, odd frame sizes, resume after a mid-shot crash, flicker metric, and settings tracking: stop on changed start, denoise or seed leaving every file untouched, different source frames, shots with no record, and the CLI exiting with a message and keeping the old video).
- Real run on the dance clip (5 s start, 4 s long, denoise 0.4): 48 frames, about 15 s per frame (about 12 min) on the RTX 2060, output has 48 video frames plus audio.
- A 1 s slice at denoise 0.55 also ran, and drifted much more in colors and outfits than 0.4.

## 5. Baseline for phase 3

Mean SSIM between consecutive frames (`cli.py flicker <shot>`), on a 256x256 grayscale copy. The source's value is the natural motion; a ratio well below 1 means flicker.

| Run | source | anime | ratio |
|---|---|---|---|
| 1 s slice, denoise 0.55 | 0.801 | 0.762 | 0.951 |
| 4 s, denoise 0.4 | 0.875 | 0.833 | 0.951 |

The metric is coarse: it did not separate the two settings, and it measures whole-frame change rather than flicker on static regions as `plan.md` intends. Phase 3 should add a static-region version before comparing methods.

## 6. Known issues and pending

- The checkpoint lightens skin tones and re-colors clothing between source and anime. Phase 3 (IP-Adapter) or phase 4 (style/actor LoRA) should fix it.
- Small figures in wide shots lose faces and detail at 0.4 MP.
- No temporal consistency: each frame is independent apart from the shared seed.
- Peak VRAM is still not measured.
- No scene detection or multi-shot handling yet (the `input:` section would become a list of shots in phase 6).
- Source frames are saved at full resolution (about 3 MB each at 1080p), so a long clip needs several GB under `work/`.
