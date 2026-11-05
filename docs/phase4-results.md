# Phase 4 results: LoRA training and use (2026-11-02 to 2026-11-05)

**Where it landed.** The style LoRA works and is on by default; the actor LoRA is off, because trained on real
photos it pulls the face back to photographic. The settled recipe for the selfie clip is in `config/project.yaml`:
style LoRA at 0.6, denoise 0.6, ControlNet 0.8, prompt plus `black hair, red eyes`, deflicker `lowpass_sigma: 8`,
and the local per-frame path rather than the AnimateDiff cloud pass. Sections below, oldest first.

Trained locally on the RTX 2060 with kohya sd-scripts (`training/train.py`), base checkpoint Counterfeit-V3.0, rank 32 / alpha 16, 512 px, batch 1, AdamW8bit, 1.24 steps/s, peak about 3.6 GB.
Grids (same seed and prompts for every column): `training/output/eval/<name>/grid.jpg`, made by `training/eval_grid.py`.

| LoRA | Data | Steps | Time |
|---|---|---|---|
| `adwait_person` | 34 photos + 27 face crops + 19 upper-body crops = 80 images, x3 repeats | 2430 | 32 min |
| `bloodlust_style` | 250 frames from a 640x360 copy of the film, x1 repeat | 2510 | 34 min |

## Actor LoRA
- Works: every LoRA column gives the same face shape, curly dark hair, glasses and build; the plain checkpoint gives a generic anime boy.
- Overfitting grows with epoch: epochs 6 and later turn semi-realistic. In the "full body, street" prompt every LoRA column shows the grey wall and red pipe of a training photo instead of a street (background leak). A grey-blue top with a black collar leaks into prompts that did not ask for it. The headband appears at weight 1.0 and in some epoch 6+ images; negative prompts (`beanie, headband, hat, headwear`) remove it.
- Provisional choice: epoch 4 or 6 at weight about 0.6 to 0.8 (to be confirmed by eye). To reduce the leaks: more photos without the headband, in other clothes and places, then train a new run (`training.actors.Adwait.run: v2`).

## Style LoRA
- Works: the plain checkpoint gives a modern generic anime look; with the LoRA the images get the 90s OVA look (long faces, heavy shading, muted gothic palette, ruined stone streets, red cathedral architecture, blonde girl in a red high-collar jacket).
- Weight 1.0 is too strong (washed out, scenes lose content). Epochs 4 and later turn curly hair into a fur-like texture (overfit); epoch 2 and the final file at weight 0.5 look cleanest.
- Provisional choice: final file at weight 0.5 to 0.6, or epoch 4 at 0.6.
- The source film copy is only 640x360, so the line quality is softer than the real film.

## Both LoRAs in the img2img pipeline (`dance_lora1`, 2 s of the dance clip)
Style `bloodlust_style` at 0.5 + actor `adwait_person` epoch 4 at 0.7, denoise 0.4, same seed as `dance_run1`; 24 frames at 16.3 s/frame, peak 5348 of 6144 MiB (LoRAs add no measurable memory). Comparison picture: `work/default/compare_lora1.png` (rows: source, `dance_lora1`, `dance_run1`).
- Flicker over the same 24 frames (lower = steadier): static-region change 5.17 vs 5.91 (`dance_run1`), whole-frame SSIM ratio 0.991 vs 0.965, color frame-to-frame 1.49 vs 1.99, drift 2.01 vs 2.46. Slightly steadier, but the LoRA look is also less detailed, so this is not proof of better quality.
- Look: darker, more muted and painterly palette than `dance_run1`; several dancers' skin and clothes pick up a red-orange tint; faces are less crisp than the plain checkpoint's cel look. At denoise 0.4 the style stays a colour/texture change, not a redraw.
- The actor LoRA cannot be judged on this clip: the dancers are other people. It needs footage of the actor.

## Actor test on a selfie clip (`me_lora1`, 3 s, 36 frames)
Footage of the actor (portrait selfie, `my video.MOV` in the project root, never in git: the repo is public). That clip was later replaced by `my video new.MOV`, which has steadier lighting; the runs below use the new one. Style 0.6 + actor epoch 4 at 0.7, denoise 0.5, negatives `beanie, headband, hat`. 16.4 s/frame, peak 5379 MiB. Picture: `work/default/compare_me1.png` (top: source, bottom: result, frames 1, 12, 24, 36); video `work/default/out/me_lora1.mp4`.
- The face, glasses and hair follow the source (the lineart ControlNet holds the structure), so the likeness comes mostly from the source, not from the actor LoRA. Whether the LoRA adds anything needs an ablation (same shot without it).
- Still very photographic: at denoise 0.5 the skin becomes flat orange cel patches with blotchy shading (frames 24 and 36), not a clean anime look.
- Unsteady details: eye color changes between frames (grey, brown, blue, red), the glasses frame color shifts, the shirt text turns into gibberish.

## Ablation on the selfie clip (12 frames, same seed; `work/default/compare_ablation.png`)

Columns: source, no LoRA (denoise 0.5), style LoRA only (0.6), style + actor ep4 (0.7, denoise 0.5), same at denoise 0.62 with ControlNet 0.7.

- **The actor LoRA is what keeps the face photographic.** It was trained on real photos, so it pulls the output toward them: soft skin, pink lips, realistic shading. Without it (no LoRA, or style only) the same frames are clearly anime (flat shadow shapes, hard lineart, red-framed glasses).
- Raising denoise to 0.62 did not make the actor-LoRA output more anime; it only made the colours warmer and darker.
- Style only is the most anime-looking, but the face turns older and sterner than the source (scowl, scar-like marks). No LoRA keeps the most of the source's face and is still clearly anime.
- Conclusion: do not use the actor LoRA at 0.7 for anime output. Try it at 0.2 to 0.3, or train it on anime-styled versions of the photos.

## Full selfie clip, style LoRA only (`my video new.MOV`, 6.3 s, 76 frames at 12 fps; `work/default/compare_full.png`)

Actor LoRA off. Prompt adds `black hair, red eyes`; the LoRA's own negatives are `scar, blood, smoke, purple/maroon/brown/colored hair` (`red hair` was left out because it also removed the red eyes).

| Shot | Settings | Whole-frame SSIM ratio (plain / deflickered) | Static-region change | Colour change per frame |
|---|---|---|---|---|
| `full_A` | style 0.6, denoise 0.6, ControlNet 0.8 | 0.886 / 0.969 | 8.35 / 4.51 | 2.14 / 1.29 |
| `full_C` | style 0.7, denoise 0.7, ControlNet 0.6 | 0.862 / 0.969 | 10.04 / 4.99 | 2.72 / 1.51 |

- Hair and eyes now read as anime on every frame; the deflicker (CPU) makes both clearly steadier and softens fine lines slightly.
- Remaining flaws: glasses frame colour changes (red, grey, black), short green or streaked hair patches (A frame 60, C frame 60), and in C a washed-out white face in frame 1 and an exaggerated muscular neck and chest.

## Cloud AnimateDiff run of `full_A`, and the deflicker artifact (2026-11-05)

### The cloud pass loses the anime look
`result_full_A/` (Kaggle, AnimateDiff + the style LoRA at 0.6, denoise 0.6). `settings.json` confirms the LoRA was
applied, so the bundle and notebook changes work. The output is still softer and more photographic than the local
`full_A`: the hard cel shadows and the bold lineart are gone, and the face is rounder. Cause: AnimateDiff's motion
module adds temporal attention trained on real video, which both dilutes the style LoRA and smooths the
high-frequency detail that the cel look is made of. Raising the LoRA weight or the denoise for the cloud run would
fight it but not remove it. For this clip the local per-frame path gives the wanted look; AnimateDiff does not.

### The deflicker smeared the face (fixed: `lowpass_sigma` 2 -> 8)
`full_A_deflicker` and `full_C_deflicker` washed out the face's cel shadows and slid blotches around (a pink smear
on the shirt at frame 50, a flattened face at frame 70). Cause: at `lowpass_sigma: 2` the face's own shading counts
as "low frequency" and is dragged along the optical flow of a nearly flat face, where Farneback flow is unreliable;
each output frame feeds the next, so the error accumulates and moves. Variants on `full_A` (76 frames):

| Settings | SSIM ratio | Static change | Colour f2f | Look |
|---|---|---|---|---|
| plain (no deflicker) | 0.886 | 8.35 | 2.14 | reference |
| strength 0.9, sigma 2, err 25 (old) | 0.969 | 4.51 | 1.29 | smeared, washed-out face |
| **strength 0.9, sigma 8, err 25 (new)** | 0.906 | 6.23 | 1.41 | **cel shadows kept, flicker down** |
| strength 0.6, sigma 8, err 15 | 0.901 | 6.80 | 1.64 | as above, slightly less steady |
| strength 0.5, sigma 12, err 15 | 0.892 | 7.26 | 1.76 | closest to plain, least smoothing |

The old settings score best on every number because the metrics reward averaging, which is exactly the smearing
complained about. Judge this stage by eye, not by the SSIM ratio alone.

### IP-Adapter would not fix the cloud look
It conditions colours and style on a reference image, but the cloud problem is lost cel shading and lineart, not
colour drift, and phase 3 already found it did not help (`docs/phase3-guide.md` section 5). Not re-enabled.

## Not done yet
- `cli.py train` (training is run through the scripts in `training/`).
- A **v2 actor LoRA** trained on anime-styled versions of the photos, which is how Corridor got an actor's likeness in
  the anime style. The current one is trained on the photos as they are, which is why it fights the anime look.
- More actor photos without the headband, in other clothes and places, to cut the background and outfit leaks.
- Phase 5 (matting, compositing, face pass): likely a bigger win on this footage than more LoRA tuning.
