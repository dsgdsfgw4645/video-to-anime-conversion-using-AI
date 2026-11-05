# Phase 4: LoRA training

Where to put things (all of `training/input/`, `training/data/` and `training/output/` stay out of git):

| What | Where |
|---|---|
| The film for the style (Vampire Hunter D: Bloodlust) | `training/input/` (any .mkv/.mp4/.avi; the largest video file is used) |
| Photos of each actor | `training/data/actors/<actor_name>/` , one folder per person, e.g. `training/data/actors/alex/` |

## Style frames
Run `training/extract_style.py` (VS Code: "Phase 4: extract style frames"). It writes 100 to 250 frames to
`training/data/style/images/`. Open `contact_sheet.jpg` there and delete bad frames (subtitles, logos, blur).
If the film has burned-in subtitles, set `training.style.crop_bottom_pct` and use a new output folder.

## Actor photos (20 to 40 per person)
- JPG or PNG, any size 512px or larger on the short side. Keep them as they come from the camera.
- Same person only, one person per photo. Nobody else's face in the frame.
- Vary angle (front, 3/4, profile), expression, and lighting. Include some from the waist up and some close-ups.
- Shoot in the same session and clothes as the video if you can; plain background is best.
- No heavy filters, sunglasses or hats covering the face in most shots.

## Captions
`training/caption.py` converts actor photos to `training/data/actors_ready/<name>/` and writes a `.txt` next to every image (style frames and actor photos). Triggers: `bloodlust_style` and `<name>_person`. Existing captions are never overwritten, so hand edits stay; delete a `.txt` to regenerate it.

## Training (local, on the 6 GB card)
Once per computer: `scripts/setup_training.py` clones kohya sd-scripts into `third_party/sd-scripts` and builds a
separate `.venv-train`, so the project's own `.venv` is untouched. Then **close ComfyUI** (it holds the GPU; the
script refuses to start while port 8188 is open) and run:

```powershell
.venv\Scripts\python.exe training	rain.py --target style     # or --target <ActorName>
.venv\Scripts\python.exe training	rain.py --smoke            # 20 steps, to check speed and memory
```

Output: `training/output/<name>/<name>.safetensors`, plus a checkpoint every 2 epochs. About 33 minutes for 2400 to
2500 steps (1.25 steps/s, about 3.6 GB of GPU memory). A finished LoRA is never overwritten: if the settings
changed the run stops, and you set `training.<target>.run` to a new name to train again.

## Checking and using a LoRA
`training/eval_grid.py --target style|<ActorName>` renders the same four prompts with the same seed for the plain
checkpoint, every saved epoch at weight 0.8 and the final file at two other weights, into
`training/output/eval/<name>/grid.jpg` (32 images, about 5 minutes). Pick a column, then list the file under
`style.loras` in the config to use it in the conversion.

**What the first round settled** (`docs/phase4-results.md`): the style LoRA works and is on by default at weight
0.6. The actor LoRA is **off**: trained on real photos, it pulls the face back to photographic and fights the anime
look, and in a close-up the lineart ControlNet already carries the likeness. Training an actor on anime-styled
versions of the photos is the open idea, and is how Corridor did it.
