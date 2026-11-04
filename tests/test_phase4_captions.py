"""Phase 4 tests: photo preparation and captioning (fake tagger, no model download)."""
import numpy as np
from PIL import Image

from pipeline.captioning import caption_folder, filter_tags, list_images, prepare_photos


def test_filter_tags_style_and_person():
    tags = ["1boy", "black hair", "brown eyes", "beard", "lowres", "watermark", "outdoors"]
    assert filter_tags(tags, "style") == ["1boy", "black hair", "brown eyes", "beard", "outdoors"]
    assert filter_tags(tags, "person") == ["1boy", "outdoors"]


def test_prepare_photos_resizes_and_skips_done(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.mkdir()
    Image.fromarray(np.zeros((300, 2000, 3), np.uint8)).save(src / "a.png")
    assert prepare_photos(src, dst, max_side=1000, log=lambda *_: None) == 1
    assert max(Image.open(dst / "photo_001.jpg").size) == 1000
    assert prepare_photos(src, dst, max_side=1000, log=lambda *_: None) == 1


def test_captions_written_once_and_hand_edits_kept(tmp_path):
    for n in ("a", "b"):
        Image.fromarray(np.zeros((8, 8, 3), np.uint8)).save(tmp_path / f"{n}.png")
    (tmp_path / "contact_sheet.jpg").write_bytes(b"x")
    (tmp_path / "a.txt").write_text("mine", encoding="utf-8")
    assert [p.name for p in list_images(tmp_path)] == ["a.png", "b.png"]
    assert caption_folder(tmp_path, "trig", "style", lambda p: ["tag1", "lowres"], log=lambda *_: None) == 1
    assert (tmp_path / "a.txt").read_text() == "mine"
    assert (tmp_path / "b.txt").read_text() == "trig, tag1"


def test_crop_box_stays_inside_and_scales_with_face():
    from pipeline.photo_crops import crop_box
    x0, y0, x1, y1 = crop_box((900, 100, 100, 120), "upper", 1000, 2000)   # face near the top right edge
    assert 0 <= x0 and x1 <= 1000 and 0 <= y0 and y1 <= 2000 and x1 - x0 == y1 - y0
    f = crop_box((400, 800, 100, 120), "face", 1000, 2000)
    assert f[2] - f[0] == 260


def test_make_crops_skips_tiny_ambiguous_and_whole_photo(tmp_path):
    from pipeline.photo_crops import make_crops
    src, dst = tmp_path / "s", tmp_path / "d"
    src.mkdir(); dst.mkdir()
    for n in "abcd":
        Image.fromarray(np.full((1600, 1200, 3), 120, np.uint8)).save(src / f"{n}.png")
    faces = {0: [(525, 400, 150, 180, .9)],                                     # a: fine
             1: [(500, 400, 40, 50, .9)],                                       # b: tiny face -> crops too small
             2: [(300, 400, 200, 240, .9), (800, 400, 190, 230, .9)],           # c: two similar people
             3: []}                                                             # d: none
    it = iter(range(4))
    out = make_crops(src, dst, lambda im: faces[next(it)], log=lambda *_: None)
    assert out["face"] == 1 and out["upper"] == 1 and out["no_face"] == 1
    assert (dst / "photo_001_face.jpg").exists() and not (dst / "photo_002_face.jpg").exists()
    assert not list(dst.glob("photo_003*"))


def test_training_plan_and_dataset_toml(tmp_path):
    from pipeline.lora_train import build_command, dataset_toml, plan
    assert plan(250, 2500, 10) == 1 and plan(80, 2400, 10) == 3 and plan(1000, 100, 10) == 1
    toml = dataset_toml(tmp_path / "imgs", 3, 512, False)
    assert "num_repeats = 3" in toml and "keep_tokens = 1" in toml
    p = {"network_dim": 32, "network_alpha": 16, "learning_rate": 1e-4, "text_encoder_lr": 5e-5,
         "epochs": 10, "save_every_n_epochs": 2, "seed": 1}
    cmd = build_command(tmp_path / "m.safetensors", tmp_path / "d.toml", tmp_path, "x", p, max_steps=20)
    assert "AdamW8bit" in cmd and "--gradient_checkpointing" in cmd and "--clip_skip" not in cmd
    assert cmd[-2:] == ["--max_train_steps", "20"]


def test_apply_loras_chains_and_rewires():
    from pipeline.stylize import apply_loras, build_workflow, load_config
    cfg = load_config()
    cfg["style"]["loras"] = []                                                      # independent of the user's config
    wf = build_workflow(cfg, "x.png", (640, 360))
    assert not any(n["class_type"] == "LoraLoader" for n in wf.values())           # empty list = plain checkpoint
    loras = [{"name": "a.safetensors", "weight": 0.5, "trigger": "ta"},
             {"name": "b.safetensors", "weight": 0.7, "trigger": "tb", "negative": "hat"}]
    cfg["style"]["loras"] = loras
    wf = build_workflow(cfg, "x.png", (640, 360))
    assert wf["20"]["inputs"]["model"] == ["1", 0] and wf["21"]["inputs"]["model"] == ["20", 0]
    assert wf["10"]["inputs"]["model"] == ["21", 0] and wf["4"]["inputs"]["clip"] == ["21", 1] == wf["5"]["inputs"]["clip"]
    assert wf["4"]["inputs"]["text"].startswith("ta, tb, ") and wf["5"]["inputs"]["text"].endswith(", hat")
    assert wf["8"]["inputs"]["positive"] == ["4", 0]                               # ControlNet still reads the encoded prompts
