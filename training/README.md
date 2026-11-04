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
`training/caption.py` converts actor photos to `training/data/actors_ready/<name>/` and writes a `.txt` next to every image (style frames and actor photos). Triggers: `bloodlust_style` and `<name>_person`.
