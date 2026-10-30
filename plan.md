# Video → Anime Converter (Corridor Crew "Anime Rock Paper Scissors" style)

## Context
The goal is an end-to-end AI pipeline that turns live-action footage into consistent, flicker-free anime. The reference is Corridor Crew's *Anime Rock Paper Scissors*. Their recipe was:
1. Shoot actors on a greenscreen with flat, even lighting.
2. Fine-tune Stable Diffusion (DreamBooth) on one anime style. They used *Vampire Hunter D: Bloodlust* frames, and also trained on each actor's face so identities stay stable.
3. Run img2img on every frame with low denoise and a fixed seed and prompt.
4. Run DaVinci Resolve's Deflicker several times to kill frame-to-frame flicker.
5. Use stylized Unreal Engine / painted backgrounds, then composite, add VFX (speed lines, glows) and sound.

This plan rebuilds that recipe with 2026-era tools. It adds ControlNet, AnimateDiff, IP-Adapter and optical-flow consistency, which handle temporal stability much better than the original's brute-force deflicker.

**Starting state:** `D:\projects\video to anime conversion using AI` is empty and not a git repo.

**Hardware:** an RTX 2060 with 6 GB of VRAM. You skipped my questions, so I picked these defaults (easy to change):
- **Hybrid compute:** previews and SD1.5 work run locally. LoRA training and final renders run on a rented 24 GB GPU (RunPod or Vast.ai, about $0.3–0.7/hr).
- **Product:** a Python CLI that drives ComfyUI through its API. An optional FastAPI + web UI comes in the last phase.

---

## Architecture

```
            ┌────────────────────── CLI / Web UI (FastAPI) ──────────────────────┐
            │  project.yaml (style, LoRAs, prompts, seeds, denoise, resolution)  │
            └───────────────┬────────────────────────────────────────────────────┘
                            ▼
 [1 Ingest] → [2 Preprocess] → [3 Conditioning] → [4 Stylize] → [5 Temporal] → [6 Composite] → [7 Encode]
   ffmpeg      matte/segment     ControlNet maps    ComfyUI SD     deflicker     bg + fg +       ffmpeg
   probe fps   (RVM/SAM2)        lineart, depth,    + style LoRA   RIFE/EbSynth   VFX + audio    mux audio
   extract     face crop         openpose, flow     + char LoRA    flow-warp
   frames      shot split        (RAFT)             + AnimateDiff  blend
                                                    + IP-Adapter
                            ▲                         ▲
                     [T] Training pipeline (offline, cloud GPU)
                     dataset → caption → kohya_ss LoRA (style + per-actor)
```

### Stage details

**1. Ingest** (`pipeline/ingest.py`)
- Read fps, resolution and audio with `ffprobe`. Split the video into shots using PySceneDetect, so each shot gets its own seed and keyframe settings.
- Extract frames as PNG with `ffmpeg -vf fps=12`. Anime traditionally animates "on twos", so 12 fps stylization is cheaper and looks more authentic. Store the original audio separately.

**2. Preprocess** (`pipeline/preprocess.py`)
- Split foreground from background with **RobustVideoMatting**, or **SAM2** for non-greenscreen footage. This is the Corridor trick: style the actor and the background separately.
- Detect and crop faces with InsightFace. Faces are stylized at higher resolution and pasted back, which works like ADetailer.
- Resize to 512–768 px on the short side for SD1.5, or 1024 px for SDXL.

**3. Conditioning maps** (`pipeline/conditioning.py`)
- **Lineart-anime / SoftEdge:** keeps the outline structure.
- **Depth** (Depth-Anything-V2): keeps volumes.
- **OpenPose / DWPose:** keeps body pose stable.
- **Optical flow** (RAFT): needed later for warping.

**4. Stylization core** (ComfyUI workflow `workflows/stylize_animatediff.json`)
- Base model: an anime SD1.5 checkpoint. SDXL/Illustrious is optional on cloud.
- Add a **style LoRA** (this replaces Corridor's DreamBooth) and a **character LoRA per actor**.
- Frames go through **img2img** at denoise 0.35–0.55 with a fixed seed and a locked prompt.
- **ControlNet stack:** lineart (0.8), depth (0.5), openpose (0.6).
- **AnimateDiff** with a 16-frame context window and overlap. This gives temporal coherence that the original 2023 workflow lacked.
- **IP-Adapter** with a reference anime keyframe keeps colors and palette consistent across a shot.
- Do a second face pass on the crops and blend them back.
- Alternative path for cloud renders: a video diffusion model (Wan 2.x VACE with control video plus a style reference). It produces fewer artifacts, but needs 24 GB or more.

**5. Temporal consistency** (`pipeline/temporal.py`)
- Choose one option:
  - **Option A:** stylize keyframes only (every 8–12 frames) and propagate them with **EbSynth** or optical-flow warping.
  - **Option B:** run the full AnimateDiff pass.
- Deflicker by blending each frame with the flow-warped previous frame (luminance and color histogram matching). This is a scripted version of Resolve's Deflicker; Resolve is still an option for the final polish.
- Optionally hold frames "on twos" and interpolate selectively with RIFE.

**6. Composite** (`pipeline/composite.py`)
- Background: stylize a single clean plate once and reuse it for the whole shot. Static anime backgrounds look authentic and never flicker. Generated or painted backgrounds also work.
- Put the stylized foreground over the background using the alpha from stage 2.
- Anime VFX: cel-shade posterize pass, outline pass, speed lines, bloom/glow, film grain. These use OpenCV / numpy filters.

**7. Encode** (`pipeline/encode.py`)
- Encode with ffmpeg to H.264/H.265 at the target fps and mux the original audio back in.

### [T] Training pipeline (`training/`)
- **Style dataset:** 100–300 frames from the target anime, cleaned with no subtitles and varied shots. Caption them automatically with WD14 tagger plus a trigger word.
- **Character dataset:** 20–40 photos per actor, in different angles and lighting, shot in the same session as the footage.
- Train with **kohya_ss / sd-scripts** for the LoRAs: SD1.5, rank 32, about 2–4k steps, on cloud. SD1.5 can train on the 6 GB card with 8-bit Adam and gradient checkpointing, but slowly.
- Validate with a fixed prompt grid script before using the LoRAs in production.

---

## Project layout
```
video-to-anime/
  config/project.example.yaml      # style, model paths, per-shot overrides
  pipeline/                        # ingest, preprocess, conditioning, stylize, temporal, composite, encode
  pipeline/comfy_client.py         # queue prompts via ComfyUI HTTP/WebSocket API, upload frames, fetch outputs
  workflows/*.json                 # exported ComfyUI API-format graphs (keyframe test, full AnimateDiff, face pass)
  training/                        # dataset prep, captioning, kohya configs, LoRA eval grid
  cli.py                           # `anime run|preview|train|shots` (Typer)
  app/ (phase 6)                   # FastAPI + simple web UI, job queue
  tests/                           # unit tests per stage on a 2-second sample clip
  requirements.txt, README.md
```
Every stage reads and writes `work/<project>/<stage>/<shot>/frame_%05d.png`. This makes stages resumable and cacheable, so a single shot can be re-run.

## Tech stack
Python 3.11, ffmpeg, PySceneDetect, OpenCV, PyTorch, ComfyUI, and these ComfyUI custom nodes: AnimateDiff-Evolved, Advanced-ControlNet, IPAdapter_plus, controlnet_aux preprocessors, VideoHelperSuite. Also RobustVideoMatting / SAM2, InsightFace, RAFT, RIFE, kohya_ss, Typer, and later FastAPI.

## Phased roadmap
1. **Setup:** install ComfyUI and models locally. Prove one-frame img2img with ControlNet lineart on the 2060.
2. **Frame pipeline MVP:** ingest → per-frame img2img → encode. This is the original Corridor approach, used as the baseline.
3. **Consistency:** add AnimateDiff, IP-Adapter and the deflicker/flow blend. Compare flicker against the baseline.
4. **Training:** build the style LoRA and actor LoRAs on cloud GPU, then integrate them.
5. **Composite and polish:** matting, separate background, face pass, anime VFX, audio.
6. **Productize:** project.yaml per-shot overrides, resumable jobs, FastAPI web UI, cloud worker (RunPod serverless running the same ComfyUI image).

## Shooting tips (for best results, as Corridor did)
- Use flat, even lighting and a greenscreen or simple background.
- Use exaggerated, anime-like acting and costumes with strong silhouettes.
- Keep a locked-off or slow camera. Shoot 24 fps and stylize at 12.

## Verification
- `python cli.py preview sample.mp4 --frames 0-48` should produce a 4-second stylized clip locally within the 6 GB limit (512 px, SD1.5).
- A flicker metric script measures mean frame-to-frame SSIM / LPIPS on static regions. Stages 3–5 must improve on the stage 2 baseline.
- Unit tests in `tests/` run each stage on a 2-second clip, checking frame counts, alpha masks and that audio sync is preserved.
- A full run on a 10–20 second test shot on cloud GPU gets a visual review against the reference style.
