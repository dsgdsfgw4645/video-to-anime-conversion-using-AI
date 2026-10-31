# Phase 3 on a cloud GPU (Kaggle): AnimateDiff + lineart ControlNet (+ optional IP-Adapter)

The local pipeline stylizes each frame on its own. This stage sends the whole shot through ComfyUI in **one pass**: AnimateDiff's motion module (16-frame windows, 4-frame overlap) keeps neighbouring frames consistent, the same lineart ControlNet keeps the structure, and optionally IP-Adapter ties the colours to a reference image (off by default: it did not help on the test clip, see `docs/phase2-results.md` section 9b). It needs about 16 GB of GPU memory, so it runs on Kaggle (or Colab, or a rented GPU), not on the 6 GB RTX 2060.

**Status: run end to end on the local RTX 2060 with a small test (20 frames at 0.12 MP, 6 steps, about 1 minute), both with and without IP-Adapter, through the real `animatediff_shot()`. Confirmed working on Kaggle (reported by the project owner, 2026-10-31); its flicker numbers are not recorded here yet.** That local run found one real bug (the stock ControlNet nodes can't be used with AnimateDiff's sliding windows; now fixed with ComfyUI-Advanced-ControlNet). If a step fails, the notebook prints which node is missing or ComfyUI's own error.

## What each step does to the flicker

1. **AnimateDiff** (generation time): temporal attention across the frames in a window.
2. **IP-Adapter** (optional, generation time, same pass; **off by default**): conditions every frame on one reference image. On `dance_run1` it gave no gain over AnimateDiff alone and pulled the colours toward the reference. Turn it on with `animatediff.ip_adapter.enabled: true` (and a new shot name), or `--set animatediff.ip_adapter.enabled=true` when packing.
3. **Flow-warp deflicker** (afterwards, CPU, local or in the notebook): `cli.py deflicker --source animatediff`. Keep it only if it still improves the numbers.

Each stage lands in its own folder (`animatediff/`, `deflicker_animatediff/`) so `cli.py flicker --stage <folder>` measures them separately against the baseline (`dance_run1`: static change 5.85, ratio 0.951; the locally deflickered version: 3.88).

## Steps

1. **Pack** (locally, the shot's frames must exist): run **Phase 3 cloud: pack the Kaggle bundle** in VS Code, or `.venv\Scripts\python.exe scripts\make_cloud_bundle.py [shot]`. It writes `work/cloud/bundle_<shot>.zip` (about 44 MB: code, workflows, config, the IP-Adapter reference image, and the extracted frames).
2. **Upload** the zip at kaggle.com/datasets as a new dataset (private is fine). Kaggle unzips it, so the dataset ends up as the extracted folders; the notebook finds either form.
3. **Notebook:** kaggle.com/code, New Notebook, File > Import Notebook, pick `notebooks/kaggle_animatediff.ipynb`. In the right panel: Add Input (your dataset), Accelerator **GPU T4 x2** or **P100**, Internet **On** (needs a phone-verified account). Run All. It installs ComfyUI and the custom nodes, downloads the models (`download_models.py --cloud`), checks that the nodes loaded, runs the shot, measures flicker and runs the deflicker.
4. **Download** `result_<shot>.zip` from the notebook's Output tab and unzip it **at the project root**; it contains `work/default/animatediff/<shot>`, `work/default/deflicker_animatediff/<shot>` and the two mp4s in `work/default/out/`.
5. **Measure locally** (or read the numbers the notebook printed): the VS Code configs "Phase 3 cloud: flicker check of ..." or `cli.py flicker --stage animatediff` and `--stage deflicker_animatediff`. Watch the mp4s too: the metric cannot see ghosting or wrong colours.

## Doing it again for a different video

1. Edit `config/project.yaml` (copy `config/project.example.yaml` to that name once; it is read first): under `input:` set `video`, `start`, `seconds` and a **new `shot` name**.
2. **IP-Adapter (optional):** it is off by default, so there is nothing to do. If you turn it on, the default reference is a frame of the dance clip and its colours would be applied to your new video: set `animatediff.ip_adapter.reference` to an image with the colours you want.
3. **Pack:** `.venv\Scripts\python.exe scripts\make_cloud_bundle.py` (or the VS Code run config "Phase 3 cloud: pack the Kaggle bundle"). It extracts the frames itself if they aren't there (no stylizing), and writes `work/cloud/bundle_<shot>.zip`.
   **Variants without editing the config:** `--set KEY=VALUE` changes a setting in the bundle only, e.g. the same clip with IP-Adapter on, under a new shot name: `.venv\Scripts\python.exe scripts\make_cloud_bundle.py dance_run1_ipa --set animatediff.ip_adapter.enabled=true` (the frames are extracted again from the same video slice and are identical). The zip always carries the effective config as `config/project.yaml`. Put each variant in its own Kaggle dataset, or replace the old zip in the dataset, so the notebook finds only one project.
4. **Upload** that zip as a new Kaggle dataset (or a new version of the old one, but then remove the previous shot's bundle so the notebook finds only one), run the notebook, download `result_<shot>.zip`.
5. **Unpack at the project root**: the zip's `work/default/...` folders must merge into the project's `work/default/` (if your unzip tool makes a `result_<shot>` subfolder, copy its `work` folder over the project's). Then `cli.py flicker <shot> --stage animatediff`.

## Models and nodes the notebook installs

- Custom nodes: ComfyUI-AnimateDiff-Evolved, ComfyUI_IPAdapter_plus, ComfyUI-VideoHelperSuite (loads the frame folder as a batch), ComfyUI-Advanced-ControlNet (the stock ControlNet nodes fail with AnimateDiff's sliding windows: "Control type ControlNet may not support required features for sliding context window"), comfyui_controlnet_aux.
- Models (`scripts/download_models.py --cloud`): `v3_sd15_mm.ckpt` (guoyww/animatediff), and, only when IP-Adapter is enabled, `ip-adapter_sd15.safetensors` and the ViT-H image encoder saved as `CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors` (h94/IP-Adapter, about 2.6 GB), plus the phase 1 checkpoint, ControlNet and lineart extractor.

## Things to know

- **All or nothing:** a shot is one pass, so there is no per-frame resume. If it fails, nothing is written. Settings are tracked as in phase 2: a changed setting under the same shot name stops the run; use a new shot name.
- **Same frames, same size:** the stage reads the shot's extracted frames and scales them to `video.target_megapixels` (0.4), so the comparison with the baseline is like for like.
- **Free-tier limits** change; check Kaggle's current GPU hours and session length. A 4 s shot (48 frames) should take well under one session.
- **Untuned:** denoise 0.4 (shared with phase 2), v3 motion module, `autoselect` beta schedule; IP-Adapter, if enabled, only tried at weight 0.5 with two references.
- **IP-Adapter placement:** the graph applies IP-Adapter to the model before the AnimateDiff loader. If the first run errors or the colours do not change, try swapping the order.
